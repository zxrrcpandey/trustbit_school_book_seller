# Copyright (c) 2026, Trustbit Software and contributors
# Order from Paper — matching a line read from a paper to OUR item.
#
# Order (first hit wins; PLAN_order_from_paper.md §7):
#   1. code remembered for this party                      → green
#   2. wording remembered for this party                   → green (amber: item disabled / MRP changed)
#   3. ISBN / barcode printed (Item Barcode → ISBN field)  → green
#   4. our item code, or the party's own code that ERPNext
#      already knows (Item Supplier / Item Customer Detail) → green
#   5. wording remembered for ANOTHER party                → amber, preselected
#   6. smart search over our item names (+ AI double-check) → amber, best 3
#   7. nothing close                                       → red
# Fuzzy and AI results never turn green by themselves: only a line a person
# confirmed is learned (staff_app/paper.py → learn_aliases).
#
# The word index (6) is built only inside the background read job — never in a
# web worker (DANGER 21: no catalogue loads on the 3 POS web workers). Party-
# dependent layers (1, 2, 4, 5) are plain indexed lookups, so changing the
# supplier on the check screen re-matches without the index.

import math
import re
from bisect import bisect_left
from collections import defaultdict

import frappe
from frappe.utils import cint, flt, getdate, nowdate

PRESELECT = 0.55  # fuzzy score from which the best item is preselected (amber)
SUGGEST = 0.30  # below this a candidate is not even shown
CANDIDATES_KEPT = 10  # stored per line (the AI double-check chooses among these)
SHOWN = 3

# ── normalising ──────────────────────────────────────────────────────────────

_PRICE_RE = re.compile(r"(?:RS\.?|INR|MRP|₹)\s*\d+(?:[.,]\d+)?|\d+(?:\.\d+)?\s*/\s*-")
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_ORDINAL = re.compile(r"^(\d{1,2})(ST|ND|RD|TH)$")
_JOINED_CLASS = re.compile(r"^(?:CLASS|CL|STD|GRADE|GR)(\d{1,2})$")

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
_ROMAN_ALONE = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}  # V / X / I only after CLASS
_CLASS_KW = {"CLASS", "CL", "STD", "STANDARD", "GRADE", "GR", "KAKSHA", "CLAS"}
_NOT_CLASS_BEFORE = {"PART", "PT", "VOL", "VOLUME", "BHAG", "NO","SET", "PAGE", "PAGES", "PG", "UNIT", "LEVEL", "STEP", "PAPER", "SEM", "SEMESTER", "TERM", "CHAPTER", "CH"}
_NOT_CLASS_AFTER = {"PCS", "PC", "PAGE", "PAGES", "PG", "GSM", "ML", "GM", "GMS", "MM", "CM", "INCH", "SHEET", "SHEETS", "COLOUR", "COLOURS", "COLOR", "COLORS", "SHADES", "PKT", "NOS", "IN", "YEARS", "YRS", "Y", "MONTH", "QR", "QUIRE", "LINE", "LINES", "RULED", "SUBJECT", "SUBJECTS", "FLAP", "PLY"}
_PRE_PRIMARY = {
	"NUR": "NUR", "NURSERY": "NUR", "NURSARY": "NUR", "NURSRY": "NUR",
	"PRENUR": "PRE-NUR", "PRENURSERY": "PRE-NUR", "PLAYGROUP": "PRE-NUR", "PLAYWAY": "PRE-NUR",
	"LKG": "LKG", "KG1": "LKG", "KGI": "LKG", "JRKG": "LKG",
	"UKG": "UKG", "KG2": "UKG", "KGII": "UKG", "SRKG": "UKG",
}
_PRE_PRIMARY_BIGRAMS = {("PRE", "NUR"): "PRE-NUR", ("PRE", "NURSERY"): "PRE-NUR", ("KG", "1"): "LKG", ("KG", "I"): "LKG",
	("KG", "2"): "UKG", ("KG", "II"): "UKG", ("JR", "KG"): "LKG", ("SR", "KG"): "UKG", ("PLAY", "GROUP"): "PRE-NUR"}

