# Copyright (c) 2026, Trustbit Software and contributors
# KGS Staff app — Order from Paper: a photo / PDF of a supplier's quotation,
# price list or order list (or a school's book list) → a DRAFT Purchase Order
# (optionally sent into the "Purchase Order Approval" workflow) or a DRAFT
# Sales Order; a supplier's bill or challan → a Purchase Receipt or Purchase
# Invoice, linked to its PO / Receipt first, saved as a draft or submitted
# (paper_purchase.py). Plan: KGS/PLAN_order_from_paper.md + mockup v4.
#
# Flow: upload_paper → background read job (paper_read: AI; paper_match:
# our items) → [Receipt / Bill: set_links] → check screen (get_paper /
# update_lines / set_party) → save_order (inserts AS THE USER, attaches the
# pages, learns the confirmed lines as "remembered names" = Party Item Alias)
# → [after a submitted Receipt: make_bill, from the same reading, no AI].
#
# Every endpoint is POST-only and re-checks role, kill switches and rate limit.
# Purchase side: Purchase User / Purchase Manager (Receipts and Bills: only
# the people listed in Order Paper Settings); sales side: Sales User / Sales
# Manager (and only while "Sales Orders from Paper" is on). Settings: System
# Manager / Shop Owner. The AI key never leaves site_config.

import base64
import binascii
import json
import re
import time

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from trustbit_school_book_seller.staff_app import paper_match as pm
from trustbit_school_book_seller.staff_app import paper_purchase as pp
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

_BUY_MANAGERS = ("Purchase Manager", "System Manager", "Shop Owner")
PURPOSES = {
	"Purchase Order": {"party_type": "Supplier", "roles": PAPER_PO_ROLES, "managers": _BUY_MANAGERS},
	"Sales Order": {"party_type": "Customer", "roles": PAPER_SO_ROLES, "managers": ("Sales Manager", "System Manager", "Shop Owner")},
	"Purchase Receipt": {"party_type": "Supplier", "roles": PAPER_PO_ROLES, "managers": _BUY_MANAGERS},
	"Purchase Invoice": {"party_type": "Supplier", "roles": PAPER_PO_ROLES, "managers": _BUY_MANAGERS},
}
SHORT = {"Purchase Order": "PO", "Sales Order": "SO", "Purchase Receipt": "PR", "Purchase Invoice": "PI"}
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


def can_make(purpose, settings=None, roles=None, user=None):
	settings = settings or pr.get_settings()
	roles = roles if roles is not None else _roles()
	if not settings.enabled or purpose not in PURPOSES:
		return False
	if purpose == "Sales Order" and not settings.so_enabled:
		return False
	if pp.is_purchase(purpose):
		# owners' decision 2026-10-20: only the people on the Settings list
		if not settings.pr_pi_enabled or (user or frappe.session.user) not in (settings.receivers or []):
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
		if pp.is_purchase(purpose) and not settings.pr_pi_enabled:
			raise frappe.PermissionError(_("Receipts and Bills from paper are switched off."))
		if not can_make(purpose, settings):
			if pp.is_purchase(purpose):
				raise frappe.PermissionError(_("Receipts and Bills from paper are only for the people the owners listed in Settings."))
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
		"pr": 1 if can_make("Purchase Receipt", s, roles) else 0,
		"pi": 1 if can_make("Purchase Invoice", s, roles) else 0,
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


# ── the lines so far, while the AI is still writing ──────────────────────────

LIVE_TTL = 1800  # seconds; the job removes it as soon as the reading ends
LIVE_FIELDS = ("text", "qty", "unit", "rate", "mrp", "amount", "page")


def _live_key(name):
	return f"kgs_paper_live:{name}"


class LiveReading:
	"""What the phone shows during a reading: the lines read so far (cleaned
	like the final reading, as printed — no matching yet) in Redis, never in
	the database. Written about once a second; the phone polls every 2 s.
	"run" changes whenever the lines start over (fallback model, retried
	stream), so the phone knows to drop the cards it has."""

	EVERY = 0.8  # seconds between writes

	def __init__(self, name):
		self.name = name
		self.s = {"run": "", "attempt": 0, "phase": "reading", "model": "", "note": "", "party": "", "no": "", "lines": []}
		self.last = 0.0
		self.dirty = False

	def begin(self, model_label, note=""):
		self.s.update({"run": frappe.generate_hash(length=10), "attempt": self.s["attempt"] + 1, "phase": "reading",
			"model": model_label, "note": note, "lines": []})
		self.put()

	def phase(self, phase):
		self.s["phase"] = phase
		self.put()

	def __call__(self, kind, payload):
		s = self.s
		if kind == "restart":
			s["run"], s["lines"] = frappe.generate_hash(length=10), []
			self.dirty = True
		elif kind == "header" and isinstance(payload, dict):
			s["party"], s["no"] = pr._txt(payload.get("party_name"), 140), pr._txt(payload.get("paper_no"), 60)
			self.dirty = True
		elif kind == "lines":
			for raw in payload or []:
				ln = pr.clean_line(raw, len(s["lines"]) + 1) if len(s["lines"]) < pr.MAX_LINES else None
				if ln:
					s["lines"].append({k: ln[k] for k in LIVE_FIELDS})
					self.dirty = True
		if self.dirty and time.monotonic() - self.last >= self.EVERY:
			self.put()

	def put(self):
		self.last, self.dirty = time.monotonic(), False
		try:
			frappe.cache.set_value(_live_key(self.name), self.s, expires_in_sec=LIVE_TTL)
		except Exception:
			pass  # the phone then shows the reading screen without cards

	def end(self):
		try:
			frappe.cache.delete_value(_live_key(self.name))
		except Exception:
			pass


