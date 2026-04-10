// Advanced Search for Product Bundle form
// Adds Ctrl+Q Quick Add and Ctrl+B Barcode Scan for adding items to a Product Bundle

frappe.ui.form.on("Product Bundle", {
	refresh: function (frm) {
		if (frm.doc.name) {
			frm.add_custom_button(
				__("KGS School Book V5"),
				function () {
					print_product_bundle(frm.doc.name);
				},
				__("Print")
			);
		}

		frm.add_custom_button(
			__("Quick Add (Ctrl+Q)"),
			function () {
				show_quick_add_dialog(frm);
			},
			__("Add Items")
		);

		frm.add_custom_button(
			__("Scan Barcode (Ctrl+B)"),
			function () {
				show_barcode_dialog(frm);
			},
			__("Add Items")
		);
	},

	onload: function (frm) {
		// Keyboard shortcuts
		frm.$wrapper.on("keydown", function (e) {
			// Ctrl+Q = Quick Add
			if (e.ctrlKey && e.key === "q") {
				e.preventDefault();
				show_quick_add_dialog(frm);
			}
			// Ctrl+B = Barcode Scan
			if (e.ctrlKey && e.key === "b") {
				e.preventDefault();
				show_barcode_dialog(frm);
			}
		});
	},
});

// ─── Quick Add Dialog (Ctrl+Q) ───

var search_timeout = null;

function show_quick_add_dialog(frm) {
	var d = new frappe.ui.Dialog({
		title: __("Quick Add Item to Bundle"),
		fields: [
			{
				fieldname: "search_text",
				fieldtype: "Data",
				label: __("Search Item"),
				placeholder: __("Type item code, name, group, or barcode..."),
			},
			{
				fieldname: "search_results",
				fieldtype: "HTML",
			},
			{
				fieldname: "item_details_section",
				fieldtype: "Section Break",
				label: __("Item Details"),
				hidden: 1,
			},
			{
				fieldname: "selected_item_code",
				fieldtype: "Data",
				label: __("Item Code"),
				read_only: 1,
			},
			{
				fieldname: "selected_item_name",
				fieldtype: "Data",
				label: __("Item Name"),
				read_only: 1,
			},
			{
				fieldname: "col_break_detail",
				fieldtype: "Column Break",
			},
			{
				fieldname: "selected_stock_uom",
				fieldtype: "Data",
				label: __("Stock UOM"),
				read_only: 1,
			},
			{
				fieldname: "selected_item_group",
				fieldtype: "Data",
				label: __("Item Group"),
				read_only: 1,
			},
			{
				fieldname: "qty_section",
				fieldtype: "Section Break",
				label: __("Quantity"),
				hidden: 1,
			},
			{
				fieldname: "qty",
				fieldtype: "Float",
				label: __("Qty"),
				default: 1,
				reqd: 1,
			},
		],
		size: "large",
		primary_action_label: __("Add to Bundle"),
		primary_action: function () {
			var item_code = d.get_value("selected_item_code");
			var qty = flt(d.get_value("qty"));

			if (!item_code) {
				frappe.msgprint(__("Please search and select an item first"));
				return;
			}
			if (qty <= 0) {
				frappe.msgprint(__("Quantity must be greater than zero"));
				return;
			}

			add_item_to_bundle(frm, item_code, qty);

			frappe.show_alert({
				message: __("Added {0} (Qty: {1})", [item_code, qty]),
				indicator: "green",
			});

			// Reset for next item
			d.set_value("selected_item_code", "");
			d.set_value("selected_item_name", "");
			d.set_value("selected_stock_uom", "");
			d.set_value("selected_item_group", "");
			d.set_value("qty", 1);
			d.set_value("search_text", "");
			d.fields_dict.item_details_section.df.hidden = 1;
			d.fields_dict.item_details_section.refresh();
			d.fields_dict.qty_section.df.hidden = 1;
			d.fields_dict.qty_section.refresh();
			d.fields_dict.search_results.$wrapper.html("");

			// Focus back to search
			setTimeout(function () {
				d.fields_dict.search_text.$input.focus();
			}, 100);
		},
		secondary_action_label: __("Close"),
		secondary_action: function () {
			d.hide();
		},
	});

	// Auto-search on typing with debounce
	var $search_input = d.fields_dict.search_text.$input;
	$search_input.on("input", function () {
		clearTimeout(search_timeout);
		search_timeout = setTimeout(function () {
			do_item_search(d);
		}, 300);
	});

	// Search on Enter
	$search_input.on("keypress", function (e) {
		if (e.which === 13) {
			e.preventDefault();
			clearTimeout(search_timeout);
			do_item_search(d);
		}
	});

	d.show();

	setTimeout(function () {
		$search_input.focus();
	}, 200);
}

