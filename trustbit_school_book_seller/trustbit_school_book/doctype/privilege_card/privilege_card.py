import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today, flt


class PrivilegeCard(Document):
    def validate(self):
        self.validate_discount()
        self.validate_dates()
        self.check_expiry()

    def validate_discount(self):
        if flt(self.discount_percent) < 0:
            frappe.throw(_("Discount % cannot be negative"))
        if flt(self.discount_percent) > 100:
            frappe.throw(_("Discount % cannot exceed 100"))

    def validate_dates(self):
        if self.expiry_date and self.issue_date:
            if getdate(self.expiry_date) < getdate(self.issue_date):
                frappe.throw(_("Expiry Date cannot be before Issue Date"))

    def check_expiry(self):
        if (
            self.expiry_date
            and self.status == "Active"
            and getdate(self.expiry_date) < getdate(today())
        ):
            self.status = "Expired"
            frappe.msgprint(
                _("Card {0} has been marked as Expired (past expiry date)").format(self.name),
                alert=True,
                indicator="orange",
            )

    def after_insert(self):
        if not self.barcode:
            self.db_set("barcode", self.name)