def _live(name, since=0, run=None):
	"""The live reading for the phone: only the lines it does not have yet
	(since = how many it has from the same run)."""
	# expires=True: always from Redis (a plain get_value keeps a per-request copy,
	# which set_value with an expiry never updates)
	s = frappe.cache.get_value(_live_key(name), expires=True)
	if not isinstance(s, dict):
		return None
	lines = s.get("lines") or []
	since = max(0, min(cint(since), len(lines))) if run and run == s.get("run") else 0
	out = {k: s.get(k) for k in ("run", "attempt", "phase", "model", "note", "party", "no")}
	out.update({"count": len(lines), "since": since, "lines": lines[since:]})
	return out


# ── the read job ─────────────────────────────────────────────────────────────


def run_read_job(name, model=None, reason="first"):
	"""reason: first / reread (the AI reads) or rematch (the supplier changed on a
	Receipt / Bill: the stored reading is matched again, no AI, no cost)."""
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

	live = LiveReading(name)
	status, error, state, data, used_model = "Failed", None, None, None, model
	try:
		if reason == "rematch":
			data, used_model, notes = pr._json(paper.ai_json, None), paper.ai_model, list((old_state or {}).get("notes") or [])
			if not data or not data.get("lines"):
				raise pr.PaperReadError(_("The reading is missing. Read the paper again."), "rematch without ai_json")
			live.begin(_model_label(settings, used_model))
			live.phase("matching")
			state = build_state(paper, data, settings, provider, usage, notes, party=(old_state or {}).get("party"))
		else:
			blocks = pr.content_blocks(name)
			pages = cint(paper.page_count) or 1
			label = _model_label(settings, model)
			ours = pm.our_identity()
			live.begin(label, _("Reading again with {0}.").format(label) if reason != "first" else "")
			data, res = pr.read(provider, model, blocks, on_progress=live, ours=ours)
			usage.append(pr.usage_entry(settings, res, reason, pages, provider.name))
			notes = []
			if reason == "first" and settings.auto_fallback and settings.fallback_model and settings.fallback_model != model:
				why = pr.looks_wrong(data)
				if why and _pages_left(settings) - pages >= 0:
					try:
						label2 = _model_label(settings, settings.fallback_model)
						live.begin(label2, _("Reading again with {0} because {1}.").format(label2, why))
						data2, res2 = pr.read(provider, settings.fallback_model, blocks, on_progress=live, ours=ours)
						usage.append(pr.usage_entry(settings, res2, "fallback", pages, provider.name))
						if data2["lines"]:
							data, used_model = data2, settings.fallback_model
							notes.append(_("Read again with {0} because {1}.").format(_model_label(settings, used_model), why))
					except pr.PaperReadError as e:
						frappe.log_error(title=f"Order Paper {name}: fallback read failed", message=e.detail)
			if not data["lines"]:
				raise pr.PaperReadError(_("No item lines were found on this paper. Take a clearer photo of the whole page."), "0 lines")
			if _swap_if_ours(data):
				notes.append(_("This is the shop's own paper — the party is the one it is addressed to."))
			live.phase("matching")
			state = build_state(paper, data, settings, provider, usage, notes)
		if old_state:
			_carry_decisions(old_state, state)
			if reason == "rematch":
				state["party_how"] = old_state.get("party_how") or "chosen"
			if pp.is_purchase(paper.purpose):
				compose_all(state, paper.purpose, paper.party_type, cint(paper.default_copies))
				pp.doc_pcts(state, pm.exact_layers(state["lines"], paper.party_type, state.get("party")))
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
	live.end()


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


def _swap_if_ours(data):
	"""On the shop's own paper (its order list on its letterhead) the party is
	the business it is addressed to — KGS is never its own supplier. True when swapped."""
	if not (data.get("party_name") or data.get("party_gstin")) or not pm.is_us(data.get("party_name"), data.get("party_gstin")):
		return False
	data["party_name"], data["buyer_name"] = data.get("buyer_name") or "", data.get("party_name")
	data["party_gstin"], data["buyer_gstin"] = data.get("buyer_gstin") or "", data.get("party_gstin")
	return True