function do_item_search(d) {
	var search_text = d.get_value("search_text") || "";
	if (search_text.length < 2) {
		d.fields_dict.search_results.$wrapper.html(
			'<div class="text-muted text-center" style="padding:20px;">'
			+ __("Type at least 2 characters to search") + "</div>"
		);
		return;
	}

	d.fields_dict.search_results.$wrapper.html(
		'<div class="text-muted text-center" style="padding:20px;">'
		+ '<i class="fa fa-spinner fa-spin"></i> ' + __("Searching...") + "</div>"
	);

	frappe.call({
		method: "trustbit_school_book_seller.api.search_items",
		args: { search_text: search_text, limit: 30 },
		callback: function (r) {
			render_item_results(d, r.message || []);
		},
	});
}

function render_item_results(d, items) {
	var $wrapper = d.fields_dict.search_results.$wrapper;

	if (!items.length) {
		$wrapper.html(
			'<div class="text-muted text-center" style="padding:30px;">'
			+ '<i class="fa fa-search" style="font-size:24px;"></i>'
			+ '<p style="margin-top:8px;">' + __("No items found") + "</p></div>"
		);
		return;
	}

	var html =
		'<div style="max-height:300px;overflow-y:auto;border:1px solid #d1d8dd;border-radius:4px;">'
		+ '<table class="table table-hover" style="margin-bottom:0;">'
		+ '<thead style="position:sticky;top:0;background:#f5f7fa;z-index:1;">'
		+ "<tr>"
		+ '<th style="font-size:12px;padding:8px 10px;">' + __("Item Code") + "</th>"
		+ '<th style="font-size:12px;padding:8px 10px;">' + __("Item Name") + "</th>"
		+ '<th style="font-size:12px;padding:8px 10px;">' + __("Group") + "</th>"
		+ '<th style="font-size:12px;padding:8px 10px;">' + __("UOM") + "</th>"
		+ '<th style="font-size:12px;padding:8px 10px;width:70px;"></th>'
		+ "</tr></thead><tbody>";

	items.forEach(function (item) {
		html +=
			'<tr class="item-row" data-item="' + frappe.utils.escape_html(item.item_code)
			+ '" data-name="' + frappe.utils.escape_html(item.item_name || "")
			+ '" data-uom="' + frappe.utils.escape_html(item.stock_uom || "")
			+ '" data-group="' + frappe.utils.escape_html(item.item_group || "")
			+ '" style="cursor:pointer;">'
			+ '<td style="padding:8px 10px;font-size:12px;">'
			+ '<div style="font-weight:600;">' + frappe.utils.escape_html(item.item_code) + "</div>";

		if (item.barcode) {
			html +=
				'<div style="font-size:10px;color:#888;margin-top:1px;">'
				+ '<i class="fa fa-barcode"></i> '
				+ frappe.utils.escape_html(item.barcode) + "</div>";
		}

		html +=
			"</td>"
			+ '<td style="padding:8px 10px;font-size:12px;">'
			+ frappe.utils.escape_html(item.item_name || "") + "</td>"
			+ '<td style="padding:8px 10px;font-size:12px;">'
			+ frappe.utils.escape_html(item.item_group || "") + "</td>"
			+ '<td style="padding:8px 10px;font-size:12px;">'
			+ frappe.utils.escape_html(item.stock_uom || "") + "</td>"
			+ '<td style="padding:8px 10px;text-align:center;">'
			+ '<button class="btn btn-xs btn-primary" style="font-size:11px;">'
			+ __("Select") + "</button></td></tr>";
	});

	html += "</tbody></table></div>";
	$wrapper.html(html);

	// Click handler on rows
	$wrapper.find(".item-row").on("click", function () {
		var $row = $(this);
		select_item(d, {
			item_code: $row.data("item"),
			item_name: $row.data("name"),
			stock_uom: $row.data("uom"),
			item_group: $row.data("group"),
		});
	});
}

