# Copyright (c) 2026, Trustbit Software and contributors
# KGS Staff app (/staff PWA) — phase 1: warehouse transfers.
#
# Every endpoint is POST-only, needs a logged-in Stock User / Stock Manager and
# re-checks everything server-side: the PWA is a convenience, never a boundary.
#
# Why this module enforces stock availability itself: Stock Settings has
# allow_negative_stock = 1 on splashbox.in, so ERPNext would happily transfer
# stock that is not there. A transfer may only move what the source warehouse
# holds right now (checked under a row lock on tabBin).
#
# Never back-dated: posting date/time is always "now" (CLAUDE.md Rule 15 — a
# back-dated stock document queues Repost Item Valuations on the 1-vCPU box).
# Never loads the item catalogue: one barcode lookup or a 15-row search per
# call (DANGER 21 — the POS get_items storm).

import json
import re
import time

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

STAFF_ROLES = ("Stock User", "Stock Manager")
MANAGER_ROLES = ("Stock Manager",)
TRANSFER_SLIP_FORMAT = "KGS Transfer Slip"
MAX_LINES = 150  # one submit must finish inside a web-worker request on 1 vCPU
BULK_MAX_LINES = 15000  # bulk: split into MAX_LINES transfers, run in the background
SEARCH_LIMIT = 15
RATE_LIMIT_PER_MINUTE = 120  # per USER — every shop phone shares one NAT IP
_CLIENT_REF_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_REF_TAG = "[Staff app · ref:{0}]"
_EPS = 1e-6


# ── access ───────────────────────────────────────────────────────────────────


def app_enabled():
	"""Kill switch: site_config "kgs_staff_app_disabled": 1 turns the app off."""
	return not cint(frappe.conf.get("kgs_staff_app_disabled"))


def sw_enabled():
	"""site_config "kgs_staff_app_sw_off": 1 makes every phone unregister its
	service worker on the next launch (no deploy needed)."""
	return not cint(frappe.conf.get("kgs_staff_app_sw_off"))


def user_allowed(user=None):
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	return bool(set(frappe.get_roles(user)) & set(STAFF_ROLES))


def _is_manager():
	return bool(set(frappe.get_roles()) & set(MANAGER_ROLES))


def _guard():
	if frappe.session.user in (None, "", "Guest"):
		raise frappe.PermissionError(_("Please sign in again."))
	if not app_enabled():
		raise frappe.PermissionError(_("The staff app is switched off. Please use the ERP."))
	if not user_allowed():
		raise frappe.PermissionError(_("The staff app is for Stock Users. Your account does not have that role."))
	_rate_limit()


def _rate_limit():
	window = int(time.time() // 60)
	key = frappe.cache.make_key(f"kgs_staff_rl:{frappe.session.user}:{window}")
	count = frappe.cache.incr(key)
	if count == 1:
		frappe.cache.expire(key, 90)
	if count > RATE_LIMIT_PER_MINUTE:
		raise frappe.TooManyRequestsError(_("Too many requests. Please wait a minute."))


# ── helpers ──────────────────────────────────────────────────────────────────


def _warehouses():
	"""Leaf, enabled, non-transit warehouses the user may see (get_list applies
	User Permissions), with the number of items in stock in each."""
	rows = frappe.get_list(
		"Warehouse",
		filters={"is_group": 0, "disabled": 0},
		fields=["name", "warehouse_name", "company", "warehouse_type"],
		order_by="company asc, warehouse_name asc",
		limit_page_length=500,
	)
	rows = [r for r in rows if (r.warehouse_type or "") != "Transit"]
	counts = dict(
		frappe.db.sql(
			"select warehouse, sum(actual_qty > 0) from `tabBin` group by warehouse"
		)
	)
	for r in rows:
		r["items_in_stock"] = cint(counts.get(r.name))
		r.pop("warehouse_type", None)
	return rows


def _warehouse_row(name):
	return frappe.db.get_value(
		"Warehouse", name, ["name", "company", "is_group", "disabled", "warehouse_type"], as_dict=True
	)


def _bin(item_code, warehouse):
	if not warehouse:
		return frappe._dict(actual_qty=0, valuation_rate=0)
	row = frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, ["actual_qty", "valuation_rate"], as_dict=True
	)
	return row or frappe._dict(actual_qty=0, valuation_rate=0)


def _whole_number_uoms(uoms):
	if not uoms:
		return set()
	return set(
		frappe.get_all("UOM", filters={"name": ["in", list(uoms)], "must_be_whole_number": 1}, pluck="name")
	)


def _item_uoms(item_code, stock_uom):
	"""[{uom, factor, whole}] — stock UOM first, then its conversions."""
	conv = frappe.get_all(
		"UOM Conversion Detail",
		filters={"parent": item_code, "parenttype": "Item"},
		fields=["uom", "conversion_factor"],
		order_by="idx asc",
	)
	out = [{"uom": stock_uom, "factor": 1.0}]
	for c in conv:
		if c.uom and c.uom != stock_uom and flt(c.conversion_factor) > 0:
			out.append({"uom": c.uom, "factor": flt(c.conversion_factor)})
	whole = _whole_number_uoms({u["uom"] for u in out})
	for u in out:
		u["whole"] = 1 if u["uom"] in whole else 0
	return out