def build_state(paper, data, settings, provider, usage, notes, party=None):
	party_type = paper.party_type
	purpose = paper.purpose
	if party:  # rematch: the supplier a person chose
		how, cands = "chosen", name_candidates(party_type, data.get("party_name") or "")
	else:
		party, how, cands = detect_party(party_type, data)
	lines = data["lines"]
	discount_note = data.get("discount_note") or ""

	exact = pm.exact_layers(lines, party_type, party)
	need_fuzzy = [ln for ln in lines if ln["idx"] not in exact or exact[ln["idx"]]["how"] == "other_party"]
	docs = pp.open_docs(purpose, party, paper.company) if pp.is_purchase(purpose) else []
	fuzzy = {}
	if need_fuzzy or docs:
		index = pm.load_index()
		for ln in need_fuzzy:
			cls = pm.class_of(ln.get("class_hint")) or pm.class_of(ln["text"])
			fuzzy[ln["idx"]] = index.search(ln["text"], line_class=cls, mrp=ln.get("mrp"))
		if docs:
			pp.score_docs(index, lines, docs)
		del index

	# what the shop did with each suggested item: dead twins drop, items bought
	# from this supplier rise (rank_candidates)
	activity = pm.item_activity({c["item_code"] for cs in fuzzy.values() for c in cs} | {h["item_code"] for h in exact.values()})
	for cs in fuzzy.values():
		pm.rank_candidates(cs, activity, party if party_type == "Supplier" else None)
	if not party and party_type == "Supplier":
		known = {c["party"] for c in cands}
		tops = [cs[0]["item_code"] for cs in fuzzy.values() if cs] + [h["item_code"] for h in exact.values()]
		for sup, n in pm.party_suggestions(activity, tops):
			if sup not in known and n >= 2 and not cint(frappe.db.get_value("Supplier", sup, "disabled")):
				cands.append({"party": sup, "title": _party_name("Supplier", sup), "score": 0, "items": n})

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
	if pp.is_purchase(purpose):
		state["open_docs"] = docs
		state["links"] = None  # the person links the PO / Receipt (or "No PO") first
	compose_all(state, purpose, party_type, cint(paper.default_copies), exact=exact)
	if pp.is_purchase(purpose):
		pp.doc_pcts(state, exact)
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
	if ok and ok[0].get("rank_score", ok[0]["score"]) >= pm.PRESELECT:
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
	purchase = pp.is_purchase(purpose)
	if purchase:
		codes |= {r["item_code"] for r in pp.linked_rows(state)}
	info = pm.item_details(codes)
	for ln in lines:
		_compose(ln, exact.get(ln["idx"]), info, purpose, copies)
	if purchase:
		pp.apply_links(state, info, exact, purpose)
		for ln in lines:
			if ln.get("colour") == "green" and not ln.get("by_person") and not flt(ln.get("qty")):
				ln["colour"], ln["note"] = "amber", _("No quantity on the paper — enter it")


def _compose(ln, hit, info, purpose, copies):
	person = bool(ln.get("by_person"))
	if person and ln.get("item_code") in info:
		# keep the person's item / unit / qty; refresh only facts about the item
		_set_item(ln, info[ln["item_code"]], keep_uom=True)
		ln["colour"] = "green"
		ln["pct"] = 100
		return
	ln["how"], ln["note"], ln["alias"], ln["other_party"] = "none", "", None, None
	ln.pop("unit_ratio", None)
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
	# match %: exact layers 100, else the fuzzy candidate's own %
	if ln["how"] in ("alias_code", "alias_text", "barcode", "item_code", "party_code"):
		ln["pct"] = 100
	else:
		c = next((c for c in ln.get("candidates") or [] if c["item_code"] == item_code), None)
		ln["pct"] = c.get("pct", pm.pct(c.get("score"))) if c else (80 if ln["how"] == "other_party" else None)
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
	if ln["colour"] == "green" and ln.get("pct") is None:
		ln["pct"] = 100


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

	old = {key(ln): ln for ln in old_state.get("lines") or [] if ln.get("by_person") or ln.get("decision") or ln.get("rate_by_person")}
	for ln in new_state["lines"]:
		o = old.get(key(ln))
		if not o:
			continue
		for k in ("decision", "by_person", "qty_by_person", "item_code", "item_name", "item_cls", "item_mrp", "stock_uom",
				"uoms", "uom", "conversion_factor", "unit_known", "can_keep", "colour", "last_purchase_rate",
				"rate_by_person", "buy_rate", "unit_ratio"):
			if k in o:
				ln[k] = o[k]
		if o.get("qty_by_person"):
			ln["qty"] = o.get("qty")
	if old_state.get("party") and not new_state.get("party"):
		new_state["party"] = old_state["party"]
	# the same supplier's links stay (a re-read); a new supplier links again
	if old_state.get("links") and old_state.get("party") == new_state.get("party") and "links" in new_state:
		still = {d["name"] for d in new_state.get("open_docs") or [] if d["linkable"]}
		links = dict(old_state["links"])
		if links.get("mode") != "docs" or set(links.get("docs") or []) <= still:
			new_state["links"] = links


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
		"short": SHORT.get(purpose, ""),
		"source_paper": paper.get("source_paper"), "bill_paper": paper.get("bill_paper"),
	}
	if paper.status in ("Ready", "Saved") and purpose != "Sales Order":
		# what we paid before (never copied into a rate: shown next to it)
		out["last_bought"] = pm.last_bought({ln.get("item_code") for ln in out["lines"] if ln.get("item_code")})
		out["usual_discount"] = pm.supplier_usual_discount(party) if party else None
	if pp.is_purchase(purpose):
		out.update(_purchase_payload(paper, state, data, settings))
		if paper.status == "Saved" and paper.created_doc:
			out.update(_saved_purchase_info(paper, state))
	if paper.status == "Ready" and pp.is_purchase(purpose):
		out["save"] = _purchase_save_info(paper, state, data, settings)
		return out
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