# Both sides (paper text and our item names) go through the same mapping, so
# the direction never matters — only that the short forms meet.
_SYN = {
	"MATHEMATIC": "MATH", "MATHS": "MATH", "MTH": "MATH", "MATHEMATICS": "MATH", "GANIT": "MATH",
	"ENG": "ENGLISH", "ENGL": "ENGLISH", "ENGLIS": "ENGLISH",
	"HIN": "HINDI", "HND": "HINDI",
	"SCI": "SCIENCE", "SCIENC": "SCIENCE",
	"COMP": "COMPUTER", "COMPUTR": "COMPUTER", "COMPUT": "COMPUTER",
	"DICT": "DICTIONARY", "DICTIONARIE": "DICTIONARY", "DICTIONERY": "DICTIONARY",
	"ADV": "ADVANTAGE",
	"PT": "PART", "BHAG": "PART",
	"BK": "BOOK",
	"WB": "WORKBOOK", "WRKBK": "WORKBOOK",
	"QUESBANK": "QB",
	"VYAKRAN": "VYAKARAN", "VYAKARN": "VYAKARAN", "VYAKRN": "VYAKARAN",
	"SANS": "SANSKRIT", "SKT": "SANSKRIT",
	"ENV": "EVS", "ENVIRONMENTAL": "EVS", "ENVIRONMENT": "EVS",
	"SST": "SOCIAL", "SOC": "SOCIAL",
	"GEN": "GENERAL",
	"NB": "NOTEBOOK",
	"REG": "REGISTER", "REGR": "REGISTER", "REGI": "REGISTER", "REGIST": "REGISTER",
	"DRAW": "DRAWING",
	"LIT": "LITERATURE",
	"GRAM": "GRAMMAR", "GRAMMER": "GRAMMAR",
	"READR": "READER", "RDR": "READER",
	"PRAC": "PRACTICE", "PRACT": "PRACTICE",
	"COLOUR": "COLOR", "COLOURING": "COLORING", "COLOURFUL": "COLORFUL",
	"CURSIV": "CURSIVE",
}
_BIGRAMS = {("WORK", "BOOK"): "WORKBOOK", ("NOTE", "BOOK"): "NOTEBOOK", ("QUESTION", "BANK"): "QB", ("QUES", "BANK"): "QB",
	("GENERAL", "KNOWLEDGE"): "GK", ("S", "ST"): "SOCIAL", ("TEXT", "BOOK"): "TEXTBOOK", ("E", "V", "S"): "EVS"}
_STOP = {"THE", "OF", "AND", "FOR", "WITH", "TO", "IN", "BY", "ON", "A", "AN", "NEW", "ED", "EDN", "EDITION", "REVISED",
	"LATEST", "RS", "INR", "MRP", "PRICE", "NO", "PCS", "PC", "NOS", "QTY", "SERIES"} | _CLASS_KW

_UNITS = {
	"PC": "PCS", "PCS": "PCS", "PIECE": "PCS", "PIECES": "PCS", "PCE": "PCS",
	"NO": "NOS", "NOS": "NOS", "NUMBER": "NOS", "NUMBERS": "NOS",
	"EA": "EACH", "EACH": "EACH", "UNIT": "EACH", "UNITS": "EACH",
	"COPY": "PCS", "COPIES": "PCS", "BOOK": "PCS", "BOOKS": "PCS",
	"PKT": "PKT", "PKTS": "PKT", "PACKET": "PKT", "PACKETS": "PKT", "PACK": "PKT", "PCK": "PKT",
	"BOX": "BOX", "BOXES": "BOX", "BX": "BOX",
	"SET": "SET", "SETS": "SET",
	"DOZ": "DOZEN", "DOZEN": "DOZEN", "DZ": "DOZEN", "DZN": "DOZEN",
	"BUNDLE": "BUNDLE", "BDL": "BUNDLE", "BUNDLES": "BUNDLE",
	"REAM": "REAM", "REAMS": "REAM",
	"GROSS": "GROSS",
}
_PIECE_LIKE = {"PCS", "NOS", "EACH"}


def _upper(s):
	return str(s or "").upper()