function select_item(d, item) {
	d.set_value("selected_item_code", item.item_code);
	d.set_value("selected_item_name", item.item_name);
	d.set_value("selected_stock_uom", item.stock_uom);
	d.set_value("selected_item_group", item.item_group);

	// Show details and qty sections
	d.fields_dict.item_details_section.df.hidden = 0;
	d.fields_dict.item_details_section.refresh();
	d.fields_dict.qty_section.df.hidden = 0;
	d.fields_dict.qty_section.refresh();

	// Highlight selected row
	d.fields_dict.search_results.$wrapper.find(".item-row").css("background", "");
	d.fields_dict.search_results.$wrapper
		.find('.item-row[data-item="' + item.item_code + '"]')
		.css("background", "#e8f0fe");

	// Focus qty field
	setTimeout(function () {
		d.fields_dict.qty.$input.focus().select();
	}, 100);
}

// ─── Barcode Scan Dialog (Ctrl+B) ───

function show_barcode_dialog(frm) {
	var d = new frappe.ui.Dialog({
		title: __("Scan Barcode to Add Item"),
		fields: [
			{
				fieldname: "barcode",
				fieldtype: "Data",
				label: __("Barcode"),
				placeholder: __("Scan or type barcode..."),
			},
			{
				fieldname: "scan_result",
				fieldtype: "HTML",
			},
			{
				fieldname: "scan_qty_section",
				fieldtype: "Section Break",
				label: __("Quantity"),
				hidden: 1,
			},
			{
				fieldname: "scan_qty",
				fieldtype: "Float",
				label: __("Qty"),
				default: 1,
				reqd: 1,
			},
		],
		size: "small",
		primary_action_label: __("Add to Bundle"),
		primary_action: function () {
			var item_code = d._scanned_item_code;
			var qty = flt(d.get_value("scan_qty"));

			if (!item_code) {
				frappe.msgprint(__("Please scan a barcode first"));
				return;
			}
			if (qty <= 0) {
				frappe.msgprint(__("Quantity must be greater than zero"));
				return;
			}

			add_item_to_bundle(frm, item_code, qty);

			frappe.show_alert({
				message: __("Added {0} (Qty: {1})", [item_code, qty]),
				indicator: "green",
			});

			// Reset for next scan
			d._scanned_item_code = null;
			d.set_value("barcode", "");
			d.set_value("scan_qty", 1);
			d.fields_dict.scan_qty_section.df.hidden = 1;
			d.fields_dict.scan_qty_section.refresh();
			d.fields_dict.scan_result.$wrapper.html(
				'<div class="text-muted text-center" style="padding:20px;">'
				+ '<i class="fa fa-barcode" style="font-size:24px;"></i>'
				+ '<p style="margin-top:8px;">' + __("Scan barcode to find item...") + "</p></div>"
			);

			setTimeout(function () {
				d.fields_dict.barcode.$input.focus();
			}, 100);
		},
	});

	d._scanned_item_code = null;

	// Show initial state
	d.fields_dict.scan_result.$wrapper.html(
		'<div class="text-muted text-center" style="padding:20px;">'
		+ '<i class="fa fa-barcode" style="font-size:24px;"></i>'
		+ '<p style="margin-top:8px;">' + __("Scan barcode to find item...") + "</p></div>"
	);

	var barcode_timeout = null;
	var $barcode_input = d.fields_dict.barcode.$input;

	// Search on Enter or after pause
	$barcode_input.on("keypress", function (e) {
		if (e.which === 13) {
			e.preventDefault();
			clearTimeout(barcode_timeout);
			do_barcode_lookup(d);
		}
	});

	$barcode_input.on("input", function () {
		clearTimeout(barcode_timeout);
		barcode_timeout = setTimeout(function () {
			do_barcode_lookup(d);
		}, 800);
	});

	d.show();

	setTimeout(function () {
		$barcode_input.focus();
	}, 200);
}