def _purchase_payload(paper, state, data, settings):
	"""Links, the documents to link and the money check of a Receipt / Bill."""
	links = state.get("links")
	docs = state.get("open_docs") or []
	keep, left, _pending = _lines_to_save(state, paper.purpose)
	used = {(ln.get("doc_row") or {}).get("name") for ln in state["lines"] if ln.get("doc_row") and ln.get("decision") != "left"}
	linked = set((links or {}).get("docs") or [])
	not_on_paper = [
		{"doc": r["parent"], "idx": r["idx"], "item_name": r["item_name"], "due": r["due"], "uom": r["uom"]}
		for d in docs if d["name"] in linked for r in d["rows"] if r["due"] > 0 and r["name"] not in used
	]
	tot = pp.totals(state, data, paper.purpose, keep, left)
	problems = [{"idx": ln["idx"], "text": ln.get("item_name") or ln.get("text"), "why": p}
		for ln in keep for p in [pp.line_problem(ln, paper.purpose)] if p]
	return {
		"links": links,
		"open_docs": [{k: d.get(k) for k in ("doctype", "name", "date", "owner_name", "status", "linkable", "why", "bill_no",
			"pct", "hits", "due_lines", "draft_bills")} | {"lines": len(d["rows"])} for d in docs],
		"doc_preselect": pp.DOC_PRESELECT,
		"not_on_paper": not_on_paper[:60],
		"totals": tot,
		"problems": problems,
		"charges": data.get("charges") or [],
		"tax_total": data.get("tax_total"),
		"freight_account": settings.get("freight_account") or "",
	}


