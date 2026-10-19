# Copyright (c) 2026, Trustbit Software and contributors
# "Remembered name" — see staff_app/paper_match.py. The name is a hash of
# (party_type, party, key_type, match_key), so one party can never hold two
# rows for the same wording and two phones learning it at once cannot race.

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document

# Who may change or delete a remembered name, per party type (desk and app alike).
EDITOR_ROLES = {
	"Supplier": ("Purchase Manager", "System Manager"),
	"Customer": ("Sales Manager", "System Manager"),
}


def alias_name(party_type, party, key_type, match_key):
	raw = f"{party_type}|{party}|{key_type}|{match_key}".encode()
	return "PIA-" + hashlib.sha1(raw).hexdigest()[:20]


def can_edit(party_type, user=None):
	roles = set(frappe.get_roles(user))
	return bool(roles & set(EDITOR_ROLES.get(party_type, ("System Manager",))))


class PartyItemAlias(Document):
	def autoname(self):
		self.name = alias_name(self.party_type, self.party, self.key_type, self.match_key)

	def validate(self):
		if self.party_type not in EDITOR_ROLES:
			frappe.throw(_("Remembered names are for Suppliers and Customers only."))
		# learning from a confirmed line runs as the clerk (flag set by staff_app/paper.py)
		if not frappe.flags.kgs_paper_learning and not can_edit(self.party_type):
			frappe.throw(_("Only a {0} can change remembered names of a {1}.").format(
				" / ".join(EDITOR_ROLES[self.party_type][:1]), _(self.party_type)), frappe.PermissionError)
		if frappe.db.get_value("Item", self.item_code, "has_variants"):
			frappe.throw(_("{0} is a template item. Choose the actual item.").format(self.item_code))

	def on_trash(self):
		if not can_edit(self.party_type):
			frappe.throw(_("Only a manager can delete remembered names."), frappe.PermissionError)
