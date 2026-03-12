frappe.ui.form.on("Purchase Order", {
	refresh: function (frm) {
		if (frm.doc.docstatus !== 1) return;

		// Add "Create > Follow Up" button
		frm.add_custom_button(
			__("Follow Up"),
			function () {
				frappe.call({
					method: "trustbit_school_book_seller.followup_api.create_followup_from_po",
					args: { purchase_order: frm.doc.name },
					freeze: true,
					freeze_message: __("Creating Follow Up..."),
					callback: function (r) {
						if (r.message) {
							frappe.set_route("Form", "PO Follow Up", r.message);
						}
					},
				});
			},
			__("Create")
		);

		// Add "View > Follow Ups (N)" button if follow-ups exist
		if (frm.doc.custom_total_followups > 0) {
			frm.add_custom_button(
				__("Follow Ups ({0})", [frm.doc.custom_total_followups]),
				function () {
					frappe.set_route("List", "PO Follow Up", {
						purchase_order: frm.doc.name,
					});
				},
				__("View")
			);
		}

		// Dashboard indicator: last follow-up status
		if (frm.doc.custom_last_followup_status) {
			var indicator_color = {
				Pending: "orange",
				Confirmed: "blue",
				"Partially Dispatched": "yellow",
				Dispatched: "purple",
				Delivered: "green",
				Delayed: "red",
			};
			var color =
				indicator_color[frm.doc.custom_last_followup_status] || "grey";
			frm.dashboard.add_indicator(
				__("Follow Up: {0}", [frm.doc.custom_last_followup_status]),
				color
			);
		}

		// Dashboard indicator: next follow-up date
		if (frm.doc.custom_next_followup_date) {
			var next_date = frappe.datetime.str_to_obj(
				frm.doc.custom_next_followup_date
			);
			var today_date = frappe.datetime.str_to_obj(
				frappe.datetime.get_today()
			);
			var is_overdue = next_date < today_date;
			frm.dashboard.add_indicator(
				__("Next Follow Up: {0}", [
					frappe.datetime.str_to_user(
						frm.doc.custom_next_followup_date
					),
				]),
				is_overdue ? "red" : "blue"
			);
		}
	},
});