def _purchase_save_info(paper, state, data, settings):
	company = paper.company
	whs = _warehouses(company)
	rows = pp.linked_rows(state)
	row_wh = next((r["warehouse"] for r in rows if r.get("warehouse") in whs), None)
	default_wh = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	bill_date = pp.parse_paper_date(paper.paper_date)
	if bill_date and (bill_date > getdate(nowdate()) or bill_date < getdate(add_days(nowdate(), -400))):
		bill_date = None
	return {
		"warehouses": whs,
		"warehouse": row_wh or (default_wh if default_wh in whs else (whs[0] if whs else None)),
		"posting_date": str(nowdate()) if paper.purpose == pp.RECEIPT else str(bill_date or nowdate()),
		"bill_date_read": 1 if bill_date else 0,
		"bill_no": paper.paper_no or "",
		"today": str(nowdate()),
	}


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
		where purpose = %s and party_type = %s and party = %s and paper_no = %s and status = 'Saved' and name != %s
		order by saved_on desc limit 1""",
		(paper.purpose, paper.party_type, party, paper.paper_no, paper.name),
		as_dict=True,
	)
	if not row:
		return None
	r = row[0]
	return {"paper": r.name, "doctype": r.created_doctype, "doc": r.created_doc, "saved_on": str(r.saved_on or "")}


@frappe.whitelist(methods=["POST"])
def get_paper(name, light=0, since=0, run=None):
	"""light = the 2-second poll during a reading: status + the lines read since
	the last poll (since/run = what the phone already has)."""
	paper = _load(name)
	settings = _guard(paper.purpose)
	reading = paper.status in ("Uploaded", "Reading")
	if cint(light) and reading:
		out = {"name": paper.name, "status": paper.status, "purpose": paper.purpose, "page_count": paper.page_count}
	else:
		out = _paper_payload(paper, settings)
	if reading:
		out["file_kind"] = paper.file_kind
		out["live"] = _live(paper.name, since, run)
	return out


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
	changed = state.get("party") != party
	state["party"] = party
	state["party_how"] = "chosen"
	if pp.is_purchase(paper.purpose) and changed:
		# another supplier = other POs / Receipts: match the stored reading again
		# against them in the background (the word index never loads in a web worker)
		state["links"], state["open_docs"] = None, []
		paper.db_set({"lines_json": json.dumps(state), "party": party, "status": "Reading", "error": None,
			"state_version": cint(paper.state_version) + 1})
		_enqueue_read(paper.name, None, "rematch")
		return _paper_payload(paper)
	compose_all(state, paper.purpose, paper.party_type, cint(paper.default_copies))
	paper.db_set({"lines_json": json.dumps(state), "party": party, "state_version": cint(paper.state_version) + 1})
	return _paper_payload(paper)


@frappe.whitelist(methods=["POST"])
def set_links(name, mode, docs=None, version=None):
	"""Receipt / Bill: link the paper to the supplier's PO(s) or unbilled
	Receipt(s) — mode "docs" — or to nothing ("none": not ordered / the bill adds
	the stock itself). mode "change" opens the choice again."""
	paper = _load(name, lock=True)
	_guard(paper.purpose)
	_editable(paper)
	if not pp.is_purchase(paper.purpose):
		frappe.throw(_("Only a Receipt or a Bill is linked."))
	conflict = _check_version(paper, version)
	if conflict:
		return conflict
	state = _state(paper)
	if isinstance(docs, str):
		docs = json.loads(docs or "[]")
	if mode == "change":
		state["links"] = None
	elif mode == "none":
		state["links"] = {"mode": "none", "doctype": None, "docs": []}
	elif mode == "docs":
		if not state.get("party"):
			frappe.throw(_("Choose the supplier first."))
		fresh = {d["name"]: d for d in pp.open_docs(paper.purpose, state["party"], paper.company)}
		names = list(dict.fromkeys(str(d) for d in docs or []))[:10]
		if not names:
			frappe.throw(_("Tick a document to link, or choose \"No PO\"."))
		chosen = []
		for n in names:
			d = fresh.get(n)
			if not d:
				frappe.throw(_("{0} is not open for this supplier any more.").format(n))
			if not d["linkable"]:
				frappe.throw(_("{0} cannot be linked: {1}.").format(n, d["why"].lower() if d["why"] else _("not submitted")))
			chosen.append(d)
		if len({d["doctype"] for d in chosen}) > 1:
			frappe.throw(_("Link Receipts or POs, not both: a bill from a Receipt never adds stock again."))
		# keep the stored scores (doc_scores); refresh due quantities and rows
		old = {d["name"]: d for d in state.get("open_docs") or []}
		for n, d in fresh.items():
			if n in old:
				d.update({k: old[n].get(k) for k in ("pct", "hits", "due_lines") if k in old[n]})
		state["open_docs"] = list(fresh.values())
		state["links"] = {"mode": "docs", "doctype": chosen[0]["doctype"], "docs": names}
	else:
		frappe.throw(_("Unknown choice."))
	compose_all(state, paper.purpose, paper.party_type, cint(paper.default_copies))
	pp.doc_pcts(state, pm.exact_layers(state["lines"], paper.party_type, state.get("party")))
	paper.db_set({"lines_json": json.dumps(state), "state_version": cint(paper.state_version) + 1})
	return _paper_payload(paper)


@frappe.whitelist(methods=["POST"])
def update_lines(name, changes, version=None, copies=None):
	"""changes: [{idx, decision?: "ok" | "left" | null, item_code?, uom?, qty?,
	  rate? (Receipt / Bill: our rate), read_qty? / read_rate? / read_amount?
	  (a number misread from the paper), fix?: "qty" (the quantity the line's
	  amount stands for)}]
	Returns {"version", "lines": [the changed lines], "totals"?} or {"conflict": 1, "paper"}."""
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
	purchase = pp.is_purchase(paper.purpose)
	if purchase:
		for ch in (changes or [])[:500]:
			ln = by_idx.get(cint(ch.get("idx"))) if isinstance(ch, dict) else None
			if ln:
				_purchase_change(ln, ch)

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
			row = ln.get("doc_row")
			if row and u["uom"] != row["uom"] and not ch.get("item_code"):
				frappe.throw(_("This line is on {0}, in {1}: ERPNext needs the same unit.").format(row["parent"], row["uom"]))
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
				if not purchase:
					compose_all({"lines": [ln], "party": state.get("party")}, paper.purpose, paper.party_type, cint(paper.default_copies))
	if purchase:
		# rows, over-delivery, rates and totals depend on every line: compose all again
		compose_all(state, paper.purpose, paper.party_type, cint(paper.default_copies))
		touched = set(by_idx)
	version = cint(paper.state_version) + 1
	paper.db_set({"lines_json": json.dumps(state), "state_version": version, "default_copies": paper.default_copies})
	out = {"version": version, "lines": [by_idx[i] for i in sorted(touched)]}
	if purchase:
		data = pr._json(paper.ai_json, {}) or {}
		pay = _purchase_payload(paper, state, data, pr.get_settings())
		out.update({k: pay[k] for k in ("totals", "problems", "not_on_paper")})
	return out


def _purchase_change(ln, ch):
	"""A Receipt / Bill line: our rate, or a number misread from the paper."""
	def num(v, what):
		if v in (None, ""):
			return None
		n = flt(v)
		if n <= 0 or n > 1e8:
			frappe.throw(_("{0} must be more than 0.").format(what))
		return n

	if "rate" in ch:
		r = num(ch["rate"], _("The rate"))
		ln["buy_rate"], ln["rate_by_person"] = r, 1 if r else 0
		ln["rate_src"] = "person" if r else None
	for key, field, what in (("read_qty", "paper_qty", _("The quantity")), ("read_rate", "rate", _("The rate")),
			("read_amount", "amount", _("The amount"))):
		if key in ch:
			ln[field] = num(ch[key], what)
			ln["read_fixed"] = 1
	if ch.get("fix") == "qty":
		c = pr.line_check({"qty": ln.get("paper_qty"), "rate": ln.get("rate"), "mrp": ln.get("mrp"), "amount": ln.get("amount"),
			"discount_percent": ln.get("discount_percent")})
		if not c or not c.get("fix_qty"):
			frappe.throw(_("This line needs no quantity fix."))
		ln["paper_qty"], ln["read_fixed"] = c["fix_qty"], 1
	if any(k in ch for k in ("read_qty", "read_rate", "read_amount", "fix")):
		ln["paper_rate"] = pr.paper_rate(ln)
		ln["paper_amount"] = pr.line_amount(ln)
		if not ln.get("qty_by_person") and ln.get("paper_qty"):
			ln["qty"] = round(flt(ln["paper_qty"]) * (flt(ln.get("unit_ratio")) or 1.0), 6)


@frappe.whitelist(methods=["POST"])
def get_item_facts(name, item_codes):
	"""The choose sheet: what we paid before for these items (last 3 bills)."""
	paper = _load(name)
	_guard(paper.purpose)
	if isinstance(item_codes, str):
		item_codes = json.loads(item_codes or "[]")
	codes = [str(c) for c in (item_codes or [])][:30]
	return {"last_bought": pm.last_bought(codes)}


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
		f"""select i.name as item_code, i.item_name, i.item_group, i.stock_uom, {"i.custom_class" if has_class else "null"} as cls
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
		# "Xxx…" catch-all items: still findable, but flagged (never suggested)
		r["catch_all"] = 1 if pm.is_catch_all(r.item_name, r.pop("item_group", None)) else 0
	rows.sort(key=lambda r: r["catch_all"])
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
		rate_mode="paper", allow_duplicate=0, version=None, posting_date=None, bill_no=None, submit=0, charges=None):
	"""PO / SO: a draft (a PO optionally sent for approval). Receipt / Bill:
	a draft, or submitted when submit=1 — posting_date (a Bill: the bill date),
	bill_no and charges (indexes of the paper's freight lines to add) too."""
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
		if pp.is_purchase(purpose):
			return _save_purchase(paper, settings, warehouse, posting_date, bill_no, cint(submit), _charges_arg(charges),
				allow_duplicate)
		return _save(paper, settings, purpose, send_for_approval, warehouse, needed_by, school, rate_mode, allow_duplicate)
	finally:
		frappe.cache.delete(lock_key)