def _item_payload(item_code, from_warehouse=None, to_warehouse=None, scanned_uom=None):
	item = frappe.db.get_value(
		"Item",
		item_code,
		["name", "item_name", "stock_uom", "disabled", "is_stock_item", "has_variants", "item_group"],
		as_dict=True,
	)
	if not item:
		return None
	uoms = _item_uoms(item.name, item.stock_uom)
	src = _bin(item.name, from_warehouse)
	problems = []
	if item.disabled:
		problems.append(_("This item is disabled."))
	if not item.is_stock_item:
		problems.append(_("This is not a stock item."))
	if item.has_variants:
		problems.append(_("This is a template item — scan the actual variant."))
	if from_warehouse and flt(src.actual_qty) <= _EPS:
		problems.append(_("No stock in {0}.").format(from_warehouse))
	elif from_warehouse and flt(src.valuation_rate) <= 0:
		problems.append(_("Has no cost price in {0} — ask accounts to fix it first.").format(from_warehouse))
	default_uom = scanned_uom if scanned_uom in {u["uom"] for u in uoms} else item.stock_uom
	return {
		"item_code": item.name,
		"item_name": item.item_name,
		"item_group": item.item_group,
		"stock_uom": item.stock_uom,
		"uoms": uoms,
		"uom": default_uom,
		"available": flt(src.actual_qty),
		"at_target": flt(_bin(item.name, to_warehouse).actual_qty) if to_warehouse else None,
		"problems": problems,
	}


def _find_item(code):
	"""Barcode lookup order: Item Barcode (carries the packet/piece UOM) →
	ISBN (custom_isbn_barcode) → item code. Returns (item_code, uom) or (None, None)."""
	row = frappe.db.get_value("Item Barcode", {"barcode": code}, ["parent", "uom"], as_dict=True)
	if row:
		return row.parent, row.uom
	if frappe.db.has_column("Item", "custom_isbn_barcode"):
		item = frappe.db.get_value("Item", {"custom_isbn_barcode": code}, "name")
		if item:
			return item, None
	if frappe.db.exists("Item", code):
		return code, None
	return None, None


def _pdf_url(name):
	fmt = TRANSFER_SLIP_FORMAT if frappe.db.exists("Print Format", TRANSFER_SLIP_FORMAT) else "Standard"
	from urllib.parse import urlencode

	return "/api/method/frappe.utils.print_format.download_pdf?" + urlencode(
		{"doctype": "Stock Entry", "name": name, "format": fmt, "no_letterhead": 1}
	)


# ── endpoints ────────────────────────────────────────────────────────────────


@frappe.whitelist(methods=["POST"])
def boot():
	_guard()
	warehouses = _warehouses()
	names = {w["name"] for w in warehouses}
	default_from = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"is_manager": 1 if _is_manager() else 0,
		"warehouses": warehouses,
		"default_from": default_from if default_from in names else None,
		"max_lines": MAX_LINES,
	}


@frappe.whitelist(methods=["POST"])
def lookup_item(code, from_warehouse=None, to_warehouse=None):
	_guard()
	code = (code or "").strip()
	if not code or len(code) > 140:
		return {"found": 0, "code": code}
	item_code, uom = _find_item(code)
	if not item_code:
		return {"found": 0, "code": code}
	payload = _item_payload(item_code, from_warehouse, to_warehouse, scanned_uom=uom)
	if not payload:
		return {"found": 0, "code": code}
	payload["found"] = 1
	payload["code"] = code
	return payload


@frappe.whitelist(methods=["POST"])
def get_item(item_code, from_warehouse=None, to_warehouse=None):
	"""Picked from the search list — same payload as a scan."""
	_guard()
	payload = _item_payload(item_code, from_warehouse, to_warehouse)
	if not payload:
		frappe.throw(_("Item {0} not found.").format(item_code))
	payload["found"] = 1
	return payload


@frappe.whitelist(methods=["POST"])
def stock_levels(item_codes, from_warehouse=None, to_warehouse=None):
	"""One call to refresh every line after a warehouse change:
	{item_code: {available, at_target, valuation_ok}}."""
	_guard()
	if isinstance(item_codes, str):
		item_codes = json.loads(item_codes or "[]")
	item_codes = list(dict.fromkeys(str(c) for c in (item_codes or [])))[:BULK_MAX_LINES]
	if not item_codes:
		return {}
	out = {c: {"available": 0.0, "at_target": 0.0 if to_warehouse else None, "valuation_ok": 0} for c in item_codes}
	for wh, key in ((from_warehouse, "available"), (to_warehouse, "at_target")):
		for code, r in _batch_bins(item_codes, wh).items():
			out[code][key] = flt(r.actual_qty)
			if key == "available":
				out[code]["valuation_ok"] = 1 if flt(r.valuation_rate) > 0 else 0
	return out