def strip_prices(text):
	return _PRICE_RE.sub(" ", _upper(text))


def _raw_tokens(text):
	return _NON_ALNUM.sub(" ", strip_prices(text)).split()


def _join_letters(toks):
	"""G K → GK, C P → CP: dotted short forms ("G.K.", "C & P") as one word."""
	out, run = [], []
	for t in toks:
		if len(t) == 1 and t.isalpha() and t not in ("I", "V", "X"):
			run.append(t)
			continue
		if run:
			out.append("".join(run) if len(run) > 1 else run[0])
			run = []
		out.append(t)
	if run:
		out.append("".join(run) if len(run) > 1 else run[0])
	return out


def _bigrams(toks):
	out, i = [], 0
	while i < len(toks):
		for n in (3, 2):
			key = tuple(toks[i : i + n])
			if len(key) == n and key in _BIGRAMS:
				out.append(_BIGRAMS[key])
				i += n
				break
		else:
			out.append(toks[i])
			i += 1
	return out


def _stem(t):
	if len(t) >= 4 and t.endswith("S") and not t.endswith(("SS", "US", "IS")) and not t.isdigit():
		return t[:-1]
	return t


def tokens(text):
	"""Normalised word list: capitals, no punctuation or printed prices, short
	forms joined/expanded, plural S dropped, class written as digits
	(CLASS III / 3RD → 3), class keywords and filler words removed."""
	toks = _bigrams(_join_letters(_raw_tokens(text)))
	out = []
	prev_kw = False
	for t in toks:
		m = _ORDINAL.match(t) or _JOINED_CLASS.match(t)
		if m:
			out.append(str(int(m.group(1))))
			prev_kw = False
			continue
		if prev_kw and t in _ROMAN:
			out.append(str(_ROMAN[t]))
			prev_kw = False
			continue
		prev_kw = t in _CLASS_KW
		t = _stem(t)
		t = _SYN.get(t, t)
		if t in _STOP:
			continue
		out.append(t)
	return out


def match_key(text):
	"""Key of a remembered WORDING (key_type Text). Numbers stay in (class 4 ≠
	class 5); printed prices do not (next year's MRP must still match)."""
	return " ".join(tokens(text))[:140]


def code_key(code):
	"""Key of a remembered CODE: capitals and digits only, "AB-12/3" = "AB123"."""
	k = _NON_ALNUM.sub("", _upper(code))
	return k[:140] if len(k) >= 2 else ""


def isbn_variants(value):
	"""Barcode strings worth looking up for a printed ISBN / EAN / barcode."""
	raw = re.sub(r"[\s-]", "", _upper(value))
	if not raw:
		return []
	out = {raw}
	digits = re.sub(r"[^0-9X]", "", raw)
	if len(digits) == 10 and digits[:9].isdigit():
		core = "978" + digits[:9]
		check = (10 - sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(core)) % 10) % 10
		out.add(core + str(check))
		out.add(digits)
	elif len(digits) == 13 and digits.isdigit():
		out.add(digits)
		if digits.startswith("978"):
			core = digits[3:12]
			s = sum((10 - i) * int(c) for i, c in enumerate(core))
			c10 = (11 - s % 11) % 11
			out.add(core + ("X" if c10 == 10 else str(c10)))
	elif digits.isdigit() and 8 <= len(digits) <= 14:
		out.add(digits)
	return [v for v in out if len(v) >= 8]


def canonical_unit(unit):
	u = _NON_ALNUM.sub("", _upper(unit))
	if not u:
		return ""
	if u in _UNITS:
		return _UNITS[u]
	if len(u) > 3 and u.endswith("S") and u[:-1] in _UNITS:
		return _UNITS[u[:-1]]
	return u