def _charges_arg(charges):
	if isinstance(charges, str):
		charges = json.loads(charges or "[]")
	return sorted({cint(i) for i in charges or [] if str(i).lstrip("-").isdigit()})


def _purchase_ready(paper, settings, warehouse, posting_date, bill_no, charges):
	"""Everything a Receipt / Bill needs before it can be built — shared by the
	preview and the save. Returns (state, data, party, keep, left, warehouse, date, bill_no)."""
	purpose = paper.purpose
	state = _state(paper)
	data = pr._json(paper.ai_json, {}) or {}
	party = state.get("party")
	if not party:
		frappe.throw(_("Choose the supplier first."))
	party = _party_ok("Supplier", party)
	if not state.get("links"):
		frappe.throw(_("Link the PO first, or choose \"No PO\"."))
	keep, left, pending = _lines_to_save(state, purpose)
	if pending:
		frappe.throw(_("Check {0} more line(s) first.").format(len(pending)))
	if not keep:
		frappe.throw(_("No lines to save — every line was left out."))
	for ln in keep:
		p = _qty_problem(ln) or pp.line_problem(ln, purpose)
		if p:
			frappe.throw(_("Line {0} ({1}): {2}.").format(ln["idx"], ln.get("item_name") or ln.get("text"), p))
	# the linked documents must still be open, with the same rows
	if (state["links"].get("mode")) == "docs":
		fresh = {d["name"]: d for d in pp.open_docs(purpose, party, paper.company)}
		for n in state["links"].get("docs") or []:
			if n not in fresh or not fresh[n]["linkable"]:
				frappe.throw(_("{0} is not open any more. Link again.").format(n))
		rows = {r["name"] for d in fresh.values() for r in d["rows"]}
		for ln in keep:
			if ln.get("doc_row") and ln["doc_row"]["name"] not in rows:
				frappe.throw(_("Line {0}: its row on {1} changed. Link again.").format(ln["idx"], ln["doc_row"]["parent"]))
	whs = _warehouses(paper.company)
	warehouse = warehouse or frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if warehouse not in whs:
		frappe.throw(_("Choose a warehouse of {0}.").format(paper.company))
	if purpose == pp.RECEIPT:
		date = getdate(nowdate())
	else:
		date = getdate(posting_date) if posting_date else None
		if not date:
			frappe.throw(_("Enter the bill date."))
		if date > getdate(nowdate()):
			frappe.throw(_("The bill date cannot be in the future."))
		if date < getdate(add_days(nowdate(), -400)):
			frappe.throw(_("The bill date is more than a year ago. Make this bill in the ERP."))
	bill_no = (bill_no if bill_no is not None else paper.paper_no or "").strip()[:140]
	if purpose == pp.BILL and not bill_no:
		frappe.throw(_("Enter the supplier's bill no."))
	if charges and not settings.get("freight_account"):
		frappe.throw(_("No account is set for freight. Ask the owner to set it in Settings."))
	return state, data, party, keep, left, warehouse, date, bill_no


def _purchase_check(paper, settings, state, data, party, keep, left, warehouse, date, bill_no, charges):
	"""(doc, numbers, draft_only reasons): the unsaved Receipt / Bill and its money check."""
	doc = pp.build_doc(paper, state, data, paper.purpose, party, keep, left, warehouse, date, bill_no, charges,
		settings.get("freight_account"))
	tot = pp.totals(state, data, paper.purpose, keep, left, charges)
	numbers = pp.preview_numbers(doc, data, tot)
	draft_only = []
	rep = pp.repeat_bill(paper.purpose, party, bill_no)
	if rep:
		draft_only.append(_("Bill no. {0} is already on {1}").format(bill_no, rep["name"]))
	filed = pp.filed_period(paper.company, date) if paper.purpose == pp.BILL else None
	if filed:
		draft_only.append(_("GSTR-3B for {0} is filed: the accountant decides on this bill").format(f"{filed[:2]}-{filed[2:]}"))
	return doc, numbers, tot, draft_only


@frappe.whitelist(methods=["POST"])
def preview_purchase(name, warehouse=None, posting_date=None, bill_no=None, charges=None):
	"""The save screen of a Receipt / Bill: ERPNext's own totals (GST as India
	Compliance sets it, freight, rounding) against the paper, and what leaves
	only "Save draft". Nothing is saved."""
	paper = _load(name)
	settings = _guard(paper.purpose)
	if not pp.is_purchase(paper.purpose):
		frappe.throw(_("Only a Receipt or a Bill has a preview."))
	_editable(paper)
	charges = _charges_arg(charges)
	args = _purchase_ready(paper, settings, warehouse, posting_date, bill_no, charges)
	state, data, party, keep, left = args[:5]
	doc, numbers, tot, draft_only = _purchase_check(paper, settings, *args, charges)
	new_mrp = [{"idx": ln["idx"], "item_name": ln.get("item_name"), "paper": flt(ln.get("mrp")), "ours": flt(ln.get("item_mrp"))}
		for ln in keep if pp._new_mrp(ln)] if frappe.get_meta(f"{paper.purpose} Item").has_field("custom_pack_mrp") and (
		paper.purpose == pp.RECEIPT or cint(doc.get("update_stock"))) else []
	return {
		"numbers": numbers, "totals": tot, "draft_only": draft_only, "update_stock": cint(doc.get("update_stock")) if paper.purpose == pp.BILL else 1,
		"lines": len(keep), "qty": sum(flt(ln.get("qty")) for ln in keep), "new_mrp": new_mrp,
		"taxes": [{"description": t.description or t.account_head, "amount": flt(t.tax_amount)} for t in doc.taxes if flt(t.tax_amount)],
	}