@frappe.whitelist(methods=["POST"])
def search_items(txt, from_warehouse=None):
	"""Every word must appear in the item name, code or ISBN. Items with stock
	in the source warehouse come first."""
	_guard()
	words = [w for w in re.split(r"\s+", (txt or "").strip()) if w][:5]
	if not words or len("".join(words)) < 2:
		return []
	has_isbn = frappe.db.has_column("Item", "custom_isbn_barcode")
	conds, values = [], {"wh": from_warehouse or ""}
	for i, w in enumerate(words):
		values[f"w{i}"] = f"%{w}%"
		isbn = f" or i.custom_isbn_barcode like %(w{i})s" if has_isbn else ""
		conds.append(f"(i.item_name like %(w{i})s or i.name like %(w{i})s{isbn})")
	rows = frappe.db.sql(
		f"""
		select i.name as item_code, i.item_name, i.stock_uom, ifnull(b.actual_qty, 0) as available
		from `tabItem` i
		left join `tabBin` b on b.item_code = i.name and b.warehouse = %(wh)s
		where i.disabled = 0 and i.is_stock_item = 1 and i.has_variants = 0
			and {" and ".join(conds)}
		order by (ifnull(b.actual_qty, 0) > 0) desc, i.item_name asc
		limit {SEARCH_LIMIT}
		""",
		values,
		as_dict=True,
	)
	return rows


@frappe.whitelist(methods=["POST"])
def create_transfer(from_warehouse, to_warehouse, items, client_ref, remarks=None):
	"""Create AND submit one Material Transfer.

	items: [{item_code, qty, uom}] (JSON). Line problems come back as
	{"ok": 0, "problems": [{idx, item_code, message}]} so the phone can mark
	the exact lines; anything else raises."""
	_guard()
	user = frappe.session.user

	if not _CLIENT_REF_RE.match(client_ref or ""):
		frappe.throw(_("Invalid request reference. Please reload the app."))
	tag = _REF_TAG.format(client_ref)

	# Idempotency: a retried tap (slow network, double tap) returns the transfer
	# that was already made instead of moving the stock twice.
	existing = _existing_transfer(user, tag)
	if existing:
		return _created_response(existing, already=1)

	lock_key = frappe.cache.make_key(f"kgs_staff_xfer_lock:{user}:{client_ref}")
	if not frappe.cache.set(lock_key, 1, ex=180, nx=True):
		frappe.throw(_("This transfer is already being saved. Please wait a moment."))
	try:
		return _create_transfer(user, from_warehouse, to_warehouse, items, tag, remarks)
	finally:
		frappe.cache.delete(lock_key)


def _existing_transfer(user, tag):
	return frappe.db.get_value(
		"Stock Entry",
		{
			"owner": user,
			"purpose": "Material Transfer",
			"docstatus": ["<", 2],
			"remarks": ["like", f"%{tag}%"],
			"creation": [">", frappe.utils.add_days(now_datetime(), -2)],
		},
		"name",
	)


def _created_response(name, already=0):
	se = frappe.db.get_value(
		"Stock Entry", name, ["name", "docstatus", "from_warehouse", "to_warehouse"], as_dict=True
	)
	lines = frappe.db.count("Stock Entry Detail", {"parent": name})
	return {
		"ok": 1,
		"already": already,
		"name": se.name,
		"docstatus": se.docstatus,
		"from_warehouse": se.from_warehouse,
		"to_warehouse": se.to_warehouse,
		"lines": lines,
		"pdf_url": _pdf_url(se.name),
	}


def _validate_warehouses(from_warehouse, to_warehouse):
	if not from_warehouse or not to_warehouse:
		frappe.throw(_("Choose both warehouses."))
	if from_warehouse == to_warehouse:
		frappe.throw(_("From and To must be different warehouses."))
	allowed = {w["name"] for w in _warehouses()}
	src, dst = _warehouse_row(from_warehouse), _warehouse_row(to_warehouse)
	for name, row in ((from_warehouse, src), (to_warehouse, dst)):
		if not row or name not in allowed:
			frappe.throw(_("Warehouse {0} cannot be used here.").format(name))
	if src.company != dst.company:
		frappe.throw(
			_("{0} and {1} belong to different companies. That is a sale, not a transfer.").format(
				from_warehouse, to_warehouse
			)
		)
	return src.company


def _parse_lines(items, max_lines=MAX_LINES):
	if isinstance(items, str):
		try:
			items = json.loads(items)
		except ValueError:
			frappe.throw(_("Could not read the item list."))
	if not isinstance(items, list) or not items:
		frappe.throw(_("Add at least one item."))
	if len(items) > max_lines:
		frappe.throw(_("Too many lines ({0}). At most {1} lines here.").format(len(items), max_lines))
	lines = []
	for idx, row in enumerate(items, start=1):
		if not isinstance(row, dict):
			frappe.throw(_("Could not read line {0}.").format(idx))
		lines.append(
			frappe._dict(
				idx=idx,
				item_code=str(row.get("item_code") or "").strip(),
				uom=str(row.get("uom") or "").strip(),
				qty=flt(row.get("qty")),
			)
		)
	return lines


def _chunks(seq, size=1000):
	seq = list(seq)
	for i in range(0, len(seq), size):
		yield seq[i : i + size]


