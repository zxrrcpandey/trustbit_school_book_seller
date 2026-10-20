"""One-time setup of a THROWAWAY local site for the Receipt / Bill tests
(check_paper_purchase.py): a KGS-like company with a GSTIN, India Compliance's
GST templates, suppliers in-state / out-state / unregistered with addresses,
books (HSN 4901, nil GST) and stationery (18%), and production's buying /
stock / accounts settings (read from splashbox.in on 2026-10-20).

The site needs erpnext, india_compliance, trustbit_school_pro and
trustbit_school_book_seller installed and the setup wizard NOT yet run.
Run from frappe-bench/sites:
    ../env/bin/python ../apps/trustbit_school_book_seller/trustbit_school_book_seller/staff_app/dev_tests/setup_paper_purchase_site.py paper.local
Never run it against a real site."""
import sys

import frappe

SITE = sys.argv[1] if len(sys.argv) > 1 else "paper.local"
if SITE in ("splashbox.in", "site1.local"):
	raise SystemExit("refusing: this script is for a throwaway site only")
frappe.init(site=SITE, sites_path=".")
frappe.connect()
frappe.set_user("Administrator")

COMPANY, ABBR = "KGS Test Stores", "KGS"
_CH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin(first14):
	total = 0
	for i, c in enumerate(first14):
		p = _CH.index(c) * (1 if i % 2 == 0 else 2)
		total += p // 36 + p % 36
	return first14 + _CH[(36 - total % 36) % 36]


OUR_GSTIN = gstin("23AAACK1234K1Z")
SUP_IN_GSTIN = gstin("23AABCS5678S1Z")
SUP_OUT_GSTIN = gstin("29AABCO4321O1Z")
from india_compliance.gst_india.utils import validate_gstin_check_digit  # noqa: E402

for g in (OUR_GSTIN, SUP_IN_GSTIN, SUP_OUT_GSTIN):
	validate_gstin_check_digit(g)

if not frappe.db.exists("Company", COMPANY):
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	setup_complete({
		"language": "English", "country": "India", "timezone": "Asia/Kolkata", "currency": "INR",
		"full_name": "Paper Admin", "email": "paper_admin@example.com", "password": "Kgs-Test-2026!x",
		"company_name": COMPANY, "company_abbr": ABBR, "chart_of_accounts": "Standard",
		"fy_start_date": "2026-04-01", "fy_end_date": "2027-03-31", "setup_demo": 0,
		"company_gstin": OUR_GSTIN, "default_gst_rate": "18.0", "enable_audit_trail": 0,
	})
	frappe.set_user("Administrator")
	frappe.db.commit()
print("company", frappe.db.get_value("Company", COMPANY, ["gstin", "gst_category", "default_currency"]))


def address(title, link_dt, link_name, gst, state, pin, company=False):
	name = frappe.db.get_value("Dynamic Link", {"link_doctype": link_dt, "link_name": link_name, "parenttype": "Address"}, "parent")
	if name:
		return name
	a = frappe.get_doc({
		"doctype": "Address", "address_title": title, "address_type": "Billing", "address_line1": "1 Test Road",
		"city": "Betul" if state == "Madhya Pradesh" else "Bengaluru", "state": state, "country": "India", "pincode": pin,
		"gstin": gst or "", "gst_category": "Registered Regular" if gst else "Unregistered",
		"is_primary_address": 1, "is_your_company_address": 1 if company else 0,
		"links": [{"link_doctype": link_dt, "link_name": link_name}],
	})
	a.insert(ignore_permissions=True)
	return a.name


address(COMPANY, "Company", COMPANY, OUR_GSTIN, "Madhya Pradesh", "460001", company=True)
group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
for sname, gst, state, pin in (("Selina Test Publishers", SUP_IN_GSTIN, "Madhya Pradesh", "462001"),
		("Out State Books Pvt Ltd", SUP_OUT_GSTIN, "Karnataka", "560001"),
		("Unregistered Paper Mart", None, "Madhya Pradesh", "460001")):
	if not frappe.db.exists("Supplier", sname):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": sname, "supplier_group": group,
			"gstin": gst or "", "gst_category": "Registered Regular" if gst else "Unregistered"}).insert(ignore_permissions=True)
	address(sname, "Supplier", sname, gst, state, pin)

if not frappe.db.exists("Account", f"Freight & Forwarding Charges - {ABBR}"):
	frappe.get_doc({"doctype": "Account", "account_name": "Freight & Forwarding Charges", "company": COMPANY,
		"parent_account": f"Indirect Expenses - {ABBR}", "account_type": "Expense Account"}).insert(ignore_permissions=True)

for uom, whole in (("Nos", 1), ("PKT", 1)):
	if not frappe.db.exists("UOM", uom):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": whole}).insert()

# production values (splashbox.in, 2026-10-20)
for dt, vals in (
	("Buying Settings", {"maintain_same_rate": 0, "po_required": "No", "pr_required": "No", "allow_multiple_items": 1,
		"buying_price_list": "Standard Buying", "set_landed_cost_based_on_purchase_invoice_rate": 0,
		"bill_for_rejected_quantity_in_purchase_invoice": 1}),
	("Stock Settings", {"over_delivery_receipt_allowance": 1000, "role_allowed_to_over_deliver_receive": "All",
		"allow_negative_stock": 1, "auto_insert_price_list_rate_if_missing": 1, "update_existing_price_list_rate": 0,
		"allow_to_edit_stock_uom_qty_for_purchase": 1, "allow_uom_with_conversion_rate_defined_in_item": 1}),
	("Accounts Settings", {"over_billing_allowance": 1500, "role_allowed_to_over_bill": "Accounts User",
		"check_supplier_invoice_uniqueness": 0}),
	("GST Settings", {"validate_hsn_code": 1, "min_hsn_digits": 4, "enable_api": 0}),
):
	for k, v in vals.items():
		if frappe.get_meta(dt).has_field(k):
			frappe.db.set_single_value(dt, k, v)

# Purchase User may create / submit receipts and bills (production: Custom DocPerm)
for dt in ("Purchase Receipt", "Purchase Invoice"):
	if not frappe.db.exists("Custom DocPerm", {"parent": dt, "role": "Purchase User", "permlevel": 0}):
		from frappe.permissions import setup_custom_perms

		setup_custom_perms(dt)
	name = frappe.db.get_value("Custom DocPerm", {"parent": dt, "role": "Purchase User", "permlevel": 0}, "name")
	if not name:
		frappe.get_doc({"doctype": "Custom DocPerm", "parent": dt, "parenttype": "DocType", "parentfield": "permissions",
			"role": "Purchase User", "permlevel": 0}).insert(ignore_permissions=True)
		name = frappe.db.get_value("Custom DocPerm", {"parent": dt, "role": "Purchase User", "permlevel": 0}, "name")
	frappe.db.set_value("Custom DocPerm", name, {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 0, "print": 1, "report": 1})
frappe.clear_cache()

print("item tax templates", frappe.get_all("Item Tax Template", filters={"company": COMPANY}, pluck="name"))
print("purchase templates", frappe.get_all("Purchase Taxes and Charges Template", filters={"company": COMPANY},
	fields=["name", "is_default", "tax_category"]))
print("warehouses", frappe.get_all("Warehouse", filters={"company": COMPANY, "is_group": 0}, pluck="name"))
frappe.db.commit()
print("done")