def class_of(text):
	"""The class / grade a text is about: "1".."12", "NUR", "PRE-NUR", "LKG",
	"UKG" — or None. An explicit CLASS/STD keyword wins; then 3RD/10TH; then
	pre-primary words; then the LAST plain number 1–12 (KGS names end with the
	class: "Golden Maple Maths Maniya 4"), skipping PART 2 / 100 PAGES / 4.0."""
	src = strip_prices(text)
	toks = _NON_ALNUM.sub(" ", src).split()
	for i, t in enumerate(toks):
		m = _JOINED_CLASS.match(t)
		if m and 1 <= int(m.group(1)) <= 12:
			return str(int(m.group(1)))
		if t in _CLASS_KW and i + 1 < len(toks):
			n = toks[i + 1]
			m2 = _ORDINAL.match(n)
			if m2:
				n = m2.group(1)
			if n.isdigit() and 1 <= int(n) <= 12:
				return str(int(n))
			if n in _ROMAN:
				return str(_ROMAN[n])
	for t in toks:
		m = _ORDINAL.match(t)
		if m and 1 <= int(m.group(1)) <= 12:
			return str(int(m.group(1)))
	joined = _join_letters(toks)
	for i, t in enumerate(joined):
		if t in _PRE_PRIMARY:
			return _PRE_PRIMARY[t]
		for n in (2,):
			key = tuple(joined[i : i + n])
			if key in _PRE_PRIMARY_BIGRAMS:
				return _PRE_PRIMARY_BIGRAMS[key]
	decimals = set()
	for m in re.finditer(r"(\d+)\.(\d+)", src):
		decimals.update({m.group(1), m.group(2)})
	found = None
	for i, t in enumerate(toks):
		before = toks[i - 1] if i else ""
		after = toks[i + 1] if i + 1 < len(toks) else ""
		if before in _NOT_CLASS_BEFORE or after in _NOT_CLASS_AFTER:
			continue
		if t.isdigit() and 1 <= int(t) <= 12 and t not in decimals and not t.startswith("0"):
			found = str(int(t))
		elif t in _ROMAN_ALONE:
			found = str(_ROMAN[t])
	return found


_SEMESTER = re.compile(r"^(\d{1,2})\s*-\s*([12])$")
_RANGE = re.compile(r"^\d{1,2}\s*(?:&|-|/|TO|AND)\s*\d{1,2}$")


def item_class(custom_class, item_name):
	"""Class of one of OUR items: the Item's class field when it holds a class
	("3", "LKG", "Nursery", "Class 10th"), else read from the item name. A
	range ("11 & 12", "9-10") is no single class → None (no class guard)."""
	c = str(custom_class or "").strip()
	if c and c not in (".", "-", "0"):
		up = c.upper()
		if up.isdigit() and 1 <= int(up) <= 12:
			return str(int(up))
		m = _SEMESTER.match(up)
		if m and int(m.group(1)) > 2:
			return str(int(m.group(1)))
		if _RANGE.match(up):
			return None
		got = class_of(c if not up.isdigit() else "")
		if got:
			return got
	return class_of(item_name)


def price_in_name(name):
	m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*-", str(name or ""))
	return flt(m.group(1)) if m else 0.0


def same_money(a, b):
	a, b = flt(a), flt(b)
	return a > 0 and b > 0 and abs(a - b) <= max(0.5, 0.005 * max(a, b))


# ── the word index (background job only) ─────────────────────────────────────


