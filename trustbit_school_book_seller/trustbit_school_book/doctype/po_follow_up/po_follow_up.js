frappe.ui.form.on("PO Follow Up", {
	refresh: function (frm) {
		if (frm.doc.purchase_order) {
			frm.add_custom_button(__("View Purchase Order"), function () {
				frappe.set_route("Form", "Purchase Order", frm.doc.purchase_order);
			});
		}
	},

	purchase_order: function (frm) {
		if (!frm.doc.purchase_order) return;

		frappe.call({
			method: "trustbit_school_book_seller.followup_api.get_po_items",
			args: { purchase_order: frm.doc.purchase_order },
			callback: function (r) {
				if (!r.message || !r.message.length) {
					frappe.msgprint(__("No items found in the Purchase Order"));
					return;
				}

				frm.clear_table("items");
				r.message.forEach(function (item) {
					var row = frm.add_child("items");
					row.po_detail = item.po_detail;
					row.item_code = item.item_code;
					row.item_name = item.item_name;
					row.ordered_qty = item.ordered_qty;
					row.expected_qty = item.pending_qty;
					row.status = "Pending";
				});
				frm.refresh_field("items");
			},
		});
	},
});
