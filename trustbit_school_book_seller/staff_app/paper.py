# Copyright (c) 2026, Trustbit Software and contributors
# KGS Staff app — Order from Paper: a photo / PDF of a supplier's quotation,
# price list or order list (or a school's book list) → a DRAFT Purchase Order
# (optionally sent into the "Purchase Order Approval" workflow) or a DRAFT
# Sales Order. Plan: KGS/PLAN_order_from_paper.md. Nothing is ever submitted.
#
# Flow: upload_paper → background read job (paper_read: AI; paper_match:
# our items) → check screen (get_paper / update_lines / set_party) →
# save_order (inserts AS THE USER, attaches the pages, learns the confirmed
# lines as "remembered names" = Party Item Alias).
#
# Every endpoint is POST-only and re-checks role, kill switches and rate limit.
# Purchase side: Purchase User / Purchase Manager; sales side: Sales User /
# Sales Manager (and only while "Sales Orders from Paper" is on). Settings:
# System Manager / Shop Owner. The AI key never leaves site_config.

import base64
import binascii
import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from trustbit_school_book_seller.staff_app import paper_match as pm
from trustbit_school_book_seller.staff_app import paper_read as pr
from trustbit_school_book_seller.staff_app.api import (
	_CLIENT_REF_RE,
	PAPER_PO_ROLES,
	PAPER_SETTINGS_ROLES,
	PAPER_SO_ROLES,
	_rate_limit,
	app_enabled,
)
from trustbit_school_book_seller.trustbit_school_book.doctype.party_item_alias.party_item_alias import (
	alias_name,
	can_edit,
)

PURPOSES = {
	"Purchase Order": {"party_type": "Supplier", "roles": PAPER_PO_ROLES, "managers": ("Purchase Manager", "System Manager", "Shop Owner")},
	"Sales Order": {"party_type": "Customer", "roles": PAPER_SO_ROLES, "managers": ("Sales Manager", "System Manager", "Shop Owner")},
}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # all pages together, after decoding
MAX_PDF_BYTES = 10 * 1024 * 1024
DEFAULT_NEEDED_DAYS = 7
JOB_TIMEOUT = 600
RATE_WARN = 0.20  # paper rate vs our last purchase rate
NAME_WORDS_IGNORED = {"BOOK", "BOOKS", "AGENCY", "AGENCIES", "STORE", "STORES", "DISTRIBUTOR", "DISTRIBUTORS", "PVT", "LTD",
	"PRIVATE", "LIMITED", "AND", "CO", "COMPANY", "ENTERPRISES", "ENTERPRISE", "TRADERS", "SHOP", "HOUSE", "CENTRE", "CENTER",
	"PUBLISHERS", "PUBLICATION", "PUBLICATIONS", "SCHOOL", "THE", "M/S", "MS", "SONS", "BROTHERS", "BROS"}
WORKFLOW_ACTION = "Send for Approval"


# ── access ───────────────────────────────────────────────────────────────────


def _roles(user=None):
	return set(frappe.get_roles(user))


def can_make(purpose, settings=None, roles=None):
	settings = settings or pr.get_settings()
	roles = roles if roles is not None else _roles()
	if not settings.enabled or purpose not in PURPOSES:
		return False
	if purpose == "Sales Order" and not settings.so_enabled:
		return False
	return bool(roles & set(PURPOSES[purpose]["roles"]))


def _signed_in():
	if frappe.session.user in (None, "", "Guest"):
		raise frappe.PermissionError(_("Please sign in again."))
	if not app_enabled():
		raise frappe.PermissionError(_("The staff app is switched off. Please use the ERP."))


def _guard(purpose=None):
	_signed_in()
	settings = pr.get_settings()
	if not settings.enabled:
		raise frappe.PermissionError(_("Order from paper is switched off."))
	if purpose:
		if purpose not in PURPOSES:
			frappe.throw(_("Unknown order type."))
		if purpose == "Sales Order" and not settings.so_enabled:
			raise frappe.PermissionError(_("Sales Orders from paper are not switched on yet."))
		if not can_make(purpose, settings):
			raise frappe.PermissionError(
				_("Making a Purchase Order needs the Purchase User role.") if purpose == "Purchase Order"
				else _("Making a Sales Order needs the Sales User role."))
	elif not any(can_make(p, settings) for p in PURPOSES):
		raise frappe.PermissionError(_("Order from paper needs the Purchase User or Sales User role."))
	_rate_limit()
	return settings


def _guard_settings():
	_signed_in()
	if not _roles() & set(PAPER_SETTINGS_ROLES):
		raise frappe.PermissionError(_("Only a System Manager or Shop Owner can change these settings."))
	_rate_limit()


def _is_paper_manager(purpose):
	return bool(_roles() & set(PURPOSES[purpose]["managers"]))


def boot_info():
	s = pr.get_settings()
	roles = _roles()
	names = roles & {"Purchase Manager", "Sales Manager", "System Manager"}
	return {
		"enabled": s.enabled,
		"po": 1 if can_make("Purchase Order", s, roles) else 0,
		"so": 1 if can_make("Sales Order", s, roles) else 0,
		"names": 1 if s.enabled and names else 0,
		"settings": 1 if roles & set(PAPER_SETTINGS_ROLES) else 0,
		"ready": 1 if pr.provider_ready(s) else 0,
		"max_photos": pr.MAX_PHOTOS,
		"max_pages": pr.MAX_PAGES,
		"max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
	}


# ── small helpers ────────────────────────────────────────────────────────────


def _company():
	return frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")


def _load(name, lock=False):
	if not name or not frappe.db.exists("Order Paper", name):
		frappe.throw(_("Paper {0} not found.").format(name or ""))
	if lock:
		frappe.db.sql("select name from `tabOrder Paper` where name = %s for update", name)
	return frappe.get_doc("Order Paper", name)


def _state(paper):
	return pr._json(paper.lines_json, None) or {"lines": []}


def _pages_used(settings):
	return pr.month_usage(settings)["pages"]


def _pages_left(settings):
	limit = pr.page_limit(settings)
	if not limit:
		return 10**6
	return limit - _pages_used(settings)


def _check_page_limit(settings, pages):
	limit = pr.page_limit(settings)
	if not limit:
		return
	used = _pages_used(settings)
	if used + pages > limit:
		frappe.throw(
			_("This month's limit of {0} pages is reached ({1} used, this paper needs {2}). Ask the owner to raise it in Settings.").format(
				limit, used, pages),
			title=_("Monthly limit"),
		)


def _party_name(party_type, party):
	if not party:
		return ""
	field = "supplier_name" if party_type == "Supplier" else "customer_name"
	return frappe.db.get_value(party_type, party, field) or party


def _party_ok(party_type, party):
	row = frappe.db.get_value(party_type, party, ["name", "disabled"], as_dict=True)
	if not row:
		frappe.throw(_("{0} {1} not found.").format(_(party_type), party))
	if cint(row.disabled):
		frappe.throw(_("{0} {1} is disabled.").format(_(party_type), party))
	return row.name


def _warehouses(company):
	rows = frappe.get_list(
		"Warehouse",
		filters={"is_group": 0, "disabled": 0, "company": company},
		fields=["name", "warehouse_type"],
		order_by="warehouse_name asc",
		limit_page_length=500,
	)
	return [r.name for r in rows if (r.warehouse_type or "") != "Transit"]


def _school_field(doctype):
	return frappe.db.has_column(doctype, "custom_school_name")


# ── upload ───────────────────────────────────────────────────────────────────