class ItemIndex:
	"""IDF-weighted word index over our item names + codes."""

	def __init__(self, items):
		# items: [{item_code, item_name, cls, mrp, name_mrp}]
		self.items = items
		self.toks = []
		df = defaultdict(int)
		self.postings = defaultdict(list)
		for i, it in enumerate(items):
			ts = {t for t in tokens(f"{it['item_name']} {it['item_code']}") if _scorable(t)}
			self.toks.append(ts)
			for t in ts:
				df[t] += 1
				self.postings[t].append(i)
		n = max(1, len(items))
		self.n = n
		self.idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
		self.vocab = sorted(self.idf)
		self.common = 0.25 * n
		self.median_idf = sorted(self.idf.values())[len(self.idf) // 2] if self.idf else 1.0

	def _expand(self, t):
		"""Our words that start with an abbreviation from the paper (≥ 3 letters)."""
		if len(t) < 3 or not t.isalpha():
			return []
		i = bisect_left(self.vocab, t)
		out = []
		while i < len(self.vocab) and self.vocab[i].startswith(t) and len(out) < 30:
			if self.vocab[i] != t:
				out.append(self.vocab[i])
			i += 1
		return out

	def search(self, text, line_class=None, mrp=None, limit=CANDIDATES_KEPT):
		line = [t for t in dict.fromkeys(tokens(text)) if _scorable(t)]
		if not line:
			return []
		weights, acc = {}, defaultdict(float)
		for t in line:
			if t in self.idf:
				weights[t] = self.idf[t]
				post = self.postings[t]
				if len(post) <= self.common:
					for i in post:
						acc[i] += weights[t]
			else:
				exp = self._expand(t)
				weights[t] = max((self.idf[e] for e in exp), default=self.median_idf) if exp else self.median_idf
				seen = set()
				for e in exp:
					for i in self.postings[e]:
						if i not in seen:
							seen.add(i)
							acc[i] += 0.8 * weights[t]
		if not acc:  # only very common words ("ENGLISH BOOK") — use them after all
			for t in line:
				for i in self.postings.get(t, ())[:5000]:
					acc[i] += weights[t]
		if not acc:
			return []
		pool = sorted(acc, key=acc.get, reverse=True)[:60]
		total_w = sum(weights.values()) or 1.0
		out = []
		for i in pool:
			it, its = self.items[i], self.toks[i]
			matched = 0.0
			for t in line:
				if t in its:
					matched += weights[t]
				elif len(t) >= 3 and any(len(u) >= 3 and (u.startswith(t) or t.startswith(u)) for u in its):
					matched += 0.8 * weights[t]
			item_w = sum(self.idf.get(u, 0) for u in its) or 1.0
			item_hit = sum(self.idf.get(u, 0) for u in its if u in line or any(
				len(u) >= 3 and len(t) >= 3 and (u.startswith(t) or t.startswith(u)) for t in line))
			score = 0.7 * (matched / total_w) + 0.3 * (item_hit / item_w)
			mismatch = bool(line_class and it["cls"] and line_class != it["cls"])
			if line_class and it["cls"] == line_class:
				score += 0.10
			mrp_match = bool(mrp and (same_money(mrp, it["mrp"]) or same_money(mrp, it["name_mrp"])))
			if mrp_match:
				score += 0.12
			elif mrp and (it["mrp"] or it["name_mrp"]):
				score -= 0.05
			order = score * (0.6 if mismatch else 1.0)
			out.append({
				"item_code": it["item_code"], "item_name": it["item_name"], "cls": it["cls"],
				"mrp": it["mrp"] or it["name_mrp"], "score": round(min(score, 1.2), 3),
				"class_mismatch": 1 if mismatch else 0, "mrp_match": 1 if mrp_match else 0, "_o": order,
			})
		out.sort(key=lambda c: c["_o"], reverse=True)
		for c in out:
			c.pop("_o")
		return [c for c in out if c["score"] >= SUGGEST][:limit]


def _scorable(t):
	return len(t) >= 2 and not t.isdigit() and t not in _ROMAN and t not in _STOP


def selling_price_list():
	return frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"


def selling_prices(item_codes=None):
	"""{item_code: current selling rate} — the latest valid price row (an older
	row without valid_from loses to a newer dated one, like get_item_price)."""
	today = getdate(nowdate())
	cond, values = "", {"pl": selling_price_list(), "today": today}
	if item_codes is not None:
		if not item_codes:
			return {}
		cond = " and item_code in %(codes)s"
		values["codes"] = tuple(item_codes)
	rows = frappe.db.sql(
		f"""select item_code, price_list_rate, valid_from from `tabItem Price`
		where price_list = %(pl)s and selling = 1 and ifnull(customer, '') = ''
			and (valid_from is null or valid_from <= %(today)s)
			and (valid_upto is null or valid_upto >= %(today)s){cond}
		order by item_code, ifnull(valid_from, '1900-01-01'), modified""",
		values,
		as_dict=True,
	)
	out = {}
	for r in rows:
		out[r.item_code] = flt(r.price_list_rate)
	return out


def load_index():
	has_class = frappe.db.has_column("Item", "custom_class")
	rows = frappe.db.sql(
		f"""select name, item_name, {"custom_class" if has_class else "null"} as cls
		from `tabItem` where disabled = 0 and has_variants = 0""",
		as_dict=True,
	)
	prices = selling_prices()
	items = [
		{"item_code": r.name, "item_name": r.item_name or r.name, "cls": item_class(r.cls, r.item_name),
			"mrp": prices.get(r.name, 0.0), "name_mrp": price_in_name(r.item_name)}
		for r in rows
	]
	return ItemIndex(items)


# ── exact layers (indexed lookups; safe in a web request) ────────────────────


def _in(values):
	return tuple(values) or ("",)


def exact_layers(lines, party_type, party):
	"""{idx: {"how", "item_code", "note", "alias", "other_party", "alias_mrp", "alias_uom", ...}}
	for every line that a non-fuzzy layer can place."""
	codes, texts, barcodes = {}, {}, {}
	for ln in lines:
		ck = code_key(ln.get("code"))
		if ck:
			codes[ln["idx"]] = ck
		tk = match_key(ln.get("text"))
		if tk:
			texts[ln["idx"]] = tk
		vs = isbn_variants(ln.get("isbn")) or (isbn_variants(ln.get("code")) if re.fullmatch(r"[\d\s-]{8,17}X?", str(ln.get("code") or "")) else [])
		if vs:
			barcodes[ln["idx"]] = vs
	out = {}

	party_rows = []
	if party:
		party_rows = frappe.db.sql(
			"""select name, key_type, match_key, item_code, paper_unit, uom, conversion_factor, mrp, times_used
			from `tabParty Item Alias` where party_type = %s and party = %s and match_key in %s""",
			(party_type, party, _in(set(codes.values()) | set(texts.values()))),
			as_dict=True,
		)
	by_code = {r.match_key: r for r in party_rows if r.key_type == "Code"}
	by_text = {r.match_key: r for r in party_rows if r.key_type == "Text"}

	own_codes = {}
	if party and codes:
		if party_type == "Supplier":
			rows = frappe.db.sql("""select parent, supplier_part_no as c from `tabItem Supplier`
				where supplier = %s and ifnull(supplier_part_no, '') != '' and parenttype = 'Item'""", party, as_dict=True)
		else:
			rows = frappe.db.sql("""select parent, ref_code as c from `tabItem Customer Detail`
				where customer_name = %s and ifnull(ref_code, '') != '' and parenttype = 'Item'""", party, as_dict=True)
		for r in rows:
			own_codes.setdefault(code_key(r.c), r.parent)

	bc_hits = {}
	all_bc = {v for vs in barcodes.values() for v in vs}
	if all_bc:
		for r in frappe.db.sql("select barcode, parent from `tabItem Barcode` where barcode in %s", (_in(all_bc),), as_dict=True):
			bc_hits.setdefault(r.barcode, r.parent)
		if frappe.db.has_column("Item", "custom_isbn_barcode"):
			for r in frappe.db.sql("select custom_isbn_barcode as b, name from `tabItem` where custom_isbn_barcode in %s",
					(_in(all_bc),), as_dict=True):
				bc_hits.setdefault(r.b, r.name)

	raw_codes = {ln["idx"]: str(ln.get("code") or "").strip().upper() for ln in lines if str(ln.get("code") or "").strip()}
	our_codes = set()
	if raw_codes:
		our_codes = set(frappe.db.sql_list("select name from `tabItem` where name in %s", (_in(raw_codes.values()),)))

	others = defaultdict(list)
	if texts:
		for r in frappe.db.sql(
			"""select match_key, item_code, party_type, party, times_used from `tabParty Item Alias`
			where key_type = 'Text' and match_key in %s and not (party_type = %s and party = %s)
			order by times_used desc, modified desc""",
			(_in(set(texts.values())), party_type or "", party or ""),
			as_dict=True,
		):
			others[r.match_key].append(r)

	for ln in lines:
		i = ln["idx"]
		hit = None
		if i in codes and codes[i] in by_code:
			r = by_code[codes[i]]
			hit = {"how": "alias_code", "item_code": r.item_code, "alias": r.name, "alias_mrp": flt(r.mrp),
				"alias_unit": r.paper_unit, "alias_uom": r.uom, "alias_factor": flt(r.conversion_factor)}
		elif i in texts and texts[i] in by_text:
			r = by_text[texts[i]]
			hit = {"how": "alias_text", "item_code": r.item_code, "alias": r.name, "alias_mrp": flt(r.mrp),
				"alias_unit": r.paper_unit, "alias_uom": r.uom, "alias_factor": flt(r.conversion_factor)}
		elif i in barcodes and any(v in bc_hits for v in barcodes[i]):
			hit = {"how": "barcode", "item_code": next(bc_hits[v] for v in barcodes[i] if v in bc_hits)}
		elif i in raw_codes and raw_codes[i] in our_codes:
			hit = {"how": "item_code", "item_code": raw_codes[i]}
		elif i in codes and codes[i] in own_codes:
			hit = {"how": "party_code", "item_code": own_codes[codes[i]]}
		elif i in texts and others.get(texts[i]):
			r = others[texts[i]][0]
			hit = {"how": "other_party", "item_code": r.item_code, "other_party": r.party, "other_party_type": r.party_type}
		if hit:
			out[i] = hit
	return out


# ── items: everything the check screen shows about one of ours ───────────────


def item_details(item_codes):
	codes = list(dict.fromkeys(c for c in item_codes if c))
	if not codes:
		return {}
	has_class = frappe.db.has_column("Item", "custom_class")
	rows = frappe.db.sql(
		f"""select name, item_name, disabled, has_variants, stock_uom, last_purchase_rate,
			{"custom_class" if has_class else "null"} as cls
		from `tabItem` where name in %s""",
		(tuple(codes),),
		as_dict=True,
	)
	conv = defaultdict(list)
	for c in frappe.db.sql(
		"""select parent, uom, conversion_factor from `tabUOM Conversion Detail`
		where parenttype = 'Item' and parent in %s order by idx""",
		(tuple(codes),),
		as_dict=True,
	):
		conv[c.parent].append(c)
	all_uoms = {r.stock_uom for r in rows} | {c.uom for cs in conv.values() for c in cs}
	whole = set(frappe.get_all("UOM", filters={"name": ["in", list(all_uoms)], "must_be_whole_number": 1}, pluck="name")) if all_uoms else set()
	prices = selling_prices([r.name for r in rows])
	out = {}
	for r in rows:
		uoms = [{"uom": r.stock_uom, "factor": 1.0, "whole": 1 if r.stock_uom in whole else 0}]
		for c in conv[r.name]:
			if c.uom and c.uom != r.stock_uom and flt(c.conversion_factor) > 0:
				uoms.append({"uom": c.uom, "factor": flt(c.conversion_factor), "whole": 1 if c.uom in whole else 0})
		out[r.name] = {
			"item_code": r.name, "item_name": r.item_name, "disabled": cint(r.disabled), "has_variants": cint(r.has_variants),
			"stock_uom": r.stock_uom, "uoms": uoms, "cls": item_class(r.cls, r.item_name),
			"mrp": prices.get(r.name, 0.0) or price_in_name(r.item_name), "last_purchase_rate": flt(r.last_purchase_rate),
		}
	return out


def pick_uom(item, paper_unit, alias=None):
	"""Our unit for the paper's unit: the remembered one, else a unit of the item
	with the same name, else the stock unit for piece-like / blank units.
	Returns (uom, factor, known)."""
	pu = canonical_unit(paper_unit)
	if alias and alias.get("alias_uom") and (not pu or pu == canonical_unit(alias.get("alias_unit"))):
		for u in item["uoms"]:
			if u["uom"] == alias["alias_uom"]:
				return u["uom"], u["factor"], True
	if not pu:
		return item["stock_uom"], 1.0, True
	for u in item["uoms"]:
		if canonical_unit(u["uom"]) == pu:
			return u["uom"], u["factor"], True
	if pu in _PIECE_LIKE and canonical_unit(item["stock_uom"]) in _PIECE_LIKE:
		return item["stock_uom"], 1.0, True
	return item["stock_uom"], 1.0, False
