// Get Items from Product Bundle — Advanced Search
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

	var selected_bundle = null;
	var search_timeout = null;

	function show_product_bundle_dialog(frm) {
		selected_bundle = null;

		var d = new frappe.ui.Dialog({
			title: __("Get Items from Product Bundle"),
			fields: [
				{
					fieldname: "search_text",
					fieldtype: "Data",
					label: __("Search Product Bundle"),
					placeholder: __("Type to search by name, item, description, group..."),
				},
				{
					fieldname: "search_results",
					fieldtype: "HTML",
				},
				{
					fieldname: "selected_bundle_section",
					fieldtype: "Section Break",
					label: __("Selected Bundle"),
					hidden: 1,
				},
				{
					fieldname: "selected_bundle_preview",
					fieldtype: "HTML",
				},
				{
					fieldname: "options_section",
					fieldtype: "Section Break",
					label: __("Options"),
					hidden: 1,
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
					fieldname: "col_break_opts",
					fieldtype: "Column Break",
				},
				{
					fieldname: "action",
					fieldtype: "Select",
					label: __("Action"),
					options: "Append\nReplace",
					default: "Append",
					reqd: 1,
					description: __(
						"Append: add to existing items. Replace: clear first."
					),
				},
			],
			size: "large",
			primary_action_label: __("Get Items"),
			primary_action: function () {
				if (!selected_bundle) {
					frappe.msgprint(__("Please search and select a Product Bundle first"));
					return;
				}
				var qty = d.get_value("qty");
				var action = d.get_value("action");

				if (flt(qty) <= 0) {
					frappe.msgprint(__("Number of Sets must be greater than zero"));
					return;
				}

				d.hide();
				fetch_and_add_items(frm, selected_bundle, qty, action);
			},
		});

		// Auto-search on typing with debounce
		var $search_input = d.fields_dict.search_text.$input;
		$search_input.on("input", function () {
			clearTimeout(search_timeout);
			search_timeout = setTimeout(function () {
				do_search(d);
			}, 300);
		});

		// Search on Enter
		$search_input.on("keypress", function (e) {
			if (e.which === 13) {
				e.preventDefault();
				clearTimeout(search_timeout);
				do_search(d);
			}
		});

		d.show();

		// Load all bundles on open
		do_search(d);

		// Focus search input
		setTimeout(function () {
			$search_input.focus();
		}, 200);
	}

	function do_search(d) {
		var search_text = d.get_value("search_text") || "";

		d.fields_dict.search_results.$wrapper.html(
			'<div class="text-muted text-center" style="padding:20px;">'
			+ '<i class="fa fa-spinner fa-spin"></i> ' + __("Searching...") + '</div>'
		);

		frappe.call({
			method: "trustbit_school_book_seller.api.search_product_bundles",
			args: { search_text: search_text, limit: 20 },
			callback: function (r) {
				render_search_results(d, r.message || []);
			},
		});
	}

	function render_search_results(d, bundles) {
		var $wrapper = d.fields_dict.search_results.$wrapper;

		if (!bundles.length) {
			$wrapper.html(
				'<div class="text-muted text-center" style="padding:30px;">'
				+ '<i class="fa fa-search" style="font-size:24px;"></i>'
				+ '<p style="margin-top:8px;">' + __("No Product Bundles found") + '</p></div>'
			);
			return;
		}

		var html = '<div style="max-height:300px;overflow-y:auto;border:1px solid #d1d8dd;border-radius:4px;">'
			+ '<table class="table table-hover" style="margin-bottom:0;">'
			+ '<thead style="position:sticky;top:0;background:#f5f7fa;z-index:1;">'
			+ '<tr>'
			+ '<th style="font-size:12px;padding:8px 10px;">' + __("Bundle / Item Code") + '</th>'
			+ '<th style="font-size:12px;padding:8px 10px;">' + __("Item Name") + '</th>'
			+ '<th style="font-size:12px;padding:8px 10px;">' + __("Item Group") + '</th>'
			+ '<th style="font-size:12px;padding:8px 10px;text-align:center;">' + __("Items") + '</th>'
			+ '<th style="font-size:12px;padding:8px 10px;width:70px;"></th>'
			+ '</tr></thead><tbody>';

		bundles.forEach(function (b) {
			var desc_text = "";
			if (b.description) {
				desc_text = b.description.replace(/<[^>]*>/g, "").substring(0, 80);
			}

			var is_selected = selected_bundle === b.name;
			var row_style = is_selected
				? 'background:#e8f0fe;'
				: 'cursor:pointer;';

			html += '<tr class="bundle-row" data-bundle="' + frappe.utils.escape_html(b.name)
				+ '" style="' + row_style + '">'
				+ '<td style="padding:8px 10px;font-size:12px;">'
				+ '<div style="font-weight:600;">' + frappe.utils.escape_html(b.name) + '</div>';
			if (desc_text) {
				html += '<div style="font-size:11px;color:#888;margin-top:2px;">'
					+ frappe.utils.escape_html(desc_text) + '</div>';
			}
			html += '</td>'
				+ '<td style="padding:8px 10px;font-size:12px;">'
				+ frappe.utils.escape_html(b.item_name || "") + '</td>'
				+ '<td style="padding:8px 10px;font-size:12px;">'
				+ frappe.utils.escape_html(b.item_group || "") + '</td>'
				+ '<td style="padding:8px 10px;font-size:12px;text-align:center;">'
				+ '<span class="badge" style="background:#e2e8f0;color:#333;">'
				+ (b.items_count || 0) + '</span></td>'
				+ '<td style="padding:8px 10px;text-align:center;">'
				+ '<button class="btn btn-xs '
				+ (is_selected ? 'btn-primary-dark" disabled' : 'btn-primary"')
				+ ' style="font-size:11px;">'
				+ (is_selected ? '<i class="fa fa-check"></i>' : __("Select"))
				+ '</button></td></tr>';
		});

		html += '</tbody></table></div>';
		$wrapper.html(html);

		// Click handler on rows
		$wrapper.find(".bundle-row").on("click", function () {
			var bundle_name = $(this).data("bundle");
			select_bundle(d, bundle_name);
		});
	}

	function select_bundle(d, bundle_name) {
		selected_bundle = bundle_name;

		// Re-render the search results to highlight selected row
		// (but we can just update styling to avoid re-fetching)
		d.fields_dict.search_results.$wrapper.find(".bundle-row").each(function () {
			var $row = $(this);
			if ($row.data("bundle") === bundle_name) {
				$row.css("background", "#e8f0fe");
				$row.find("button").removeClass("btn-primary").addClass("btn-primary-dark")
					.prop("disabled", true).html('<i class="fa fa-check"></i>');
			} else {
				$row.css("background", "");
				$row.find("button").removeClass("btn-primary-dark").addClass("btn-primary")
					.prop("disabled", false).html(__("Select"));
			}
		});

		// Show selected bundle section and options
		d.fields_dict.selected_bundle_section.df.hidden = 0;
		d.fields_dict.selected_bundle_section.refresh();
		d.fields_dict.options_section.df.hidden = 0;
		d.fields_dict.options_section.refresh();

		// Load preview: parent item info + component items
		var $preview = d.fields_dict.selected_bundle_preview.$wrapper;
		$preview.html(
			'<div class="text-muted text-center" style="padding:10px;">'
			+ '<i class="fa fa-spinner fa-spin"></i> ' + __("Loading bundle details...") + '</div>'
		);

		// Fetch parent item info, then component items
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Item",
				filters: { name: bundle_name },
				fieldname: ["item_name", "description"],
			},
			callback: function (p) {
				var info = p.message || {};
				var phtml = '<div style="margin-bottom:8px;padding:8px 12px;'
					+ 'background:#f0f4ff;border-radius:4px;border-left:3px solid #5e64ff;">'
					+ '<div style="font-size:13px;font-weight:600;color:#333;">'
					+ frappe.utils.escape_html(bundle_name);
				if (info.item_name) {
					phtml += ' &mdash; ' + frappe.utils.escape_html(info.item_name);
				}
				phtml += '</div>';
				if (info.description) {
					var desc = info.description.replace(/<[^>]*>/g, "").substring(0, 200);
					phtml += '<div style="font-size:11px;color:#666;margin-top:2px;">'
						+ frappe.utils.escape_html(desc) + '</div>';
				}
				phtml += '</div>';
				$preview.html(phtml);

				// Fetch component items after parent info is rendered
				frappe.call({
					method: "trustbit_school_book_seller.api.get_product_bundle_items",
					args: { product_bundle: bundle_name, qty_sets: 1 },
					callback: function (r) {
						var existing = $preview.html();
						if (r.message && r.message.length) {
							var html = '<div style="max-height:150px;overflow-y:auto;">'
								+ '<table class="table table-bordered table-condensed" style="margin-bottom:0;font-size:12px;">'
								+ '<thead><tr><th>' + __("Item Code") + '</th><th>'
								+ __("Item Name") + '</th><th>' + __("Qty") + '</th><th>'
								+ __("UOM") + '</th></tr></thead><tbody>';
							r.message.forEach(function (item) {
								html += '<tr><td>' + frappe.utils.escape_html(item.item_code)
									+ '</td><td>' + frappe.utils.escape_html(item.item_name || "")
									+ '</td><td>' + item.qty
									+ '</td><td>' + frappe.utils.escape_html(item.uom || "")
									+ '</td></tr>';
							});
							html += '</tbody></table></div>';
							$preview.html(existing + html);
						}
					},
				});
			},
		});
	}

	function fetch_and_add_items(frm, bundle_name, qty_sets, action) {
		var price_list = frm.doc.buying_price_list
			|| frm.doc.selling_price_list || "";

		frappe.call({
			method: "trustbit_school_book_seller.api.get_product_bundle_items",
			args: {
				product_bundle: bundle_name,
				qty_sets: qty_sets,
				price_list: price_list,
				doctype: frm.doc.doctype,
				company: frm.doc.company || "",
			},
			freeze: true,
			freeze_message: __("Fetching bundle items..."),
			callback: function (r) {
				if (!r.message || !r.message.length) {
					frappe.msgprint(__("No available items in the selected Product Bundle"));
					return;
				}

				if (action === "Replace") {
					frm.doc.items = [];
				}

				r.message.forEach(function (item) {
					var row = frm.add_child("items");
					row.item_code = item.item_code;
					row.item_name = item.item_name;
					row.description = item.description;
					row.qty = item.qty;
					row.uom = item.uom;
					row.stock_uom = item.stock_uom;
					row.conversion_factor = item.conversion_factor || 1;
					row.custom_bundle_id = bundle_name;
					row.discount_percentage = item.discount_percentage || 0;
					row.discount_amount = item.discount_amount || 0;
					// Item defaults (accounts, warehouse, cost center)
					if (item.income_account) row.income_account = item.income_account;
					if (item.expense_account) row.expense_account = item.expense_account;
					if (item.warehouse) row.warehouse = item.warehouse;
					if (item.cost_center) row.cost_center = item.cost_center;
					if (item.price_list_rate) {
						row.price_list_rate = item.price_list_rate;
						row.rate = item.rate || item.price_list_rate;
						row.amount = flt(row.qty) * flt(row.rate);
					}
				});

				frm.refresh_fields();
				frm.dirty();

				frappe.show_alert({
					message: __("Added {0} items from Product Bundle", [r.message.length]),
					indicator: "green",
				});

				if (!price_list) {
					frappe.show_alert({
						message: __("No Price List set — rates not fetched"),
						indicator: "orange",
					});
				}
			},
		});
	}
})();