def _save_purchase(paper, settings, warehouse, posting_date, bill_no, submit, charges, allow_duplicate):
	purpose = paper.purpose
	args = _purchase_ready(paper, settings, warehouse, posting_date, bill_no, charges)
	state, data, party, keep, left, warehouse, date, bill_no = args
	doc, numbers, tot, draft_only = _purchase_check(paper, settings, *args, charges)
	if not numbers.get("ok"):
		if tot["missing_bill_lines"]:
			ln = tot["missing_bill_lines"][0]
			frappe.throw(_("Line {0} ({1}) is on the bill but not here. A bill must carry every line.").format(ln["idx"], ln["text"]))
		frappe.throw(_("The total is ₹{0} off the paper. Fix it first — nothing was saved.").format(_money(abs(numbers.get("diff") or 0))))
	if submit and draft_only:
		frappe.throw(_("Only a draft can be saved: {0}.").format("; ".join(draft_only)))
	dup = _duplicate(paper, party)
	if dup and not cint(allow_duplicate):
		return {"ok": 0, "duplicate": dup}

	doc.flags.kgs_paper_remark = doc.get("remarks") if doc.meta.has_field("remarks") else _("From paper {0}").format(paper.name)
	doc.insert()  # AS THE USER: normal permissions, ERPNext + India Compliance validations
	state["made_rows"] = {str(ln["idx"]): doc.items[i].name for i, ln in enumerate(keep) if i < len(doc.items)}
	_attach_pages(paper, doc)
	learned = learn_aliases(paper, party, keep)

	submit_error = None
	if submit:
		frappe.db.savepoint("kgs_paper_submit")
		try:
			doc.reload()
			doc.submit()
		except Exception as e:
			frappe.db.rollback(save_point="kgs_paper_submit")
			frappe.clear_messages()
			submit_error = re.sub(r"<[^>]+>", "", str(e) or "")[:500] or _("It could not be submitted.")
	paper.db_set({
		"status": "Saved", "created_doctype": purpose, "created_doc": doc.name, "party": party,
		"saved_by": frappe.session.user, "saved_on": now_datetime(), "lines_json": json.dumps(state),
	})
	out = _saved_response(paper)
	out["submit_error"] = submit_error
	out["learned"] = learned
	return out


@frappe.whitelist(methods=["POST"])
def make_bill(name, client_ref=None):
	"""After a submitted Receipt made from this paper: the Bill from the SAME
	reading — no second AI read, no cost. Its lines are the Receipt's rows."""
	src = _load(name, lock=True)
	_guard(pp.BILL)
	if src.purpose != pp.RECEIPT or src.status != "Saved" or src.created_doctype != pp.RECEIPT:
		frappe.throw(_("A bill is made from a paper that became a Receipt."))
	if src.get("bill_paper"):
		st = frappe.db.get_value("Order Paper", src.bill_paper, "status")
		if st and st != "Discarded":
			return {"name": src.bill_paper, "already": 1}
	pr_doc = frappe.db.get_value(pp.RECEIPT, src.created_doc, ["docstatus", "per_billed"], as_dict=True)
	if not pr_doc or pr_doc.docstatus != 1:
		frappe.throw(_("{0} is not submitted yet. The bill can be made once the office submits it.").format(src.created_doc))
	if flt(pr_doc.per_billed) >= 100:
		frappe.throw(_("{0} is already fully billed.").format(src.created_doc))
	state = _state(src)
	made = state.get("made_rows") or {}
	docs = [d for d in pp.open_docs(pp.BILL, src.party, src.company) if d["name"] == src.created_doc]
	if not docs:
		frappe.throw(_("{0} has nothing left to bill.").format(src.created_doc))
	rows = {r["name"]: r for r in docs[0]["rows"]}
	lines = []
	for ln in state["lines"]:
		ln = dict(ln)
		for k in ("doc_scores", "doc_row", "link_how", "link_pct", "over"):
			ln.pop(k, None)
		row = rows.get(made.get(str(ln["idx"])))
		if row:
			ln["pin_row"] = row["name"]  # this paper line became that Receipt row
			ln["by_person"], ln["decision"], ln["colour"] = 1, "ok", "green"
			ln["item_code"] = row["item_code"]
		elif ln.get("decision") != "left" and not (ln.get("colour") == "red" and not ln.get("by_person")):
			ln["decision"] = "left"  # was not on the Receipt
		lines.append(ln)
	new_state = {
		"v": 1, "party": src.party, "party_how": "receipt", "party_candidates": [], "notes": [
			_("Made from {0} with the same reading — no second AI read.").format(src.created_doc)],
		"discount_note": state.get("discount_note") or "", "lines": lines, "open_docs": docs,
		"links": {"mode": "docs", "doctype": pp.RECEIPT, "docs": [src.created_doc]},
	}
	paper = frappe.get_doc({
		"doctype": "Order Paper", "purpose": pp.BILL, "status": "Ready", "company": src.company, "party_type": "Supplier",
		"party": src.party, "client_ref": frappe.generate_hash(length=20) if not _CLIENT_REF_RE.match(client_ref or "") else client_ref,
		"page_count": src.page_count, "file_kind": src.file_kind, "ai_json": src.ai_json, "ai_model": src.ai_model,
		"ai_provider": src.ai_provider, "paper_party_text": src.paper_party_text, "paper_gstin": src.paper_gstin,
		"paper_no": src.paper_no, "paper_date": src.paper_date, "paper_kind": src.paper_kind, "source_paper": src.name,
		"usage_json": "[]", "state_version": 1,
	})
	compose_all(new_state, pp.BILL, "Supplier", 0)
	pp.doc_pcts(new_state, {})
	paper.lines_json = json.dumps(new_state)
	paper.insert(ignore_permissions=True)
	for f in pr.paper_files(src.name):
		frappe.get_doc({"doctype": "File", "file_url": f.file_url, "file_name": f.file_name, "is_private": 1,
			"attached_to_doctype": "Order Paper", "attached_to_name": paper.name}).insert(ignore_permissions=True)
	src.db_set("bill_paper", paper.name)
	return {"name": paper.name}


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
		"workflow_state": wf, "grand_total": flt(vals.get("grand_total")), "docstatus": cint(vals.get("docstatus")),
		"lines": len(keep), "qty": sum(flt(ln.get("qty")) for ln in keep),
		"left_out": [{"text": ln["text"], "qty": ln.get("qty")} for ln in left],
		"url": f"/app/{frappe.scrub(dt).replace('_', '-')}/{dn}",
		"owners": _owner_names() if dt == "Purchase Order" else [],
	}


