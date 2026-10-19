# Copyright (c) 2026, Trustbit Software and contributors
# Read by every paper job (staff_app/paper_read.get_settings), so a change here
# applies from the next read without a restart. The AI key is deliberately NOT
# a field: it stays in site_config (kgs_paper_ai_key) and never reaches a browser.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class OrderPaperSettings(Document):
	def validate(self):
		from trustbit_school_book_seller.staff_app.paper_read import DEFAULT_PRICES, PROVIDERS

		if not self.model_prices:
			for row in DEFAULT_PRICES:
				self.append("model_prices", row)
		seen = set()
		for row in self.model_prices:
			row.model = (row.model or "").strip()
			if row.model in seen:
				frappe.throw(_("Model {0} is listed twice in the price table.").format(row.model))
			seen.add(row.model)
			if flt(row.input_per_mtok) < 0 or flt(row.output_per_mtok) < 0:
				frappe.throw(_("Prices cannot be negative ({0}).").format(row.model))
		if self.provider not in PROVIDERS:
			frappe.throw(_("{0} is coming soon. Choose Anthropic for now.").format(self.provider))
		self.ai_model = (self.ai_model or "").strip()
		self.fallback_model = (self.fallback_model or "").strip()
		if self.ai_model not in seen:
			frappe.throw(_("Model {0} has no row in the price table. Add its price first.").format(self.ai_model))
		if cint(self.auto_fallback) and self.fallback_model and self.fallback_model not in seen:
			frappe.throw(_("Better model {0} has no row in the price table.").format(self.fallback_model))
		for f in ("month_page_limit", "peak_month_page_limit"):
			if cint(self.get(f)) < 0:
				self.set(f, 0)
		if flt(self.usd_rate) <= 0:
			self.usd_rate = 100
		if flt(self.gst_percent) < 0:
			self.gst_percent = 0
