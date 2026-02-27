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
					change: function () {
						var bundle = d.get_value("product_bundle");
						if (bundle) {
							// Fetch parent item name and bundle items in parallel
							frappe.call({
								method: "frappe.client.get_value",
								args: {
									doctype: "Item",
									filters: { name: bundle },
									fieldname: ["item_name", "description"]
								},
								async: false,
								callback: function (p) {
									var parent_info = p.message || {};
									var parent_html = '<div style="margin-top:4px;margin-bottom:8px;padding:8px 10px;'
										+ 'background:#f5f7fa;border-radius:4px;border-left:3px solid #5e64ff;">'
										+ '<div style="font-size:13px;font-weight:600;color:#333;">'
										+ frappe.utils.escape_html(bundle)
										+ (parent_info.item_name ? ' — ' + frappe.utils.escape_html(parent_info.item_name) : '')
										+ '</div>';
									if (parent_info.description) {
										var desc = frappe.utils.escape_html(
											parent_info.description.replace(/<[^>]*>/g, '').substring(0, 150)
										);
										parent_html += '<div style="font-size:11px;color:#666;margin-top:2px;">' + desc + '</div>';
									}
									parent_html += '</div>';
									d.fields_dict.bundle_preview.$wrapper.html(parent_html);
								}
							});

							frappe.call({
								method: "trustbit_school_book_seller.api.get_product_bundle_items",
								args: { product_bundle: bundle, qty_sets: 1 },
								callback: function (r) {
									var existing = d.fields_dict.bundle_preview.$wrapper.html();
									if (r.message && r.message.length) {
										var html = '<div style="max-height:150px;overflow-y:auto;">'
											+ '<table class="table table-bordered table-condensed" style="margin-bottom:0;font-size:12px;">'
											+ '<thead><tr><th>Item</th><th>Qty</th><th>UOM</th></tr></thead><tbody>';
										r.message.forEach(function (item) {
											html += '<tr><td>' + frappe.utils.escape_html(item.item_code)
												+ ' - ' + frappe.utils.escape_html(item.item_name || '')
												+ '</td><td>' + item.qty + '</td><td>'
												+ frappe.utils.escape_html(item.uom || '') + '</td></tr>';
										});
										html += '</tbody></table></div>';
										d.fields_dict.bundle_preview.$wrapper.html(existing + html);
									} else {
										d.fields_dict.bundle_preview.$wrapper.html(
											existing + '<p class="text-muted">' + __("No items in this bundle") + '</p>'
										);
									}
								}
							});
						} else {
							d.fields_dict.bundle_preview.$wrapper.html("");
						}
					},
				},
				{
					fieldname: "bundle_preview",
					fieldtype: "HTML",
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