def _batch_items(item_codes):
	out = {}
	for part in _chunks(set(item_codes)):
		for r in frappe.get_all(
			"Item",
			filters={"name": ["in", part]},
			fields=["name", "item_name", "stock_uom", "disabled", "is_stock_item", "has_variants", "item_group"],
		):
			out[r.name] = r
	return out


def _batch_uoms(item_rows):
	"""{item_code: {uom: {uom, factor, whole}}} — stock UOM + conversions, in
	a few queries whatever the number of items (bulk transfers: thousands)."""
	out = {code: {r.stock_uom: {"uom": r.stock_uom, "factor": 1.0}} for code, r in item_rows.items()}
	for part in _chunks(item_rows):
		for c in frappe.db.sql(
			"""select parent, uom, conversion_factor from `tabUOM Conversion Detail`
			where parenttype = 'Item' and parent in %s order by parent, idx""",
			(tuple(part),),
			as_dict=True,
		):
			if c.uom and flt(c.conversion_factor) > 0 and c.uom not in out[c.parent]:
				out[c.parent][c.uom] = {"uom": c.uom, "factor": flt(c.conversion_factor)}
	whole = _whole_number_uoms({u for m in out.values() for u in m})
	for m in out.values():
		for u in m.values():
			u["whole"] = 1 if u["uom"] in whole else 0
	return out


def _batch_bins(item_codes, warehouse, for_update=False):
	out = {}
	if not warehouse:
		return out
	lock = " for update" if for_update else ""
	for part in _chunks(set(item_codes)):
		for r in frappe.db.sql(
			f"""select item_code, actual_qty, valuation_rate from `tabBin`
			where warehouse = %s and item_code in %s{lock}""",
			(warehouse, tuple(part)),
			as_dict=True,
		):
			out[r.item_code] = r
	return out


def _validate_transfer(from_warehouse, to_warehouse, items, max_lines=MAX_LINES):
	"""Every rule of a transfer, for any number of lines. Returns
	(company, lines, problems); lines carry uom/factor/stock_qty when valid.
	Takes a row lock on the source bins (held until this request commits)."""
	company = _validate_warehouses(from_warehouse, to_warehouse)
	lines = _parse_lines(items, max_lines)
	problems = []

	def problem(line, msg):
		problems.append({"idx": line.idx, "item_code": line.item_code, "message": msg})

	item_rows = _batch_items(l.item_code for l in lines if l.item_code)
	uoms = _batch_uoms(item_rows)
	needed = {}  # item_code -> stock qty asked for
	for line in lines:
		item = item_rows.get(line.item_code)
		if not item:
			problem(line, _("Item not found."))
			continue
		if item.disabled or not item.is_stock_item or item.has_variants:
			problem(line, _("This item cannot be transferred (disabled, non-stock or template)."))
			continue
		if line.qty <= 0:
			problem(line, _("Quantity must be more than zero."))
			continue
		uom = uoms[item.name].get(line.uom or item.stock_uom)
		if not uom:
			problem(line, _("{0} is not a unit of this item.").format(line.uom))
			continue
		if uom["whole"] and abs(line.qty - round(line.qty)) > _EPS:
			problem(line, _("{0} must be a whole number.").format(uom["uom"]))
			continue
		line.uom = uom["uom"]
		line.factor = uom["factor"]
		line.stock_qty = flt(line.qty * uom["factor"], 6)
		needed[item.name] = needed.get(item.name, 0) + line.stock_qty

	# Availability under a row lock, so two phones cannot both move the last
	# units of the same item out of the same warehouse.
	if needed:
		bins = _batch_bins(needed, from_warehouse, for_update=True)
		reported = set()
		for line in lines:
			if line.item_code not in needed or line.item_code in reported:
				continue
			b = bins.get(line.item_code) or frappe._dict(actual_qty=0, valuation_rate=0)
			if needed[line.item_code] > flt(b.actual_qty) + _EPS:
				reported.add(line.item_code)
				problem(
					line,
					_("Only {0} {1} in {2}, you asked for {3}.").format(
						_fmt(b.actual_qty), item_rows[line.item_code].stock_uom, from_warehouse,
						_fmt(needed[line.item_code]),
					),
				)
			elif flt(b.valuation_rate) <= 0:
				reported.add(line.item_code)
				problem(line, _("Has no cost price in {0} — ask accounts to fix it first.").format(from_warehouse))
	return company, lines, sorted(problems, key=lambda p: p["idx"])


def _make_entry(company, from_warehouse, to_warehouse, lines, tag, remarks):
	note = (remarks or "").strip()[:500]
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.purpose = "Material Transfer"
	se.company = company
	se.set_posting_time = 0  # always now — never back-dated (Rule 15)
	se.from_warehouse = from_warehouse
	se.to_warehouse = to_warehouse
	se.remarks = (note + "\n" if note else "") + tag
	for line in lines:
		se.append(
			"items",
			{
				"item_code": line.item_code,
				"qty": line.qty,
				"uom": line.uom,
				"conversion_factor": line.factor,
				"s_warehouse": from_warehouse,
				"t_warehouse": to_warehouse,
			},
		)
	se.insert()  # normal permission checks: Stock User may create + submit
	se.submit()
	return se.name