function do_barcode_lookup(d) {
	var barcode = (d.get_value("barcode") || "").trim();
	if (!barcode) return;

	d.fields_dict.scan_result.$wrapper.html(
		'<div class="text-muted text-center" style="padding:15px;">'
		+ '<i class="fa fa-spinner fa-spin"></i> ' + __("Looking up barcode...") + "</div>"
	);

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Item Barcode",
			filters: { barcode: barcode },
			fields: ["parent"],
			limit_page_length: 1,
		},
		callback: function (r) {
			if (r.message && r.message.length) {
				var item_code = r.message[0].parent;
				frappe.call({
					method: "frappe.client.get",
					args: { doctype: "Item", name: item_code },
					callback: function (r2) {
						if (r2.message) {
							var item = r2.message;
							d._scanned_item_code = item.name;

							var html =
								'<div style="padding:10px;background:#f0fff0;border-radius:4px;'
								+ 'border-left:3px solid #28a745;">'
								+ '<div style="font-size:13px;font-weight:600;color:#333;">'
								+ '<i class="fa fa-check-circle text-success"></i> '
								+ frappe.utils.escape_html(item.name) + "</div>"
								+ '<div style="font-size:12px;color:#555;margin-top:4px;">'
								+ frappe.utils.escape_html(item.item_name || "") + "</div>"
								+ '<div style="font-size:11px;color:#888;margin-top:2px;">'
								+ frappe.utils.escape_html(item.item_group || "")
								+ " | UOM: " + frappe.utils.escape_html(item.stock_uom || "")
								+ "</div></div>";

							d.fields_dict.scan_result.$wrapper.html(html);
							d.fields_dict.scan_qty_section.df.hidden = 0;
							d.fields_dict.scan_qty_section.refresh();

							setTimeout(function () {
								d.fields_dict.scan_qty.$input.focus().select();
							}, 100);
						}
					},
				});
			} else {
				d._scanned_item_code = null;
				d.fields_dict.scan_result.$wrapper.html(
					'<div style="padding:10px;background:#fff0f0;border-radius:4px;'
					+ 'border-left:3px solid #dc3545;">'
					+ '<div style="font-size:13px;color:#dc3545;">'
					+ '<i class="fa fa-times-circle"></i> '
					+ __("No item found for barcode: {0}", [frappe.utils.escape_html(barcode)])
					+ "</div></div>"
				);
				d.fields_dict.scan_qty_section.df.hidden = 1;
				d.fields_dict.scan_qty_section.refresh();
			}
		},
	});
}

// ─── Common: Add item to bundle ───

function add_item_to_bundle(frm, item_code, qty) {
	// Check if item already exists in the bundle
	var existing_row = null;
	(frm.doc.items || []).forEach(function (row) {
		if (row.item_code === item_code) {
			existing_row = row;
		}
	});

	if (existing_row) {
		// Update quantity of existing row
		frappe.model.set_value(
			existing_row.doctype,
			existing_row.name,
			"qty",
			flt(existing_row.qty) + qty
		);
	} else {
		// Add new row
		var row = frm.add_child("items");
		frappe.model.set_value(row.doctype, row.name, "item_code", item_code);
		frappe.model.set_value(row.doctype, row.name, "qty", qty);
	}

	frm.refresh_field("items");
	frm.dirty();
}

// ── Print Product Bundle as KGS School Book V5 ──────────────
function print_product_bundle(bundle_name) {
	// Open PDF directly via Frappe's PDF endpoint
	var url = "/api/method/trustbit_school_book_seller.dashboard_api.get_bundle_pdf"
		+ "?product_bundle=" + encodeURIComponent(bundle_name);
	window.open(url, "_blank");
}

// ── List View: Bulk Print ──────────────
frappe.listview_settings["Product Bundle"] = frappe.listview_settings["Product Bundle"] || {};
frappe.listview_settings["Product Bundle"].onload = function (listview) {
	listview.page.add_action_item(__("Print (KGS School Book V5)"), function () {
		var selected = listview.get_checked_items();
		if (!selected.length) {
			frappe.msgprint(__("Please select Product Bundles to print"));
			return;
		}
		frappe.confirm(
			__("Print {0} Product Bundle(s)?", [selected.length]),
			function () {
				selected.forEach(function (item, idx) {
					setTimeout(function () {
						print_product_bundle(item.name);
					}, idx * 500);
				});
			}
		);
	});
};
