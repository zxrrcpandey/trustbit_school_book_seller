# Copyright (c) 2024, Trustbit and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ClassMaster(Document):
    def validate(self):
        # Convert short_code to uppercase
        if self.short_code:
            self.short_code = self.short_code.upper().strip()
    
    def before_save(self):
        # Remove extra spaces from class name
        if self.class_name:
            self.class_name = self.class_name.strip()
