frappe.query_reports["School Book Sales Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			// 1 January: season purchases are dated Jan-Mar, before sales start in April
			default: frappe.datetime.get_today().slice(0, 4) + "-01-01",
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "product_bundle",
			label: __("Product Bundle"),
			fieldtype: "MultiSelectList",
			options: "Product Bundle",
			get_data: (txt) =>
				frappe
					.call({
						method: "trustbit_school_book_seller.api.search_product_bundles",
						args: { search_text: txt, limit: 20 },
					})
					.then((r) =>
						(r.message || []).map((d) => ({ value: d.name, description: d.item_name }))
					),
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "MultiSelectList",
			options: "Item",
			get_data: (txt) => frappe.db.get_link_options("Item", txt),
		},
		{
			fieldname: "school",
			label: __("School (Customer Group)"),
			fieldtype: "MultiSelectList",
			options: "Customer Group",
			get_data: (txt) => frappe.db.get_link_options("Customer Group", txt),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "MultiSelectList",
			options: "Customer",
			get_data: (txt) => frappe.db.get_link_options("Customer", txt),
		},
		{
			fieldname: "show_other_customers",
			label: __("Show Other Customers"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