def _decode_files(files):
	"""[{name, data(base64)}] → [(kind, bytes, ext)] after checking the real type,
	the page count and the size. Photos are re-encoded (rotation applied, ≤ 2000 px)."""
	if isinstance(files, str):
		files = json.loads(files or "[]")
	if not isinstance(files, list) or not files:
		frappe.throw(_("Add a photo or a PDF of the paper first."))
	if len(files) > pr.MAX_PHOTOS:
		frappe.throw(_("Up to {0} photos per paper.").format(pr.MAX_PHOTOS))
	out, total = [], 0
	for f in files:
		data = (f or {}).get("data") if isinstance(f, dict) else None
		if not data or not isinstance(data, str):
			frappe.throw(_("A file was empty. Add it again."))
		if len(data) > MAX_UPLOAD_BYTES * 4 // 3 + 16:
			frappe.throw(_("The paper is larger than {0} MB.").format(MAX_UPLOAD_BYTES // (1024 * 1024)))
		try:
			raw = base64.b64decode(data, validate=True)
		except (binascii.Error, ValueError):
			frappe.throw(_("A file could not be read. Add it again."))
		total += len(raw)
		if total > MAX_UPLOAD_BYTES:
			frappe.throw(_("The paper is larger than {0} MB.").format(MAX_UPLOAD_BYTES // (1024 * 1024)))
		kind = pr.sniff(raw)
		if kind == "pdf":
			if len(raw) > MAX_PDF_BYTES:
				frappe.throw(_("The PDF is larger than {0} MB.").format(MAX_PDF_BYTES // (1024 * 1024)))
			out.append(("pdf", raw, "pdf"))
		elif kind in ("jpeg", "png", "webp"):
			try:
				jpeg, _w, _h = pr.normalise_image(raw)
			except pr.PaperReadError as e:
				frappe.throw(e.staff_message)
			out.append(("image", jpeg, "jpg"))
		else:
			frappe.throw(_("Only photos (JPG, PNG) and PDF files can be read."))
	kinds = {k for k, _b, _e in out}
	if "pdf" in kinds and len(out) > 1:
		frappe.throw(_("Send one PDF, or photos — not both, and only one PDF per paper."))
	if "pdf" in kinds:
		try:
			pages = pr.pdf_pages(out[0][1])
		except pr.PaperReadError as e:
			frappe.throw(e.staff_message)
		if pages < 1:
			frappe.throw(_("This PDF has no pages."))
		if pages > pr.MAX_PAGES:
			frappe.throw(_("This PDF has {0} pages. Up to {1} pages per paper — split it.").format(pages, pr.MAX_PAGES))
	else:
		pages = len(out)
	return out, pages


@frappe.whitelist(methods=["POST"])
def upload_paper(purpose, files, client_ref, copies=None):
	settings = _guard(purpose)
	user = frappe.session.user
	if not _CLIENT_REF_RE.match(client_ref or ""):
		frappe.throw(_("Invalid request reference. Please reload the app."))
	existing = frappe.db.get_value("Order Paper", {"client_ref": client_ref, "owner": user}, "name")
	if existing:
		return {"name": existing, "already": 1}
	lock_key = frappe.cache.make_key(f"kgs_paper_up_lock:{user}:{client_ref}")
	if not frappe.cache.set(lock_key, 1, ex=180, nx=True):
		frappe.throw(_("This paper is already being uploaded. Please wait a moment."))
	try:
		return _upload(settings, purpose, files, client_ref, copies)
	finally:
		frappe.cache.delete(lock_key)


def _upload(settings, purpose, files, client_ref, copies):
	if not pr.provider_ready(settings):
		frappe.throw(_("The AI service is not set up yet. Ask the office."), title=_("Not ready"))

	parts, pages = _decode_files(files)
	_check_page_limit(settings, pages)
	company = _company()
	if not company:
		frappe.throw(_("No default company is set for your user."))

	paper = frappe.get_doc({
		"doctype": "Order Paper",
		"purpose": purpose,
		"status": "Reading",
		"company": company,
		"party_type": PURPOSES[purpose]["party_type"],
		"client_ref": client_ref,
		"page_count": pages,
		"file_kind": "PDF" if parts[0][0] == "pdf" else "Photos",
		"default_copies": max(0, min(cint(copies), 10000)) or None,
	})
	paper.insert(ignore_permissions=True)
	for i, (_kind, data, ext) in enumerate(parts, start=1):
		frappe.get_doc({
			"doctype": "File",
			"file_name": f"{paper.name}-{i}.{ext}",
			"content": data,
			"is_private": 1,
			"attached_to_doctype": "Order Paper",
			"attached_to_name": paper.name,
		}).insert(ignore_permissions=True)
	_enqueue_read(paper.name, None, "first")
	return {"name": paper.name}


def _enqueue_read(name, model, reason):
	frappe.enqueue(
		"trustbit_school_book_seller.staff_app.paper.run_read_job",
		queue="default",  # not "long": that queue carries the reports and bulk transfers
		timeout=JOB_TIMEOUT,
		job_id=f"kgs_paper_read::{name}",
		deduplicate=True,
		enqueue_after_commit=True,
		name=name,
		model=model,
		reason=reason,
	)


# ── the read job ─────────────────────────────────────────────────────────────


def run_read_job(name, model=None, reason="first"):
	paper = frappe.get_doc("Order Paper", name)
	if paper.status in ("Saved", "Discarded"):
		return
	settings = pr.get_settings()
	provider = pr.get_provider(settings)
	model = model or settings.ai_model
	usage = pr._json(paper.usage_json, [])
	old_state = _state(paper) if reason != "first" else None
	frappe.db.set_value("Order Paper", name, {"status": "Reading", "error": None}, update_modified=False)
	frappe.db.commit()

	status, error, state, data, used_model = "Failed", None, None, None, model
	try:
		blocks = pr.content_blocks(name)
		pages = cint(paper.page_count) or 1
		data, res = pr.read(provider, model, blocks)
		usage.append(pr.usage_entry(settings, res, reason, pages, provider.name))
		notes = []
		if reason == "first" and settings.auto_fallback and settings.fallback_model and settings.fallback_model != model:
			why = pr.looks_wrong(data)
			if why and _pages_left(settings) - pages >= 0:
				try:
					data2, res2 = pr.read(provider, settings.fallback_model, blocks)
					usage.append(pr.usage_entry(settings, res2, "fallback", pages, provider.name))
					if data2["lines"]:
						data, used_model = data2, settings.fallback_model
						notes.append(_("Read again with {0} because {1}.").format(_model_label(settings, used_model), why))
				except pr.PaperReadError as e:
					frappe.log_error(title=f"Order Paper {name}: fallback read failed", message=e.detail)
		if not data["lines"]:
			raise pr.PaperReadError(_("No item lines were found on this paper. Take a clearer photo of the whole page."), "0 lines")
		state = build_state(paper, data, settings, provider, usage, notes)
		if old_state:
			_carry_decisions(old_state, state)
		status = "Ready"
	except pr.PaperReadError as e:
		error = e.staff_message
		frappe.log_error(title=f"Order Paper {name}: read failed", message=f"{e.staff_message}\n{e.detail}")
	except Exception:
		error = _("Something went wrong while reading. Please try again.")
		frappe.log_error(title=f"Order Paper {name}: read crashed")

	# a discard (or save) while the job ran wins over the reading
	current = frappe.db.get_value("Order Paper", name, "status")
	values = {
		"usage_json": json.dumps(usage),
		"pages_read": sum(cint(u.get("pages")) for u in usage),
		"ai_input_tokens": sum(cint(u.get("input_tokens")) for u in usage),
		"ai_output_tokens": sum(cint(u.get("output_tokens")) for u in usage),
		"ai_cost_usd": round(sum(flt(u.get("usd")) for u in usage), 6),
		"ai_provider": provider.name,
	}
	if current not in ("Saved", "Discarded"):
		values.update({"status": status, "error": error})
		if state is not None:
			values.update({
				"lines_json": json.dumps(state),
				"ai_json": json.dumps(data),
				"ai_model": used_model,
				"state_version": cint(paper.state_version) + 1,
				"paper_party_text": data.get("party_name"),
				"paper_gstin": data.get("party_gstin"),
				"paper_no": data.get("paper_no"),
				"paper_date": data.get("paper_date"),
				"paper_kind": data.get("paper_kind"),
				"party": state.get("party") or None,
			})
	frappe.db.set_value("Order Paper", name, values)
	frappe.db.commit()


def _model_label(settings, model):
	p = settings.prices.get(model)
	return (p.label if p and p.label else model) or ""


def detect_party(party_type, data):
	"""(party, how, candidates): GSTIN → the party chosen last time for the same
	printed name → else none (top names offered; a person confirms)."""
	gstin, printed = data.get("party_gstin"), (data.get("party_name") or "").strip()
	party, how = None, ""
	if gstin and frappe.db.has_column(party_type, "gstin"):
		party = frappe.db.get_value(party_type, {"gstin": gstin, "disabled": 0}, "name")
		how = "gstin" if party else ""
	if not party and printed:
		party = frappe.db.sql(
			"""select p.party from `tabOrder Paper` p
			where p.party_type = %s and p.paper_party_text = %s and p.status = 'Saved' and ifnull(p.party, '') != ''
			order by p.modified desc limit 1""",
			(party_type, printed),
		)
		party = party[0][0] if party else None
		if party and cint(frappe.db.get_value(party_type, party, "disabled")):
			party = None
		how = "last_time" if party else ""
	cands = name_candidates(party_type, printed or data.get("school_or_class") or "")
	if not party and printed:
		same = [c for c in cands if _norm_name(c["title"]) == _norm_name(printed)]
		if len(same) == 1:  # printed name = our name exactly; the check screen still shows it to confirm
			party, how = same[0]["party"], "name"
	return party, how, cands


def _norm_name(s):
	return re.sub(r"[^A-Z0-9]+", " ", str(s or "").upper()).strip()


def name_candidates(party_type, printed, limit=3):
	words = [w for w in re.split(r"[^A-Za-z0-9]+", (printed or "").upper()) if len(w) >= 3 and w not in NAME_WORDS_IGNORED][:6]
	if not words:
		return []
	field = "supplier_name" if party_type == "Supplier" else "customer_name"
	conds = " or ".join([f"`{field}` like %(w{i})s or name like %(w{i})s" for i in range(len(words))])
	values = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
	rows = frappe.db.sql(
		f"select name, `{field}` as title from `tab{party_type}` where disabled = 0 and ({conds}) limit 60",
		values,
		as_dict=True,
	)
	scored = []
	for r in rows:
		t = (r.title or r.name).upper()
		hits = sum(1 for w in words if w in t)
		scored.append((hits / len(words), -len(t), r))
	scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
	return [{"party": r.name, "title": r.title or r.name, "score": round(s, 2)} for s, _l, r in scored[:limit] if s >= 0.5]


def build_state(paper, data, settings, provider, usage, notes):
	party_type = paper.party_type
	party, how, cands = detect_party(party_type, data)
	lines = data["lines"]
	discount_note = data.get("discount_note") or ""

	exact = pm.exact_layers(lines, party_type, party)
	need_fuzzy = [ln for ln in lines if ln["idx"] not in exact or exact[ln["idx"]]["how"] == "other_party"]
	fuzzy = {}
	if need_fuzzy:
		index = pm.load_index()
		for ln in need_fuzzy:
			cls = pm.class_of(ln.get("class_hint")) or pm.class_of(ln["text"])
			fuzzy[ln["idx"]] = index.search(ln["text"], line_class=cls, mrp=ln.get("mrp"))
		del index

	# AI double-check: only lines that stay amber/red and have a real choice
	ai = {}
	if settings.rerank:
		todo = [
			{"idx": ln["idx"], "text": ln["text"], "class_hint": pm.class_of(ln.get("class_hint")) or pm.class_of(ln["text"]),
				"mrp": ln.get("mrp"), "candidates": fuzzy[ln["idx"]]}
			for ln in lines
			if ln["idx"] not in exact and len(fuzzy.get(ln["idx"]) or []) >= 2
		]
		if todo:
			try:
				ai, res = pr.rerank(provider, settings.ai_model, todo)
				if res:
					usage.append(pr.usage_entry(settings, res, "double_check", 0, provider.name))
			except pr.PaperReadError as e:
				frappe.log_error(title=f"Order Paper {paper.name}: double-check failed", message=e.detail)
				ai = {}

	out_lines = []
	for ln in lines:
		base = dict(ln)
		base["paper_qty"] = ln.get("qty")  # as read; "qty" becomes the quantity we order
		base["line_class"] = pm.class_of(ln.get("class_hint")) or pm.class_of(ln["text"])
		base["paper_rate"] = pr.paper_rate(ln)
		base["paper_amount"] = pr.line_amount(ln)
		cs = fuzzy.get(ln["idx"]) or []
		base["fuzzy_pick"], base["ai_note"] = _fuzzy_pick(cs, ai.get(ln["idx"], "-"))
		if base["fuzzy_pick"] and cs and cs[0]["item_code"] != base["fuzzy_pick"]:
			cs = [c for c in cs if c["item_code"] == base["fuzzy_pick"]] + [c for c in cs if c["item_code"] != base["fuzzy_pick"]]
		base["candidates"] = cs
		out_lines.append(base)

	state = {
		"v": 1,
		"party": party,
		"party_how": how,
		"party_candidates": cands,
		"notes": notes,
		"discount_note": discount_note,
		"lines": out_lines,
	}
	compose_all(state, paper.purpose, party_type, cint(paper.default_copies), exact=exact)
	return state


def _fuzzy_pick(cands, ai_choice):
	"""(item_code | None, note). ai_choice: "-" = no AI answer, None = AI says none."""
	ok = [c for c in cands if not c["class_mismatch"]]
	if ai_choice is None:
		return None, "ai_none"
	if ai_choice != "-":
		c = next((c for c in ok if c["item_code"] == ai_choice), None)
		if c:
			return c["item_code"], "ai_pick" if cands and cands[0]["item_code"] != ai_choice else "ai_agrees"
	if ok and ok[0]["score"] >= pm.PRESELECT:
		return ok[0]["item_code"], ""
	return None, ""


def compose_all(state, purpose, party_type, copies, exact=None):
	"""(Re)compute item, colour and note of every line from the stored reading
	+ the party-dependent layers. A person's decision on a line is kept."""
	lines = state["lines"]
	if exact is None:
		exact = pm.exact_layers(lines, party_type, state.get("party"))
	codes = set()
	for ln in lines:
		hit = exact.get(ln["idx"])
		if hit:
			codes.add(hit["item_code"])
		if ln.get("fuzzy_pick"):
			codes.add(ln["fuzzy_pick"])
		if ln.get("by_person") and ln.get("item_code"):
			codes.add(ln["item_code"])
	info = pm.item_details(codes)
	for ln in lines:
		_compose(ln, exact.get(ln["idx"]), info, purpose, copies)


def _compose(ln, hit, info, purpose, copies):
	person = bool(ln.get("by_person"))
	if person and ln.get("item_code") in info:
		# keep the person's item / unit / qty; refresh only facts about the item
		_set_item(ln, info[ln["item_code"]], keep_uom=True)
		ln["colour"] = "green"
		return
	ln["how"], ln["note"], ln["alias"], ln["other_party"] = "none", "", None, None
	ln["problems"] = []
	item_code = None
	if hit and hit["how"] != "other_party":
		item_code = hit["item_code"]
		ln["how"] = hit["how"]
		ln["alias"] = hit.get("alias")
		ln["colour"] = "green"
	elif hit:
		item_code = hit["item_code"]
		ln["how"] = "other_party"
		ln["other_party"] = hit.get("other_party")
		ln["colour"] = "amber"
		ln["note"] = _("Used before for {0}").format(_party_name(hit.get("other_party_type"), hit.get("other_party")))
	elif ln.get("fuzzy_pick"):
		item_code = ln["fuzzy_pick"]
		ln["how"] = "fuzzy"
		ln["colour"] = "amber"
		ln["note"] = {"ai_pick": _("Picked by the AI double-check"), "ai_agrees": _("Best match, AI double-check agrees")}.get(
			ln.get("ai_note"), _("Best guess"))
	else:
		ln["colour"] = "red"
		ln["how"] = "none"
		ln["note"] = _("Not sure — choose the item or leave it out") if ln.get("candidates") else _("Not in our items")

	it = info.get(item_code) if item_code else None
	if item_code and not it:  # item deleted since
		ln["colour"], ln["note"], item_code = "red", _("Not in our items"), None
	if not it:
		for k in ("item_code", "item_name", "item_cls", "item_mrp", "stock_uom", "uom"):
			ln[k] = None
		ln["uoms"], ln["conversion_factor"], ln["unit_known"], ln["can_keep"] = [], 1, 1, 0
		ln["qty"] = _default_qty(ln, purpose, copies)
		return
	_set_item(ln, it, alias=hit if hit and hit.get("alias") else None)
	ln["qty"] = _default_qty(ln, purpose, copies)

	if ln["colour"] == "green":
		if it["disabled"]:
			ln["colour"], ln["note"] = "amber", _("This item is disabled — choose another")
		elif hit and hit.get("alias_mrp") and ln.get("mrp") and not pm.same_money(hit["alias_mrp"], ln["mrp"]):
			ln["colour"] = "amber"
			ln["note"] = _("MRP on the paper ₹{0}, ₹{1} when remembered — new edition?").format(
				_money(ln["mrp"]), _money(hit["alias_mrp"]))
		elif ln.get("line_class") and it["cls"] and ln["line_class"] != it["cls"]:
			ln["colour"] = "amber"
			ln["note"] = _("Class {0} item, paper says {1}").format(it["cls"], ln["line_class"])
		elif ln.get("unclear"):
			ln["colour"], ln["note"] = "amber", _("Hard to read on the paper — check the numbers")
		elif not ln["unit_known"]:
			ln["colour"], ln["note"] = "amber", _("Unit {0} on the paper — choose ours").format(ln.get("unit"))
	if ln["colour"] == "green" and purpose == "Purchase Order" and not ln.get("qty"):
		ln["colour"], ln["note"] = "amber", _("No quantity on the paper — enter it")


def _set_item(ln, it, alias=None, keep_uom=False):
	ln["item_code"] = it["item_code"]
	ln["item_name"] = it["item_name"]
	ln["item_cls"] = it["cls"]
	ln["item_mrp"] = it["mrp"]
	ln["stock_uom"] = it["stock_uom"]
	ln["uoms"] = it["uoms"]
	ln["last_purchase_rate"] = it["last_purchase_rate"]
	ln["can_keep"] = 0 if it["disabled"] else 1
	ln["class_mismatch"] = 1 if ln.get("line_class") and it["cls"] and ln["line_class"] != it["cls"] else 0
	if keep_uom and any(u["uom"] == ln.get("uom") for u in it["uoms"]):
		ln["conversion_factor"] = next(u["factor"] for u in it["uoms"] if u["uom"] == ln["uom"])
		ln["unit_known"] = 1
		return
	uom, factor, known = pm.pick_uom(it, ln.get("unit"), alias)
	ln["uom"], ln["conversion_factor"], ln["unit_known"] = uom, factor, 1 if known else 0


def _default_qty(ln, purpose, copies):
	"""A person's quantity, else the paper's, else "copies of each" (lists without quantities)."""
	if ln.get("qty_by_person"):
		return ln.get("qty")
	return ln.get("paper_qty") or copies or None


def _carry_decisions(old_state, new_state):
	"""After "Read again": keep what a person already decided on the same line."""
	def key(ln):
		return (pm.code_key(ln.get("code")), pm.match_key(ln.get("text")))

	old = {key(ln): ln for ln in old_state.get("lines") or [] if ln.get("by_person") or ln.get("decision")}
	for ln in new_state["lines"]:
		o = old.get(key(ln))
		if not o:
			continue
		for k in ("decision", "by_person", "qty_by_person", "item_code", "item_name", "item_cls", "item_mrp", "stock_uom",
				"uoms", "uom", "conversion_factor", "unit_known", "can_keep", "colour", "last_purchase_rate"):
			if k in o:
				ln[k] = o[k]
		if o.get("qty_by_person"):
			ln["qty"] = o.get("qty")
	if old_state.get("party") and not new_state.get("party"):
		new_state["party"] = old_state["party"]


def _money(v):
	return f"{flt(v):,.2f}".rstrip("0").rstrip(".") if flt(v) % 1 else f"{flt(v):,.0f}"


# ── check screen ─────────────────────────────────────────────────────────────


def _paper_payload(paper, settings=None):
	settings = settings or pr.get_settings()
	state = _state(paper)
	data = pr._json(paper.ai_json, {}) or {}
	files = [{"url": f.file_url, "kind": "pdf" if (f.file_url or "").lower().endswith(".pdf") else "image"}
		for f in pr.paper_files(paper.name)]
	purpose = paper.purpose
	party = state.get("party") or paper.party
	dup = _duplicate(paper, party) if paper.status == "Ready" else None
	models = [{"model": m, "label": p.label or m, "note": p.note or ""} for m, p in settings.prices.items()]
	out = {
		"name": paper.name, "purpose": purpose, "status": paper.status, "error": paper.error,
		"party_type": paper.party_type, "party": party, "party_title": _party_name(paper.party_type, party),
		"party_how": state.get("party_how") or "", "party_candidates": state.get("party_candidates") or [],
		"notes": state.get("notes") or [], "version": cint(paper.state_version),
		"paper": {
			"party_text": paper.paper_party_text, "gstin": paper.paper_gstin, "no": paper.paper_no, "date": paper.paper_date,
			"kind": paper.paper_kind, "school_or_class": data.get("school_or_class"), "discount_note": data.get("discount_note"),
			"items_total": data.get("items_total"), "grand_total": data.get("grand_total"), "total_qty": data.get("total_qty"),
			"warnings": data.get("warnings") or [], "truncated": data.get("truncated") or 0,
		},
		"lines": state.get("lines") or [],
		"files": files, "page_count": paper.page_count, "copies": cint(paper.default_copies),
		"created_doctype": paper.created_doctype, "created_doc": paper.created_doc,
		"created_status": frappe.db.get_value(paper.created_doctype, paper.created_doc, "workflow_state")
			if paper.created_doc and paper.created_doctype == "Purchase Order" and frappe.db.has_column("Purchase Order", "workflow_state") else None,
		"saved_by": paper.saved_by, "saved_by_name": frappe.utils.get_fullname(paper.saved_by) if paper.saved_by else None,
		"saved_on": str(paper.saved_on or ""), "owner": paper.owner, "owner_name": frappe.utils.get_fullname(paper.owner),
		"creation": str(paper.creation),
		"model": paper.ai_model, "model_label": _model_label(settings, paper.ai_model),
		"models": models, "duplicate": dup,
		"can_save": 1 if can_make(purpose, settings) else 0,
		"ready": 1 if pr.provider_ready(settings) else 0,
		# the check screen and the "sent for approval" screen both name the approvers
		"owners": _owner_names() if purpose == "Purchase Order" and paper.status in ("Ready", "Saved") else [],
	}
	if paper.status == "Ready":
		company = paper.company
		whs = _warehouses(company)
		default_wh = frappe.db.get_single_value("Stock Settings", "default_warehouse")
		out["save"] = {
			"warehouses": whs,
			"warehouse": default_wh if default_wh in whs else (whs[0] if whs else None),
			"needed_by": str(add_days(nowdate(), DEFAULT_NEEDED_DAYS)),
			"school_field": 1 if _school_field(purpose) else 0,
			"approval": 1 if purpose == "Purchase Order" and _approval_active() else 0,
			"can_send": 1 if purpose == "Purchase Order" and _approval_active() and "Purchase User" in _roles() else 0,
		}
	return out


def _approval_active():
	from frappe.model.workflow import get_workflow_name

	from trustbit_school_book_seller.po_approval import WORKFLOW

	return get_workflow_name("Purchase Order") == WORKFLOW


def _owner_names():
	from trustbit_school_book_seller.po_approval import SHOP_OWNER

	users = frappe.get_all("Has Role", filters={"role": SHOP_OWNER, "parenttype": "User"}, pluck="parent")
	enabled = frappe.get_all("User", filters={"name": ["in", users or [""]], "enabled": 1, "user_type": "System User"},
		fields=["first_name", "full_name"])
	return sorted({(u.first_name or u.full_name or "").strip() for u in enabled if (u.first_name or u.full_name)})


def _duplicate(paper, party):
	"""The order made earlier from a paper with the same party + paper no."""
	if not party or not paper.paper_no:
		return None
	row = frappe.db.sql(
		"""select name, created_doctype, created_doc, saved_on from `tabOrder Paper`
		where party_type = %s and party = %s and paper_no = %s and status = 'Saved' and name != %s
		order by saved_on desc limit 1""",
		(paper.party_type, party, paper.paper_no, paper.name),
		as_dict=True,
	)
	if not row:
		return None
	r = row[0]
	return {"paper": r.name, "doctype": r.created_doctype, "doc": r.created_doc, "saved_on": str(r.saved_on or "")}


@frappe.whitelist(methods=["POST"])
def get_paper(name, light=0):
	paper = _load(name)
	settings = _guard(paper.purpose)
	if cint(light) and paper.status in ("Uploaded", "Reading"):
		return {"name": paper.name, "status": paper.status, "purpose": paper.purpose, "page_count": paper.page_count}
	return _paper_payload(paper, settings)


def _check_version(paper, version):
	if version is not None and cint(version) != cint(paper.state_version):
		return {"conflict": 1, "paper": _paper_payload(paper)}
	return None


def _editable(paper):
	if paper.status != "Ready":
		frappe.throw(_("This paper is {0} and cannot be changed.").format(_(paper.status).lower()))


@frappe.whitelist(methods=["POST"])
def set_party(name, party, version=None):
	paper = _load(name, lock=True)
	_guard(paper.purpose)
	_editable(paper)
	conflict = _check_version(paper, version)
	if conflict:
		return conflict
	party = _party_ok(paper.party_type, party)
	state = _state(paper)
	state["party"] = party
	state["party_how"] = "chosen"
	compose_all(state, paper.purpose, paper.party_type, cint(paper.default_copies))
	paper.db_set({"lines_json": json.dumps(state), "party": party, "state_version": cint(paper.state_version) + 1})
	return _paper_payload(paper)


@frappe.whitelist(methods=["POST"])
def update_lines(name, changes, version=None, copies=None):
	"""changes: [{idx, decision?: "ok" | "left" | null, item_code?, uom?, qty?}]
	Returns {"version", "lines": [the changed lines]} or {"conflict": 1, "paper"}."""
	paper = _load(name, lock=True)
	_guard(paper.purpose)
	_editable(paper)
	conflict = _check_version(paper, version)
	if conflict:
		return conflict
	if isinstance(changes, str):
		changes = json.loads(changes or "[]")
	state = _state(paper)
	by_idx = {ln["idx"]: ln for ln in state["lines"]}
	touched = set()

	if copies is not None:
		c = cint(copies)
		if c < 0 or c > 10000:
			frappe.throw(_("Copies must be between 0 and 10000."))
		paper.default_copies = c or None
		for ln in state["lines"]:
			if not ln.get("qty_by_person") and not ln.get("paper_qty"):
				ln["qty"] = c or None
				touched.add(ln["idx"])

	new_items = {str(ch.get("item_code")) for ch in changes or [] if isinstance(ch, dict) and ch.get("item_code")}
	info = pm.item_details(new_items) if new_items else {}
	for ch in (changes or [])[:500]:
		if not isinstance(ch, dict):
			continue
		ln = by_idx.get(cint(ch.get("idx")))
		if not ln:
			continue
		touched.add(ln["idx"])
		if ch.get("item_code"):
			it = info.get(str(ch["item_code"]))
			if not it:
				frappe.throw(_("Item {0} not found.").format(ch["item_code"]))
			if it["disabled"]:
				frappe.throw(_("{0} is disabled. Choose another item.").format(it["item_name"]))
			if it["has_variants"]:
				frappe.throw(_("{0} is a template item. Choose the actual item.").format(it["item_name"]))
			_set_item(ln, it)
			ln["by_person"], ln["decision"], ln["colour"] = 1, "ok", "green"
		if "uom" in ch and ch["uom"]:
			u = next((u for u in ln.get("uoms") or [] if u["uom"] == ch["uom"]), None)
			if not u:
				frappe.throw(_("Unit {0} is not set up for {1}.").format(ch["uom"], ln.get("item_name") or ""))
			ln["uom"], ln["conversion_factor"], ln["unit_known"] = u["uom"], u["factor"], 1
		if "qty" in ch:
			q = flt(ch["qty"]) if ch["qty"] not in (None, "") else None
			if q is not None and (q <= 0 or q > 1_000_000):
				frappe.throw(_("Quantity must be more than 0."))
			if q is not None:
				u = next((u for u in ln.get("uoms") or [] if u["uom"] == ln.get("uom")), None)
				if u and u["whole"] and q != int(q):
					frappe.throw(_("{0} is counted in whole numbers.").format(ln.get("uom")))
			ln["qty"], ln["qty_by_person"] = q, 1
		if "decision" in ch:
			d = ch["decision"]
			if d not in (None, "ok", "left"):
				frappe.throw(_("Unknown choice."))
			if d == "ok":
				if not ln.get("item_code"):
					frappe.throw(_("Choose the item first."))
				if not ln.get("can_keep"):
					frappe.throw(_("{0} is disabled. Choose another item.").format(ln.get("item_name") or ""))
				# the person confirmed THIS item: a later supplier change must not swap it
				ln["by_person"], ln["colour"] = 1, "green"
			ln["decision"] = d
			if d is None and ln.get("by_person") and not ch.get("item_code"):
				# undo: back to what the paper matched by itself
				ln["by_person"] = 0
				compose_all({"lines": [ln], "party": state.get("party")}, paper.purpose, paper.party_type, cint(paper.default_copies))
	version = cint(paper.state_version) + 1
	paper.db_set({"lines_json": json.dumps(state), "state_version": version, "default_copies": paper.default_copies})
	return {"version": version, "lines": [by_idx[i] for i in sorted(touched)]}


@frappe.whitelist(methods=["POST"])
def search_parties(purpose, txt=""):
	_guard(purpose)
	party_type = PURPOSES[purpose]["party_type"]
	field = "supplier_name" if party_type == "Supplier" else "customer_name"
	extra = "customer_group" if party_type == "Customer" else ("gstin" if frappe.db.has_column("Supplier", "gstin") else "supplier_group")
	words = [w for w in re.split(r"\s+", (txt or "").strip()) if w][:5]
	conds, values = [], {}
	for i, w in enumerate(words):
		values[f"w{i}"] = f"%{w}%"
		conds.append(f"(name like %(w{i})s or `{field}` like %(w{i})s)")
	where = (" and " + " and ".join(conds)) if conds else ""
	order = "order by modified desc" if not conds else f"order by `{field}` asc"
	return frappe.db.sql(
		f"select name as party, `{field}` as title, `{extra}` as extra from `tab{party_type}` where disabled = 0{where} {order} limit 20",
		values,
		as_dict=True,
	)


@frappe.whitelist(methods=["POST"])
def search_items(txt):
	"""The choose-item sheet: every word in the item name, code or ISBN; with the
	class and MRP so a person can tell twins apart. Works for purchase and sales staff."""
	_guard()
	words = [w for w in re.split(r"\s+", (txt or "").strip()) if w][:6]
	if not words or len("".join(words)) < 2:
		return []
	has_isbn = frappe.db.has_column("Item", "custom_isbn_barcode")
	has_class = frappe.db.has_column("Item", "custom_class")
	conds, values = [], {}
	for i, w in enumerate(words):
		values[f"w{i}"] = f"%{w}%"
		isbn = f" or i.custom_isbn_barcode like %(w{i})s" if has_isbn else ""
		conds.append(f"(i.item_name like %(w{i})s or i.name like %(w{i})s{isbn})")
	rows = frappe.db.sql(
		f"""select i.name as item_code, i.item_name, i.stock_uom, {"i.custom_class" if has_class else "null"} as cls
		from `tabItem` i
		where i.disabled = 0 and i.has_variants = 0 and {" and ".join(conds)}
		order by i.item_name asc limit 20""",
		values,
		as_dict=True,
	)
	prices = pm.selling_prices([r.item_code for r in rows])
	for r in rows:
		r["cls"] = pm.item_class(r.cls, r.item_name)
		r["mrp"] = prices.get(r.item_code) or pm.price_in_name(r.item_name)
	return rows


@frappe.whitelist(methods=["POST"])
def search_schools(txt=""):
	_guard()
	if not frappe.db.exists("DocType", "School"):
		return []
	filters = {}
	if txt:
		filters = [["School", "name", "like", f"%{txt}%"]]
	return frappe.get_list("School", filters=filters, fields=["name"], order_by="name asc", limit_page_length=20, pluck="name")


@frappe.whitelist(methods=["POST"])
def reread(name, model=None):
	paper = _load(name, lock=True)
	settings = _guard(paper.purpose)
	if paper.status not in ("Ready", "Failed"):
		frappe.throw(_("This paper is {0}.").format(_(paper.status).lower()))
	model = (model or "").strip() or settings.ai_model
	if model not in settings.prices:
		frappe.throw(_("Model {0} is not in the price list of Settings.").format(model))
	if not pr.provider_ready(settings):
		frappe.throw(_("The AI service is not set up yet. Ask the office."))
	_check_page_limit(settings, cint(paper.page_count) or 1)
	paper.db_set({"status": "Reading", "error": None})
	_enqueue_read(paper.name, model, "reread")
	return {"name": paper.name, "status": "Reading"}


@frappe.whitelist(methods=["POST"])
def discard_paper(name):
	paper = _load(name, lock=True)
	_guard(paper.purpose)
	if paper.status == "Saved":
		frappe.throw(_("This paper already became {0}.").format(paper.created_doc))
	if paper.owner != frappe.session.user and not _is_paper_manager(paper.purpose):
		frappe.throw(_("Only {0} or a manager can discard this paper.").format(frappe.utils.get_fullname(paper.owner)))
	paper.db_set("status", "Discarded")
	return {"name": paper.name, "status": "Discarded"}


@frappe.whitelist(methods=["POST"])
def my_papers(scope="mine", days=30, purpose=None):
	settings = _guard()
	allowed = [p for p in PURPOSES if can_make(p, settings)]
	if purpose in allowed:
		allowed = [purpose]
	filters = {"purpose": ["in", allowed], "creation": [">=", str(add_days(nowdate(), -max(1, min(cint(days) or 30, 400))))]}
	if scope != "all" or not any(_is_paper_manager(p) for p in allowed):
		filters["owner"] = frappe.session.user
	rows = frappe.get_all(
		"Order Paper",
		filters=filters,
		fields=["name", "purpose", "status", "party_type", "party", "paper_party_text", "paper_no", "created_doctype",
			"created_doc", "creation", "owner", "page_count"],
		order_by="creation desc",
		limit_page_length=100,
	)
	for r in rows:
		r["party_title"] = _party_name(r.party_type, r.party) if r.party else (r.paper_party_text or "")
		r["owner_name"] = frappe.utils.get_fullname(r.owner)
		r["creation"] = str(r.creation)
	return rows


# ── save ─────────────────────────────────────────────────────────────────────


def _lines_to_save(state, purpose):
	keep, left, pending = [], [], []
	for ln in state["lines"]:
		d = ln.get("decision")
		if d == "left":
			left.append(ln)
		elif d == "ok" or (ln.get("colour") == "green" and d is None and ln.get("can_keep") and ln.get("item_code")):
			keep.append(ln)
		elif ln.get("colour") == "red" and not ln.get("by_person"):
			left.append(ln)
		else:
			pending.append(ln)
	return keep, left, pending


def _qty_problem(ln):
	if not flt(ln.get("qty")):
		return _("enter the quantity")
	u = next((u for u in ln.get("uoms") or [] if u["uom"] == ln.get("uom")), None)
	if not u:
		return _("choose the unit")
	if u["whole"] and flt(ln["qty"]) != int(flt(ln["qty"])):
		return _("{0} is counted in whole numbers").format(ln["uom"])
	return ""


@frappe.whitelist(methods=["POST"])
def save_order(name, client_ref, send_for_approval=0, warehouse=None, needed_by=None, school=None,
		rate_mode="paper", allow_duplicate=0, version=None):
	paper = _load(name, lock=True)
	settings = _guard(paper.purpose)
	purpose = paper.purpose
	if paper.created_doc:  # idempotent: a retried tap returns what was made
		return _saved_response(paper, already=1)
	if paper.status != "Ready":
		frappe.throw(_("This paper is {0}.").format(_(paper.status).lower()))
	if not _CLIENT_REF_RE.match(client_ref or ""):
		frappe.throw(_("Invalid request reference. Please reload the app."))
	conflict = _check_version(paper, version)
	if conflict:
		return conflict
	lock_key = frappe.cache.make_key(f"kgs_paper_save_lock:{paper.name}")
	if not frappe.cache.set(lock_key, 1, ex=180, nx=True):
		frappe.throw(_("This paper is being saved right now. Please wait a moment."))
	try:
		return _save(paper, settings, purpose, send_for_approval, warehouse, needed_by, school, rate_mode, allow_duplicate)
	finally:
		frappe.cache.delete(lock_key)


def _save(paper, settings, purpose, send_for_approval, warehouse, needed_by, school, rate_mode, allow_duplicate):
	state = _state(paper)
	party = state.get("party")
	if not party:
		frappe.throw(_("Choose the {0} first.").format(_("supplier") if purpose == "Purchase Order" else _("customer")))
	party = _party_ok(paper.party_type, party)
	keep, left, pending = _lines_to_save(state, purpose)
	if pending:
		frappe.throw(_("Check {0} more line(s) first.").format(len(pending)))
	if not keep:
		frappe.throw(_("No lines to save — every line was left out."))
	bad = [(ln, _qty_problem(ln)) for ln in keep]
	bad = [(ln, p) for ln, p in bad if p]
	if bad:
		ln, p = bad[0]
		frappe.throw(_("Line {0} ({1}): {2}.").format(ln["idx"], ln.get("item_name") or ln.get("text"), p))
	dup = _duplicate(paper, party)
	if dup and not cint(allow_duplicate):
		return {"ok": 0, "duplicate": dup}

	company = paper.company
	whs = _warehouses(company)
	warehouse = warehouse or frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if warehouse not in whs:
		frappe.throw(_("Choose a warehouse of {0}.").format(company))
	date = getdate(needed_by) if needed_by else getdate(add_days(nowdate(), DEFAULT_NEEDED_DAYS))
	if date < getdate(nowdate()):
		frappe.throw(_("The date cannot be in the past."))
	if school:
		if not _school_field(purpose) or not frappe.db.exists("School", school):
			frappe.throw(_("School {0} not found.").format(school))

	doc = _build_order(paper, purpose, party, keep, left, company, warehouse, date, school, rate_mode)
	doc.insert()  # AS THE USER: normal permissions + the PO hooks (approval guards)
	_attach_pages(paper, doc)
	learned = learn_aliases(paper, party, keep)

	approval_error = None
	if cint(send_for_approval) and purpose == "Purchase Order" and _approval_active():
		from frappe.model.workflow import apply_workflow

		frappe.db.savepoint("kgs_paper_send")
		try:
			apply_workflow(doc, WORKFLOW_ACTION)
		except Exception as e:
			frappe.db.rollback(save_point="kgs_paper_send")
			frappe.clear_messages()
			approval_error = str(e) or _("It could not be sent for approval.")

	paper.db_set({
		"status": "Saved", "created_doctype": purpose, "created_doc": doc.name, "party": party,
		"saved_by": frappe.session.user, "saved_on": now_datetime(),
	})
	out = _saved_response(paper)
	out["approval_error"] = approval_error
	out["learned"] = learned
	return out


def _build_order(paper, purpose, party, keep, left, company, warehouse, date, school, rate_mode):
	is_po = purpose == "Purchase Order"
	doc = frappe.new_doc(purpose)
	doc.company = company
	doc.transaction_date = nowdate()  # never back-dated
	if is_po:
		doc.supplier = party
		doc.schedule_date = date
	else:
		doc.customer = party
		doc.delivery_date = date
	doc.set_warehouse = warehouse
	if school and _school_field(purpose):
		doc.custom_school_name = school
	for ln in keep:
		row = {
			"item_code": ln["item_code"],
			"qty": flt(ln["qty"]),
			"uom": ln["uom"],
			"conversion_factor": flt(ln.get("conversion_factor")) or 1,
			"warehouse": warehouse,
		}
		if is_po:
			row["schedule_date"] = date
			if rate_mode != "ours" and ln.get("paper_rate"):
				row["rate"] = flt(ln["paper_rate"])
			if ln.get("code"):
				row["supplier_part_no"] = ln["code"][:140]
		else:
			row["delivery_date"] = date
		doc.append("items", row)
	remark = _("From paper {0}").format(paper.name)
	if paper.paper_no:
		remark += f" ({paper.paper_no})"
	if left:
		remark += ". " + _("Left out: {0}").format("; ".join(
			f"{ln['text']}" + (f" × {_money(ln['qty'])}" if ln.get("qty") else "") for ln in left[:30]))
	if is_po and frappe.db.has_column("Purchase Order", "custom_remark"):
		doc.custom_remark = remark[:1000]
	elif not is_po:
		# Sales Order has no remark field of ours; the timeline comment carries it
		doc.flags.kgs_paper_remark = remark
	return doc


def _attach_pages(paper, doc):
	for f in pr.paper_files(paper.name):
		frappe.get_doc({
			"doctype": "File",
			"file_url": f.file_url,
			"file_name": f.file_name,
			"is_private": 1,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
		}).insert(ignore_permissions=True)
	note = doc.flags.kgs_paper_remark or _("Made in the KGS Staff app from paper {0}.").format(paper.name)
	doc.add_comment("Comment", note)


def _saved_response(paper, already=0):
	dt, dn = paper.created_doctype, paper.created_doc
	vals = frappe.db.get_value(dt, dn, ["docstatus", "grand_total"], as_dict=True) or {}
	wf = frappe.db.get_value(dt, dn, "workflow_state") if frappe.db.has_column(dt, "workflow_state") else None
	state = _state(paper)
	keep, left, _p = _lines_to_save(state, paper.purpose)
	return {
		"ok": 1, "already": already, "name": paper.name, "doctype": dt, "doc": dn,
		"workflow_state": wf, "grand_total": flt(vals.get("grand_total")),
		"lines": len(keep), "qty": sum(flt(ln.get("qty")) for ln in keep),
		"left_out": [{"text": ln["text"], "qty": ln.get("qty")} for ln in left],
		"url": f"/app/{frappe.scrub(dt).replace('_', '-')}/{dn}",
		"owners": _owner_names() if dt == "Purchase Order" else [],
	}


# ── remembered names (Party Item Alias) ──────────────────────────────────────


def _text_key(ln):
	"""A wording without its own class gets the class of its section ("ENGLISH"
	under a "Class 3" heading must not match next year's Class 4 list)."""
	key = pm.match_key(ln.get("text"))
	if key and not pm.class_of(ln.get("text")) and ln.get("line_class"):
		key = f"{key} C{ln['line_class']}"
	return key if len(key) >= 4 else ""


def learn_aliases(paper, party, lines):
	"""Remember every saved line for this party, by code and by wording. Runs as
	the clerk; the flag lets Party Item Alias.validate accept a non-manager here."""
	user, now = frappe.session.user, now_datetime()
	n = 0
	frappe.flags.kgs_paper_learning = True
	try:
		for ln in lines:
			keys = []
			ck = pm.code_key(ln.get("code"))
			if ck:
				keys.append(("Code", ck, ln.get("code")))
			tk = _text_key(ln)
			if tk:
				keys.append(("Text", tk, ln.get("text")))
			for key_type, key, printed in keys:
				name = alias_name(paper.party_type, party, key_type, key)
				vals = {
					"item_code": ln["item_code"], "paper_unit": pm.canonical_unit(ln.get("unit")), "uom": ln.get("uom"),
					"conversion_factor": flt(ln.get("conversion_factor")) or 1, "paper_text": (printed or "")[:140],
					"last_used_on": now, "last_used_by": user, "last_paper": paper.name,
				}
				if ln.get("mrp"):
					vals["mrp"] = flt(ln["mrp"])
				if not frappe.db.exists("Party Item Alias", name):
					doc = frappe.get_doc(dict(vals, doctype="Party Item Alias", party_type=paper.party_type, party=party,
						key_type=key_type, match_key=key, times_used=1))
					doc.flags.ignore_permissions = True
					frappe.db.savepoint("kgs_alias")
					try:
						doc.insert()
						n += 1
						continue
					except frappe.DuplicateEntryError:  # another phone learned it a moment ago
						frappe.db.rollback(save_point="kgs_alias")
				doc = frappe.get_doc("Party Item Alias", name)
				same = doc.item_code == ln["item_code"]
				doc.update(vals)
				doc.times_used = (cint(doc.times_used) + 1) if same else 1
				doc.flags.ignore_version = True
				doc.flags.ignore_permissions = True
				doc.save()
				n += 1
			if ck and paper.party_type == "Supplier":
				_fill_supplier_part_no(ln["item_code"], party, ln.get("code"))
	finally:
		frappe.flags.kgs_paper_learning = False
	return n


def _fill_supplier_part_no(item_code, supplier, code):
	"""ERPNext's own "supplier part no" (Item → Supplier Items), only where empty,
	so a printed PO can show the supplier their code. Quiet child-row write: the
	Item itself is not saved (no version, no modified, no item hooks)."""
	code = (code or "").strip()[:140]
	if not code:
		return
	row = frappe.db.get_value("Item Supplier", {"parent": item_code, "parenttype": "Item", "supplier": supplier},
		["name", "supplier_part_no"], as_dict=True)
	if row:
		if not row.supplier_part_no:
			frappe.db.set_value("Item Supplier", row.name, "supplier_part_no", code, update_modified=False)
		return
	idx = cint(frappe.db.sql("select max(idx) from `tabItem Supplier` where parent = %s and parenttype = 'Item'", item_code)[0][0]) + 1
	now, user = now_datetime(), frappe.session.user
	frappe.get_doc({
		"doctype": "Item Supplier", "parent": item_code, "parenttype": "Item", "parentfield": "supplier_items",
		"supplier": supplier, "supplier_part_no": code, "idx": idx,
		"creation": now, "modified": now, "owner": user, "modified_by": user,
	}).db_insert()


def _names_guard(party_type):
	settings = _guard()
	if party_type not in ("Supplier", "Customer"):
		frappe.throw(_("Choose suppliers or customers."))
	return settings


@frappe.whitelist(methods=["POST"])
def alias_parties(party_type, txt=""):
	_names_guard(party_type)
	field = "supplier_name" if party_type == "Supplier" else "customer_name"
	values = {"pt": party_type, "txt": f"%{txt.strip()}%" if txt else "%"}
	rows = frappe.db.sql(
		f"""select a.party, p.`{field}` as title, count(*) as names, max(a.modified) as last
		from `tabParty Item Alias` a join `tab{party_type}` p on p.name = a.party
		where a.party_type = %(pt)s and (a.party like %(txt)s or p.`{field}` like %(txt)s)
		group by a.party, p.`{field}` order by last desc limit 50""",
		values,
		as_dict=True,
	)
	for r in rows:
		r["last"] = str(r["last"])
	return {"parties": rows, "can_edit": 1 if can_edit(party_type) else 0}


@frappe.whitelist(methods=["POST"])
def list_aliases(party_type, party, txt="", start=0):
	_names_guard(party_type)
	values = {"pt": party_type, "party": party, "txt": f"%{txt.strip()}%" if txt else "%", "start": max(0, cint(start))}
	rows = frappe.db.sql(
		"""select a.name, a.key_type, a.paper_text, a.item_code, i.item_name, a.uom, a.mrp, a.times_used, a.last_used_on,
			a.last_used_by, i.disabled
		from `tabParty Item Alias` a left join `tabItem` i on i.name = a.item_code
		where a.party_type = %(pt)s and a.party = %(party)s
			and (a.paper_text like %(txt)s or a.item_code like %(txt)s or i.item_name like %(txt)s)
		order by a.last_used_on desc, a.name limit 50 offset %(start)s""",
		values,
		as_dict=True,
	)
	for r in rows:
		r["last_used_on"] = str(r["last_used_on"] or "")
		r["last_used_by_name"] = frappe.utils.get_fullname(r["last_used_by"]) if r["last_used_by"] else ""
	return {"rows": rows, "party_title": _party_name(party_type, party), "can_edit": 1 if can_edit(party_type) else 0}


@frappe.whitelist(methods=["POST"])
def change_alias(name, item_code):
	doc = frappe.get_doc("Party Item Alias", name)
	_names_guard(doc.party_type)
	if not can_edit(doc.party_type):
		raise frappe.PermissionError(_("Only a manager can change remembered names."))
	it = frappe.db.get_value("Item", item_code, ["name", "disabled", "has_variants", "stock_uom"], as_dict=True)
	if not it or it.disabled or it.has_variants:
		frappe.throw(_("Choose an enabled item."))
	if doc.item_code != it.name:
		doc.item_code = it.name
		doc.uom, doc.conversion_factor, doc.times_used = it.stock_uom, 1, 1
	doc.save(ignore_permissions=True)  # role checked above + in validate
	return {"name": doc.name, "item_code": doc.item_code, "item_name": frappe.db.get_value("Item", doc.item_code, "item_name")}


@frappe.whitelist(methods=["POST"])
def delete_alias(name):
	doc = frappe.get_doc("Party Item Alias", name)
	_names_guard(doc.party_type)
	if not can_edit(doc.party_type):
		raise frappe.PermissionError(_("Only a manager can delete remembered names."))
	frappe.delete_doc("Party Item Alias", name, ignore_permissions=True)  # role checked above + in on_trash
	return {"deleted": name}


# ── settings (System Manager + Shop Owner) ───────────────────────────────────

_SETTING_FIELDS = ("enabled", "so_enabled", "provider", "ai_model", "fallback_model", "auto_fallback", "rerank",
	"month_page_limit", "peak_month_page_limit", "usd_rate", "gst_percent")


@frappe.whitelist(methods=["POST"])
def get_paper_settings():
	_guard_settings()
	s = pr.get_settings()
	usage = pr.month_usage(s)
	gst = 1 + s.gst_percent / 100
	models = []
	for m, p in s.prices.items():
		models.append({
			"model": m, "label": p.label or m, "note": p.note or "", "provider": p.provider or "Anthropic",
			"input_per_mtok": flt(p.input_per_mtok), "output_per_mtok": flt(p.output_per_mtok),
			# ESTIMATE per page, the plan's cost basis: ~7,000 tokens in (page image +
			# instructions), ~3,000 out (the lines). The real figures are in "usage".
			"inr_per_page": round((7000 * flt(p.input_per_mtok) + 3000 * flt(p.output_per_mtok)) / 1e6 * s.usd_rate * gst, 2),
		})
	return {
		"values": {k: s.get(k) for k in _SETTING_FIELDS},
		"models": models,
		"providers": [{"name": n, "label": c.label, "active": 1} for n, c in pr.PROVIDERS.items()]
			+ [dict(p, active=0) for p in pr.COMING_SOON],
		"key_set": 1 if (frappe.conf.get("kgs_paper_ai_key") or "").strip() else 0,
		"fake": 1 if pr.fake_allowed() else 0,
		"usage": usage,
	}


@frappe.whitelist(methods=["POST"])
def save_paper_settings(values):
	_guard_settings()
	if isinstance(values, str):
		values = json.loads(values or "{}")
	doc = frappe.get_doc("Order Paper Settings")
	for k in _SETTING_FIELDS:
		if k in values:
			doc.set(k, values[k])
	if isinstance(values.get("models"), list):
		doc.set("model_prices", [])
		for m in values["models"][:20]:
			doc.append("model_prices", {
				"model": str(m.get("model") or "").strip()[:80], "label": str(m.get("label") or "")[:80],
				"provider": "Anthropic", "input_per_mtok": flt(m.get("input_per_mtok")),
				"output_per_mtok": flt(m.get("output_per_mtok")), "note": str(m.get("note") or "")[:140],
			})
	doc.save()  # as the user: Order Paper Settings grants write to System Manager + Shop Owner only
	frappe.clear_document_cache("Order Paper Settings", "Order Paper Settings")
	return get_paper_settings()