def _saved_purchase_info(paper, state):
	"""The "Saved" screen of a Receipt / Bill: submitted or draft, links, what is
	still due on the PO, and whether the Bill can be made from this reading."""
	dt, dn = paper.created_doctype, paper.created_doc
	vals = frappe.db.get_value(dt, dn, ["docstatus", "grand_total", "per_billed"] if dt == pp.RECEIPT else ["docstatus", "grand_total"],
		as_dict=True) or {}
	links = state.get("links") or {}
	still_due = []
	if links.get("doctype") == pp.ORDER:
		for po in links.get("docs") or []:
			n = frappe.db.sql("""select count(*) from `tabPurchase Order Item` where parent = %s and qty > received_qty""", po)[0][0]
			if n:
				still_due.append({"doc": po, "lines": cint(n)})
	bill = None
	if dt == pp.RECEIPT:
		bp = paper.get("bill_paper")
		bp_status = frappe.db.get_value("Order Paper", bp, ["status", "created_doc"], as_dict=True) if bp else None
		can = cint(vals.get("docstatus")) == 1 and flt(vals.get("per_billed")) < 100 and can_make(pp.BILL)
		bill = {
			"paper": bp if bp_status and bp_status.status != "Discarded" else None,
			"doc": bp_status.created_doc if bp_status and bp_status.status != "Discarded" else None,
			"can": 1 if can and not (bp_status and bp_status.status != "Discarded") else 0,
			"waiting": 1 if cint(vals.get("docstatus")) == 0 else 0,
		}
	return {"created_docstatus": cint(vals.get("docstatus")), "created_total": flt(vals.get("grand_total")),
		"still_due": still_due, "bill": bill}


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
	"month_page_limit", "peak_month_page_limit", "usd_rate", "gst_percent", "pr_pi_enabled", "freight_account")


def _receiver_rows(users):
	rows = frappe.get_all("User", filters={"name": ["in", list(users) or [""]]}, fields=["name", "full_name", "enabled"])
	by = {r.name: r for r in rows}
	return [{"user": u, "full_name": (by[u].full_name if u in by else u) or u, "enabled": cint(by[u].enabled) if u in by else 0}
		for u in users]


def _freight_accounts():
	company = _company()
	return frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "disabled": 0, "root_type": "Expense"},
		order_by="account_name asc", pluck="name", limit_page_length=300,
	)


@frappe.whitelist(methods=["POST"])
def search_receivers(txt=""):
	"""Settings: enabled desk users with Purchase User / Manager, for the list of
	people who may make Receipts and Bills."""
	_guard_settings()
	users = set(frappe.get_all("Has Role", filters={"role": ["in", list(PAPER_PO_ROLES)], "parenttype": "User"}, pluck="parent"))
	filters = {"name": ["in", list(users) or [""]], "enabled": 1, "user_type": "System User"}
	or_filters = None
	if txt:
		or_filters = {"name": ["like", f"%{txt}%"], "full_name": ["like", f"%{txt}%"]}
	return frappe.get_all("User", filters=filters, or_filters=or_filters, fields=["name as user", "full_name"],
		order_by="full_name asc", limit_page_length=30)


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
		"receivers": _receiver_rows(s.receivers or []),
		"freight_accounts": _freight_accounts(),
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
	if isinstance(values.get("receivers"), list):
		doc.set("receivers", [])
		for u in values["receivers"][:50]:
			u = str((u or {}).get("user") if isinstance(u, dict) else u or "").strip()
			if u:
				if not frappe.db.exists("User", u):
					frappe.throw(_("User {0} not found.").format(u))
				doc.append("receivers", {"user": u})
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
