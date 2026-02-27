// Get Items from Product Bundle
// Adds "Get Items > Product Bundle" button to:
//   Material Request, Sales Invoice, Sales Order, Purchase Order, Purchase Invoice

(function () {
	var TARGET_DOCTYPES = [
		"Material Request",
		"Sales Invoice",
		"Sales Order",
		"Purchase Order",
		"Purchase Invoice",
	];

	TARGET_DOCTYPES.forEach(function (dt) {
		frappe.ui.form.on(dt, {
			refresh: function (frm) {
				if (frm.doc.docstatus !== 0) return;

				frm.add_custom_button(
					__("Product Bundle"),
					function () {
						show_product_bundle_dialog(frm);
					},
					__("Get Items")
				);
			},
		});
	});

	function show_product_bundle_dialog(frm) {
		let d = new frappe.ui.Dialog({
			title: __("Get Items from Product Bundle"),
			fields: [
				{
					fieldname: "product_bundle",
					fieldtype: "Link",
					label: __("Product Bundle"),
					options: "Product Bundle",
					reqd: 1,
				},
				{
					fieldname: "qty",
					fieldtype: "Float",
					label: __("Number of Sets"),
					default: 1,
					reqd: 1,
					description: __(
						"Each item quantity will be multiplied by this number"
					),
				},
				{
					fieldname: "action",
					fieldtype: "Select",
					label: __("Action"),
					options: "Append\nReplace",
					default: "Append",
					reqd: 1,
					description: __(
						"Append: add to existing items. Replace: clear existing items first."
					),
				},
			],
			size: "small",
			primary_action_label: __("Get Items"),
			primary_action: function (values) {
				if (flt(values.qty) <= 0) {
					frappe.msgprint(
						__("Number of Sets must be greater than zero")
					);
					return;
				}

				d.hide();

				frappe.call({
					method: "trustbit_school_book_seller.api.get_product_bundle_items",
					args: {
						product_bundle: values.product_bundle,
						qty_sets: values.qty,
					},
					freeze: true,
					freeze_message: __("Fetching bundle items..."),
					callback: function (r) {
						if (!r.message || !r.message.length) {
							frappe.msgprint(
								__(
									"No items found in the selected Product Bundle"
								)
							);
							return;
						}

						if (values.action === "Replace") {
							frm.doc.items = [];
						}

						var added_rows = [];
						r.message.forEach(function (item) {
							var row = frm.add_child("items");
							row.item_code = item.item_code;
							row.item_name = item.item_name;
							row.description = item.description;
							row.qty = item.qty;
							row.uom = item.uom;
							row.stock_uom = item.stock_uom;
							row.conversion_factor =
								item.conversion_factor || 1;
							added_rows.push(row);
						});

						frm.refresh_fields();
						frm.dirty();

						frappe.show_alert({
							message: __(
								"Added {0} items from Product Bundle",
								[r.message.length]
							),
							indicator: "green",
						});

						// Trigger item_code change on each row to fetch rates from Price List
						var chain = Promise.resolve();
						added_rows.forEach(function (row) {
							chain = chain.then(function () {
								return frappe.model.set_value(
									row.doctype,
									row.name,
									"item_code",
									row.item_code
								);
							});
						});
					},
				});
			},
		});

		d.show();
	}
})();
