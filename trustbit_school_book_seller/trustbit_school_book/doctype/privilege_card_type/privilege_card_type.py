import frappe
from frappe.model.document import Document


class PrivilegeCardType(Document):
    def validate(self):
        if self.discount_percent and self.discount_percent < 0:
            frappe.throw("Discount % cannot be negative")
        if self.discount_percent and self.discount_percent > 100:
            frappe.throw("Discount % cannot exceed 100")
