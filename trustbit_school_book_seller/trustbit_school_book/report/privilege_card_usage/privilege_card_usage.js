frappe.query_reports["Privilege Card Usage"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
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
			fieldname: "card_type",
			label: __("Card Type"),
			fieldtype: "Link",
			options: "Privilege Card Type",
		},
		{
			fieldname: "school",
			label: __("School"),
			fieldtype: "Link",
			options: "School",
		},
		{
			fieldname: "status",
			label: __("Card Status"),
			fieldtype: "Select",
			options: "\nActive\nInactive\nExpired",
		},
	],
};