def _create_transfer(user, from_warehouse, to_warehouse, items, tag, remarks):
	company, lines, problems = _validate_transfer(from_warehouse, to_warehouse, items)
	if problems:
		return {"ok": 0, "problems": problems}
	return _created_response(_make_entry(company, from_warehouse, to_warehouse, lines, tag, remarks))


def _fmt(n):
	n = flt(n, 3)
	return str(int(n)) if n == int(n) else str(n)


@frappe.whitelist(methods=["POST"])
def my_transfers(scope="mine", days=30):
	_guard()
	days = min(max(cint(days) or 30, 1), 120)
	everyone = scope == "all" and _is_manager()
	values = {"since": frappe.utils.add_days(frappe.utils.nowdate(), -days), "user": frappe.session.user}
	owner_cond = "" if everyone else "and se.owner = %(user)s"
	return frappe.db.sql(
		f"""
		select se.name, se.posting_date, se.posting_time, se.from_warehouse, se.to_warehouse,
			se.docstatus, se.owner, count(d.name) as line_count, sum(d.transfer_qty) as stock_qty,
			(se.remarks like '%%[Staff app%%') as from_app
		from `tabStock Entry` se
		left join `tabStock Entry Detail` d on d.parent = se.name
		where se.purpose = 'Material Transfer' and se.posting_date >= %(since)s {owner_cond}
		group by se.name
		order by se.creation desc
		limit 100
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist(methods=["POST"])
def get_transfer(name):
	_guard()
	se = frappe.get_doc("Stock Entry", name)
	se.check_permission("read")
	if se.purpose != "Material Transfer":
		frappe.throw(_("{0} is not a warehouse transfer.").format(name))
	return {
		"name": se.name,
		"docstatus": se.docstatus,
		"posting_date": se.posting_date,
		"posting_time": str(se.posting_time),
		"from_warehouse": se.from_warehouse,
		"to_warehouse": se.to_warehouse,
		"owner": se.owner,
		"owner_name": frappe.utils.get_fullname(se.owner),
		"remarks": re.sub(r"\s*\[Staff app · ref:[^\]]*\]", "", se.remarks or "").strip(),
		"items": [
			{
				"item_code": d.item_code,
				"item_name": d.item_name,
				"qty": d.qty,
				"uom": d.uom,
				"transfer_qty": d.transfer_qty,
				"stock_uom": d.stock_uom,
				"s_warehouse": d.s_warehouse,
				"t_warehouse": d.t_warehouse,
			}
			for d in se.items
		],
		"pdf_url": _pdf_url(se.name),
	}


# ── bulk ─────────────────────────────────────────────────────────────────────
# Three ways to load many lines into the draft (school set, everything in a
# warehouse, an Excel/CSV sheet) and one way to move more than MAX_LINES:
# create_bulk_transfer validates the WHOLE list, then a background job on the
# long queue submits it as consecutive transfers of <= MAX_LINES lines, each
# tagged "[Staff app · ref:<ref>#<part>/<parts>]" so a re-run skips the parts
# already made. Stock Managers only, and never in shop hours (1 vCPU; tills).

SHOP_HOURS = ((10, 30), (19, 30))  # IST — site timezone is Asia/Kolkata
MAX_UPLOAD_BYTES = 3 * 1024 * 1024
_BULK_TAG = "[Staff app · ref:{0}#{1}/{2}]"


def _in_shop_hours():
	if cint(frappe.conf.get("kgs_staff_bulk_in_shop_hours")):
		return False
	now = now_datetime()
	t = (now.hour, now.minute)
	return SHOP_HOURS[0] <= t < SHOP_HOURS[1]


def _merge_wanted(wanted):
	"""[(item_code, qty, uom|None)] → same item+unit summed, first-seen order."""
	merged = {}
	for code, qty, uom in wanted:
		key = (code, uom or "")
		if key in merged:
			merged[key][1] += flt(qty)
		else:
			merged[key] = [code, flt(qty), uom or None]
	return [tuple(v) for v in merged.values()]


def _bulk_payloads(wanted, from_warehouse, to_warehouse):
	"""Line payloads (same shape as a scan) for many items in a few queries.
	Items that can never be moved from From are returned in `skipped` with the
	reason; a shortfall is NOT skipped — the line shows "Only X in …" in red."""
	wanted = _merge_wanted(wanted)
	codes = [w[0] for w in wanted]
	items = _batch_items(codes)
	uoms = _batch_uoms(items)
	src = _batch_bins(codes, from_warehouse)
	dst = _batch_bins(codes, to_warehouse) if to_warehouse else {}
	lines, skipped = [], []
	for code, qty, uom in wanted:
		it = items.get(code)
		b = src.get(code)
		reason = None
		if not it:
			reason = _("Item not found.")
		elif it.disabled:
			reason = _("This item is disabled.")
		elif not it.is_stock_item or it.has_variants:
			reason = _("Not a stock item / template item.")
		elif not b or flt(b.actual_qty) <= _EPS:
			reason = _("No stock in {0}.").format(from_warehouse)
		elif flt(b.valuation_rate) <= 0:
			reason = _("Has no cost price in {0} — ask accounts to fix it first.").format(from_warehouse)
		elif uom and uom not in uoms[code]:
			reason = _("{0} is not a unit of this item.").format(uom)
		elif qty <= 0:
			reason = _("No quantity.")
		if reason:
			skipped.append({"item_code": code, "item_name": it.item_name if it else "", "qty": qty, "uom": uom, "reason": reason})
			continue
		unit = uom or it.stock_uom
		if uoms[code][unit]["whole"]:
			qty = round(qty, 6)
		lines.append(
			{
				"found": 1,
				"item_code": code,
				"item_name": it.item_name,
				"item_group": it.item_group,
				"stock_uom": it.stock_uom,
				"uoms": list(uoms[code].values()),
				"uom": unit,
				"qty": qty,
				"available": flt(b.actual_qty),
				"at_target": flt(dst[code].actual_qty) if code in dst else (0.0 if to_warehouse else None),
				"valuation_ok": 1,
				"problems": [],
			}
		)
	return lines, skipped


@frappe.whitelist(methods=["POST"])
def search_bundles(txt=""):
	"""School sets (Product Bundles) by name/code/description — every word must match."""
	_guard()
	words = [w for w in re.split(r"\s+", (txt or "").strip()) if w][:5]
	conds, values = ["pb.disabled = 0"], {"phrase": " ".join(words)}
	for i, w in enumerate(words):
		values[f"w{i}"] = f"%{w}%"
		conds.append(f"(pb.name like %(w{i})s or i.item_name like %(w{i})s or pb.description like %(w{i})s)")
	return frappe.db.sql(
		f"""
		select pb.name as bundle, ifnull(i.item_name, pb.description) as bundle_name,
			(select count(*) from `tabProduct Bundle Item` pbi where pbi.parent = pb.name) as items_count
		from `tabProduct Bundle` pb
		left join `tabItem` i on i.name = pb.new_item_code
		where {" and ".join(conds)}
		order by (locate(%(phrase)s, ifnull(i.item_name, pb.description)) = 1) desc,
			(locate(%(phrase)s, ifnull(i.item_name, pb.description)) > 0) desc,
			length(ifnull(i.item_name, pb.description)) asc, bundle_name asc
		limit 20
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist(methods=["POST"])
def expand_bundle(bundle, sets, from_warehouse, to_warehouse=None):
	"""A school set × number of sets → lines. Rows marked "Not Available" in
	the set (custom_product_bundle_stock) are skipped, as at the POS."""
	_guard()
	sets = cint(sets)
	if sets < 1 or sets > 5000:
		frappe.throw(_("Number of sets must be between 1 and 5000."))
	if not frappe.db.exists("Product Bundle", bundle):
		frappe.throw(_("School set {0} not found.").format(bundle))
	has_na = frappe.db.has_column("Product Bundle Item", "custom_product_bundle_stock")
	rows = frappe.db.sql(
		f"""select item_code, qty, uom{", custom_product_bundle_stock as na" if has_na else ", '' as na"}
		from `tabProduct Bundle Item` where parent = %s order by idx""",
		bundle,
		as_dict=True,
	)
	wanted, skipped = [], []
	for r in rows:
		if (r.na or "") == "Not Available":
			skipped.append({"item_code": r.item_code, "item_name": frappe.db.get_value("Item", r.item_code, "item_name") or "",
				"qty": flt(r.qty) * sets, "uom": r.uom, "reason": _("Marked Not Available in this set.")})
			continue
		wanted.append((r.item_code, flt(r.qty) * sets, r.uom or None))
	lines, more_skipped = _bulk_payloads(wanted, from_warehouse, to_warehouse)
	name = frappe.db.get_value("Item", bundle, "item_name") or bundle
	return {"bundle": bundle, "bundle_name": name, "sets": sets, "lines": lines, "skipped": skipped + more_skipped}


@frappe.whitelist(methods=["POST"])
def warehouse_contents(from_warehouse, to_warehouse=None):
	"""Everything with stock in From, at its full quantity (e.g. a van coming back)."""
	_guard()
	_validate_warehouses(from_warehouse, to_warehouse) if to_warehouse else None
	rows = frappe.db.sql(
		"""select b.item_code, b.actual_qty from `tabBin` b
		join `tabItem` i on i.name = b.item_code
		where b.warehouse = %s and b.actual_qty > 0
		order by i.item_name limit %s""",
		(from_warehouse, BULK_MAX_LINES + 1),
		as_dict=True,
	)
	if len(rows) > BULK_MAX_LINES:
		frappe.throw(_("{0} holds more than {1} items — too many for one bulk transfer.").format(from_warehouse, BULK_MAX_LINES))
	lines, skipped = _bulk_payloads([(r.item_code, flt(r.actual_qty), None) for r in rows], from_warehouse, to_warehouse)
	return {"lines": lines, "skipped": skipped}


def _sheet_rows(filename, content):
	name = (filename or "").lower()
	if name.endswith(".xlsx"):
		from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

		return read_xlsx_file_from_attached_file(fcontent=content) or []
	if name.endswith(".csv"):
		from frappe.utils.csvutils import read_csv_content

		return read_csv_content(content) or []
	frappe.throw(_("Upload an .xlsx or .csv file."))


def _resolve_codes(codes):
	"""{code: (item_code, barcode_uom|None)} via Item Barcode → ISBN → item code, batched."""
	found = {}
	codes = [c for c in dict.fromkeys(codes) if c]
	for part in _chunks(codes):
		for r in frappe.db.sql(
			"select barcode, parent, uom from `tabItem Barcode` where barcode in %s", (tuple(part),), as_dict=True
		):
			found.setdefault(r.barcode, (r.parent, r.uom or None))
	rest = [c for c in codes if c not in found]
	if rest and frappe.db.has_column("Item", "custom_isbn_barcode"):
		for part in _chunks(rest):
			for r in frappe.db.sql(
				"select custom_isbn_barcode, name from `tabItem` where custom_isbn_barcode in %s", (tuple(part),), as_dict=True
			):
				found.setdefault(r.custom_isbn_barcode, (r.name, None))
	rest = [c for c in codes if c not in found]
	for part in _chunks(rest):
		for r in frappe.db.sql("select name from `tabItem` where name in %s", (tuple(part),), as_dict=True):
			found.setdefault(r.name, (r.name, None))
	return found


def _cell(v):
	if v is None:
		return ""
	if isinstance(v, float) and v.is_integer():
		v = int(v)  # Excel turns 9781234567897 into 9.781234567897e12
	return str(v).strip()


@frappe.whitelist(methods=["POST"])
def parse_sheet(filename, content, from_warehouse, to_warehouse=None):
	"""Excel/CSV upload. Column A = barcode / ISBN / item code, B = qty,
	C = unit (optional). A first row that is not a number in B is a header;
	headers named code/barcode/isbn/item, qty/quantity, uom/unit are honoured."""
	_guard()
	import base64

	try:
		raw = base64.b64decode(content or "", validate=False)
	except Exception:
		frappe.throw(_("Could not read the file."))
	if not raw:
		frappe.throw(_("The file is empty."))
	if len(raw) > MAX_UPLOAD_BYTES:
		frappe.throw(_("The file is larger than 3 MB."))
	rows = [[_cell(c) for c in (r or [])] for r in _sheet_rows(filename, raw)]
	rows = [r for r in rows if any(r)]
	if not rows:
		frappe.throw(_("No rows found in the file."))

	col = {"code": 0, "qty": 1, "uom": 2}
	start = 0
	first = [c.lower() for c in rows[0]]
	if len(rows[0]) < 2 or not re.match(r"^-?\d+(\.\d+)?$", rows[0][1] if len(rows[0]) > 1 else ""):
		start = 1
		for i, h in enumerate(first):
			if h in ("code", "barcode", "isbn", "item", "item code", "item_code", "isbn/barcode"):
				col["code"] = i
			elif h in ("qty", "quantity", "qnty"):
				col["qty"] = i
			elif h in ("uom", "unit"):
				col["uom"] = i
	data = rows[start:]
	if len(data) > BULK_MAX_LINES:
		frappe.throw(_("The file has {0} rows; at most {1}.").format(len(data), BULK_MAX_LINES))

	get = lambda r, k: r[col[k]] if col[k] < len(r) else ""  # noqa: E731
	found = _resolve_codes([get(r, "code") for r in data])
	wanted, skipped = [], []
	for n, r in enumerate(data, start=start + 1):
		code, qty, uom = get(r, "code"), flt(get(r, "qty")), get(r, "uom") or None
		if not code:
			skipped.append({"row": n, "item_code": "", "item_name": "", "qty": qty, "reason": _("No code in column A.")})
			continue
		if code not in found:
			skipped.append({"row": n, "item_code": code, "item_name": "", "qty": qty, "reason": _("Not found (barcode / ISBN / item code).")})
			continue
		if qty <= 0:
			skipped.append({"row": n, "item_code": code, "item_name": "", "qty": qty, "reason": _("No quantity.")})
			continue
		item_code, barcode_uom = found[code]
		wanted.append((item_code, qty, uom or barcode_uom))
	lines, more = _bulk_payloads(wanted, from_warehouse, to_warehouse) if wanted else ([], [])
	return {"rows": len(data), "lines": lines, "skipped": skipped + more}


def _bulk_key(ref):
	return frappe.cache.make_key(f"kgs_staff_bulk:{ref}")


# Plain Redis get/set (JSON), NOT frappe.cache.get_value/set_value: get_value
# remembers a miss in frappe.local.cache and set_value with an expiry writes
# Redis only, so a read after a write in the same request/job saw the old miss.
def _bulk_meta(ref):
	raw = frappe.cache.get(_bulk_key(ref))
	try:
		return json.loads(raw) if raw else {}
	except ValueError:
		return {}


def _save_bulk_meta(ref, meta):
	frappe.cache.set(_bulk_key(ref), json.dumps(meta, default=str), ex=14 * 86400)


def _bulk_transfers(ref):
	return frappe.db.sql(
		"""select se.name, se.docstatus, se.owner, se.remarks, count(d.name) as line_count
		from `tabStock Entry` se left join `tabStock Entry Detail` d on d.parent = se.name
		where se.purpose = 'Material Transfer' and se.remarks like %s
		group by se.name order by se.creation""",
		(f"%[Staff app · ref:{ref}#%",),
		as_dict=True,
	)


@frappe.whitelist(methods=["POST"])
def create_bulk_transfer(from_warehouse, to_warehouse, items, client_ref, remarks=None):
	"""More than MAX_LINES lines: validate everything now, then submit in the
	background as transfers of <= MAX_LINES lines. Stock Managers, outside shop hours."""
	_guard()
	if not _is_manager():
		raise frappe.PermissionError(_("Only a Stock Manager can move more than {0} lines at once.").format(MAX_LINES))
	if not _CLIENT_REF_RE.match(client_ref or ""):
		frappe.throw(_("Invalid request reference. Please reload the app."))
	if _bulk_meta(client_ref) or _bulk_transfers(client_ref):
		return {"ok": 1, "bulk": 1, "ref": client_ref, "already": 1}
	if _in_shop_hours():
		frappe.throw(_("Big transfers run only outside shop hours (before 10:30 or after 19:30), so the tills stay fast."))

	company, lines, problems = _validate_transfer(from_warehouse, to_warehouse, items, BULK_MAX_LINES)
	if problems:
		return {"ok": 0, "problems": problems}
	chunks = [
		[{"item_code": l.item_code, "qty": l.qty, "uom": l.uom} for l in lines[i : i + MAX_LINES]]
		for i in range(0, len(lines), MAX_LINES)
	]
	meta = {
		"ref": client_ref, "user": frappe.session.user, "from_warehouse": from_warehouse,
		"to_warehouse": to_warehouse, "parts": len(chunks), "lines": len(lines), "done": 0,
		"state": "queued", "error": "", "queued_at": str(now_datetime()),
	}
	_save_bulk_meta(client_ref, meta)
	frappe.enqueue(
		"trustbit_school_book_seller.staff_app.api.run_bulk_transfer",
		queue="long",
		timeout=300 + 240 * len(chunks),
		job_id=f"kgs_staff_bulk::{client_ref}",
		deduplicate=True,
		enqueue_after_commit=True,
		ref=client_ref,
		from_warehouse=from_warehouse,
		to_warehouse=to_warehouse,
		chunks=chunks,
		remarks=remarks,
	)
	return {"ok": 1, "bulk": 1, "ref": client_ref, "parts": len(chunks), "lines": len(lines)}


def run_bulk_transfer(ref, from_warehouse, to_warehouse, chunks, remarks=None):
	"""Background (long queue, runs as the Stock Manager who started it). One
	transfer per chunk, committed one by one; stops at the first part that can
	no longer be moved (stock changed since the check) and says why."""
	meta = _bulk_meta(ref) or {"ref": ref, "parts": len(chunks)}
	n = len(chunks)

	def save(**kw):
		meta.update(kw)
		_save_bulk_meta(ref, meta)

	save(state="running", started_at=str(now_datetime()))
	for i, chunk in enumerate(chunks, start=1):
		tag = _BULK_TAG.format(ref, i, n)
		if _existing_transfer(frappe.session.user, tag):
			save(done=i)
			continue
		try:
			company, lines, problems = _validate_transfer(from_warehouse, to_warehouse, chunk)
			if problems:
				frappe.db.rollback()
				p = problems[0]
				save(state="stopped", error=_("Part {0}/{1}, {2}: {3} ({4} line(s) affected)").format(
					i, n, p["item_code"], p["message"], len(problems)))
				return
			_make_entry(company, from_warehouse, to_warehouse, lines, tag, remarks)
			frappe.db.commit()
			save(done=i)
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(title="Staff app bulk transfer stopped", message=f"ref={ref} part={i}/{n}\n{frappe.get_traceback()}")
			save(state="stopped", error=_("Part {0}/{1}: {2}").format(i, n, str(e)[:300]))
			return
	save(state="done", finished_at=str(now_datetime()))


@frappe.whitelist(methods=["POST"])
def bulk_status(ref):
	_guard()
	if not _CLIENT_REF_RE.match(ref or ""):
		frappe.throw(_("Invalid reference."))
	meta = _bulk_meta(ref)
	rows = _bulk_transfers(ref)
	if meta.get("user") and meta["user"] != frappe.session.user and not _is_manager():
		raise frappe.PermissionError(_("Not your transfer."))
	transfers = []
	for r in rows:
		m = re.search(r"ref:[^#\]]+#(\d+)/(\d+)\]", r.remarks or "")
		transfers.append({"name": r.name, "docstatus": r.docstatus, "line_count": r.line_count,
			"part": cint(m.group(1)) if m else 0, "parts": cint(m.group(2)) if m else 0})
	parts = meta.get("parts") or (transfers[0]["parts"] if transfers else 0)
	state = meta.get("state") or ("done" if parts and len(transfers) >= parts else "unknown")
	return {
		"ref": ref, "state": state, "error": meta.get("error") or "", "parts": parts, "done": len(transfers),
		"lines": meta.get("lines"), "from_warehouse": meta.get("from_warehouse"), "to_warehouse": meta.get("to_warehouse"),
		"transfers": transfers,
	}
