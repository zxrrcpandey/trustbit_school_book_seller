/**
 * Return Scanner — Barcode/Search dialog for Sales/Purchase Returns
 *
 * Adds a "Scan Return Items" button on Sales Invoice and Purchase Invoice
 * when is_return = 1. Opens a dialog to scan barcodes or search items,
 * then populates the items table with negative quantities.
 */
frappe.provide("trustbit.return_scanner");

trustbit.return_scanner = {
	// Cached settings
	_settings: null,
	_scanned_items: [],

	setup: function (frm) {
		// Only show on return invoices
		if (!frm.doc.is_return) return;
		// Don't show on submitted/cancelled docs
		if (frm.doc.docstatus !== 0) return;

		frm.add_custom_button(
			__("Scan Return Items"),
			function () {
				trustbit.return_scanner.open_scanner(frm);
			},
			__("Tools")
		);
	},

	open_scanner: function (frm) {
		var self = this;
		self._scanned_items = [];

		// Load settings first
		frappe.call({
			method: "trustbit_school_book_seller.return_scanner_api.get_return_scanner_settings",
			callback: function (r) {
				self._settings = r.message || {
					return_mode: "Hybrid",
					auto_focus_barcode: 1,
					play_sound_on_scan: 1,
					allow_exceed_original_qty: 0,
					max_return_without_approval: 0,
				};

				// Determine effective mode
				var mode = self._settings.return_mode;
				var is_strict = false;

				if (mode === "Strict") {
					if (!frm.doc.return_against) {
						frappe.msgprint(
							__(
								"Strict mode requires 'Return Against' to be set. Please select the original invoice first."
							)
						);
						return;
					}
					is_strict = true;
				} else if (mode === "Hybrid") {
					is_strict = !!frm.doc.return_against;
				}
				// Free mode: is_strict = false

				// If strict, pre-load original invoice items
				if (is_strict) {
					frappe.call({
						method: "trustbit_school_book_seller.return_scanner_api.get_original_invoice_items",
						args: {
							return_against: frm.doc.return_against,
							doctype: frm.doc.doctype,
						},
						callback: function (r2) {
							var orig_items = r2.message || [];
							self._show_dialog(frm, is_strict, orig_items);
						},
					});
				} else {
					self._show_dialog(frm, is_strict, []);
				}
			},
		});
	},

	_show_dialog: function (frm, is_strict, orig_items) {
		var self = this;
		self._scanned_items = [];

		var mode_label = is_strict
			? '<span style="color:#e57373;">STRICT</span> — Items from: ' +
				frm.doc.return_against
			: '<span style="color:#4caf50;">FREE</span> — Scan any item';

		var d = new frappe.ui.Dialog({
			title: __("Return Item Scanner"),
			size: "extra-large",
			fields: [
				{
					fieldname: "mode_info",
					fieldtype: "HTML",
					options:
						'<div style="font-size:12px;margin-bottom:8px;padding:6px 10px;background:#f5f5f5;border-radius:4px;">' +
						"Mode: " +
						mode_label +
						"</div>",
				},
				{
					fieldname: "barcode",
					fieldtype: "Data",
					label: __("Scan Barcode or Search Item"),
					placeholder: __("Scan barcode or type item name..."),
				},
				{
					fieldname: "search_results",
					fieldtype: "HTML",
					options: "",
				},
				{
					fieldname: "items_section",
					fieldtype: "Section Break",
					label: __("Items to Return"),
				},
				{
					fieldname: "items_html",
					fieldtype: "HTML",
					options: self._render_items_table([]),
				},
				{
					fieldname: "summary_html",
					fieldtype: "HTML",
					options: self._render_summary(0, 0),
				},
			],
			primary_action_label: __("Add to Return"),
			primary_action: function () {
				self._add_items_to_form(frm, d);
			},
			secondary_action_label: __("Clear All"),
			secondary_action: function () {
				self._scanned_items = [];
				self._refresh_dialog(d);
			},
		});

		// Barcode input handling
		var $input = d.fields_dict.barcode.$input;
		var search_timeout = null;

		$input.on("keypress", function (e) {
			if (e.which === 13) {
				e.preventDefault();
				clearTimeout(search_timeout);
				var val = $input.val().trim();
				if (val) {
					self._handle_scan(d, frm, val, is_strict, orig_items);
				}
			}
		});

		$input.on("input", function () {
			var val = $input.val().trim();
			clearTimeout(search_timeout);

			if (val.length >= 3) {
				search_timeout = setTimeout(function () {
					self._search_items(d, frm, val, is_strict);
				}, 400);
			} else {
				d.fields_dict.search_results.$wrapper.html("");
			}
		});

		d.show();

		if (self._settings.auto_focus_barcode) {
			setTimeout(function () {
				$input.focus();
			}, 300);
		}

		// Store reference
		d._is_strict = is_strict;
		d._orig_items = orig_items;
		d._frm = frm;
	},

	_handle_scan: function (d, frm, barcode, is_strict, orig_items) {
		var self = this;

		// First check if it matches an item already in orig_items (strict mode)
		if (is_strict) {
			var found_in_orig = null;
			for (var i = 0; i < orig_items.length; i++) {
				if (
					orig_items[i].item_code === barcode ||
					orig_items[i].item_name === barcode
				) {
					found_in_orig = orig_items[i];
					break;
				}
			}
			if (found_in_orig) {
				self._add_scanned_item(d, found_in_orig, is_strict);
				return;
			}
		}

		// Call server to scan barcode
		frappe.call({
			method: "trustbit_school_book_seller.return_scanner_api.scan_return_barcode",
			args: {
				barcode: barcode,
				return_against: is_strict ? frm.doc.return_against : null,
				doctype: frm.doc.doctype,
			},
			callback: function (r) {
				var result = r.message;
				if (!result || !result.success) {
					self._play_error_sound();
					frappe.show_alert(
						{
							message: result
								? result.message
								: __("Item not found"),
							indicator: "red",
						},
						3
					);
					d.fields_dict.barcode.set_value("");
					d.fields_dict.barcode.$input.focus();
					return;
				}
				self._add_scanned_item(d, result, is_strict);
			},
		});
	},

	_add_scanned_item: function (d, item_data, is_strict) {
		var self = this;
		var allow_exceed = self._settings.allow_exceed_original_qty;

		// Check if already in scanned list
		var existing = null;
		for (var i = 0; i < self._scanned_items.length; i++) {
			if (self._scanned_items[i].item_code === item_data.item_code) {
				existing = self._scanned_items[i];
				break;
			}
		}

		if (existing) {
			// Increment qty
			var new_qty = existing.return_qty + 1;
			if (
				is_strict &&
				!allow_exceed &&
				new_qty > item_data.returnable_qty
			) {
				frappe.show_alert(
					{
						message: __(
							"Cannot exceed returnable qty ({0}) for {1}",
							[item_data.returnable_qty, item_data.item_name]
						),
						indicator: "orange",
					},
					3
				);
			} else {
				existing.return_qty = new_qty;
				self._play_scan_sound();
			}
		} else {
			// Add new item
			var return_qty = 1;
			if (
				is_strict &&
				!allow_exceed &&
				item_data.returnable_qty <= 0
			) {
				frappe.show_alert(
					{
						message: __(
							"No returnable qty left for {0}",
							[item_data.item_name]
						),
						indicator: "orange",
					},
					3
				);
				d.fields_dict.barcode.set_value("");
				d.fields_dict.barcode.$input.focus();
				return;
			}

			self._scanned_items.push({
				item_code: item_data.item_code,
				item_name: item_data.item_name,
				brand: item_data.brand || "",
				original_qty: item_data.original_qty || 0,
				returnable_qty: item_data.returnable_qty || 9999,
				return_qty: return_qty,
				rate: item_data.rate || 0,
				price_list_rate: item_data.price_list_rate || item_data.rate || 0,
				uom: item_data.uom || "Nos",
				discount_percentage: item_data.discount_percentage || 0,
				warehouse: item_data.warehouse || "",
			});
			self._play_scan_sound();
		}

		self._refresh_dialog(d);
		d.fields_dict.barcode.set_value("");
		d.fields_dict.barcode.$input.focus();
		d.fields_dict.search_results.$wrapper.html("");
	},

	_search_items: function (d, frm, query, is_strict) {
		var self = this;

		frappe.call({
			method: "trustbit_school_book_seller.return_scanner_api.search_return_items",
			args: {
				query: query,
				return_against: is_strict ? frm.doc.return_against : null,
				doctype: frm.doc.doctype,
			},
			callback: function (r) {
				var items = r.message || [];
				if (!items.length) {
					d.fields_dict.search_results.$wrapper.html(
						'<div style="padding:6px;color:#999;font-size:11px;">No items found</div>'
					);
					return;
				}

				var html =
					'<div style="max-height:150px;overflow-y:auto;border:1px solid #eee;border-radius:4px;margin-bottom:8px;">';
				html += '<table style="width:100%;font-size:11px;border-collapse:collapse;">';

				for (var i = 0; i < items.length; i++) {
					var item = items[i];
					var avail_label = is_strict
						? " (Avail: " + item.returnable_qty + ")"
						: "";
					html +=
						'<tr class="return-search-result" data-idx="' +
						i +
						'" style="cursor:pointer;border-bottom:1px solid #f0f0f0;"' +
						' onmouseover="this.style.background=\'#f5f5f5\'"' +
						' onmouseout="this.style.background=\'#fff\'">' +
						'<td style="padding:6px 8px;">' +
						frappe.utils.escape_html(item.item_code) +
						"</td>" +
						'<td style="padding:6px 4px;">' +
						frappe.utils.escape_html(item.item_name) +
						"</td>" +
						'<td style="padding:6px 4px;color:#888;">' +
						frappe.utils.escape_html(item.brand || "") +
						"</td>" +
						'<td style="padding:6px 8px;text-align:right;color:#666;">' +
						avail_label +
						"</td></tr>";
				}
				html += "</table></div>";

				d.fields_dict.search_results.$wrapper.html(html);

				// Click handler for search results
				d.fields_dict.search_results.$wrapper
					.find(".return-search-result")
					.on("click", function () {
						var idx = $(this).data("idx");
						var selected = items[idx];
						self._add_scanned_item(d, selected, is_strict);
					});
			},
		});
	},

	_refresh_dialog: function (d) {
		var self = this;
		d.fields_dict.items_html.$wrapper.html(
			self._render_items_table(self._scanned_items)
		);
		var total_qty = 0;
		var total_amount = 0;
		for (var i = 0; i < self._scanned_items.length; i++) {
			total_qty += self._scanned_items[i].return_qty;
			total_amount +=
				self._scanned_items[i].return_qty * self._scanned_items[i].rate;
		}
		d.fields_dict.summary_html.$wrapper.html(
			self._render_summary(total_qty, total_amount)
		);

		// Bind qty change and remove handlers
		d.fields_dict.items_html.$wrapper
			.find(".return-qty-input")
			.on("change", function () {
				var idx = parseInt($(this).data("idx"));
				var new_qty = parseFloat($(this).val()) || 0;
				if (new_qty < 0) new_qty = 0;

				var item = self._scanned_items[idx];
				if (!item) return;

				var is_strict = d._is_strict;
				var allow_exceed = self._settings.allow_exceed_original_qty;

				if (
					is_strict &&
					!allow_exceed &&
					new_qty > item.returnable_qty
				) {
					frappe.show_alert(
						{
							message: __(
								"Max returnable: {0}",
								[item.returnable_qty]
							),
							indicator: "orange",
						},
						2
					);
					new_qty = item.returnable_qty;
					$(this).val(new_qty);
				}

				item.return_qty = new_qty;
				self._refresh_dialog(d);
			});

		d.fields_dict.items_html.$wrapper
			.find(".return-remove-btn")
			.on("click", function () {
				var idx = parseInt($(this).data("idx"));
				self._scanned_items.splice(idx, 1);
				self._refresh_dialog(d);
			});
	},

	_render_items_table: function (items) {
		if (!items.length) {
			return '<div style="text-align:center;padding:20px;color:#ccc;font-size:13px;">Scan items or search to add them here</div>';
		}

		var html =
			'<table style="width:100%;border-collapse:collapse;font-size:12px;">';
		html += "<thead><tr>";
		html +=
			'<th style="padding:6px 4px;border-bottom:2px solid #ddd;width:5%;text-align:center;">SN</th>';
		html +=
			'<th style="padding:6px 4px;border-bottom:2px solid #ddd;width:30%;text-align:left;">Item</th>';
		html +=
			'<th style="padding:6px 4px;border-bottom:2px solid #ddd;width:12%;">Brand</th>';
		html +=
			'<th style="padding:6px 4px;border-bottom:2px solid #ddd;width:10%;text-align:center;">Avail</th>';
		html +=
			'<th style="padding:6px 4px;border-bottom:2px solid #ddd;width:12%;text-align:center;">Return Qty</th>';
		html +=
			'<th style="padding:6px 4px;border-bottom:2px solid #ddd;width:10%;text-align:right;">Rate</th>';
		html +=
			'<th style="padding:6px 4px;border-bottom:2px solid #ddd;width:12%;text-align:right;">Amount</th>';
		html +=
			'<th style="padding:6px 4px;border-bottom:2px solid #ddd;width:5%;"></th>';
		html += "</tr></thead><tbody>";

		for (var i = 0; i < items.length; i++) {
			var item = items[i];
			var item_rate = parseFloat(item.rate) || 0;
			var amount = item.return_qty * item_rate;
			var avail_display =
				item.returnable_qty >= 9999 ? "—" : item.returnable_qty;

			html += '<tr style="border-bottom:1px solid #f0f0f0;">';
			html +=
				'<td style="padding:5px 4px;text-align:center;color:#888;">' +
				(i + 1) +
				"</td>";
			html +=
				'<td style="padding:5px 4px;">' +
				frappe.utils.escape_html(item.item_name) +
				'<br><span style="font-size:10px;color:#999;">' +
				frappe.utils.escape_html(item.item_code) +
				"</span></td>";
			html +=
				'<td style="padding:5px 4px;color:#888;">' +
				frappe.utils.escape_html(item.brand) +
				"</td>";
			html +=
				'<td style="padding:5px 4px;text-align:center;color:#666;">' +
				avail_display +
				"</td>";
			html +=
				'<td style="padding:5px 4px;text-align:center;">' +
				'<input type="number" class="return-qty-input" data-idx="' +
				i +
				'" value="' +
				item.return_qty +
				'"' +
				' min="0" step="1"' +
				' style="width:60px;text-align:center;border:1px solid #ccc;border-radius:3px;padding:3px;font-size:12px;">' +
				"</td>";
			html +=
				'<td style="padding:5px 4px;text-align:right;">' +
				item_rate.toFixed(2) +
				"</td>";
			html +=
				'<td style="padding:5px 4px;text-align:right;font-weight:500;">' +
				amount.toFixed(2) +
				"</td>";
			html +=
				'<td style="padding:5px 4px;text-align:center;">' +
				'<button class="btn btn-xs btn-danger return-remove-btn" data-idx="' +
				i +
				'" title="Remove">&times;</button>' +
				"</td>";
			html += "</tr>";
		}

		html += "</tbody></table>";
		return html;
	},

	_render_summary: function (total_qty, total_amount) {
		if (!total_qty) return "";
		return (
			'<div style="display:flex;justify-content:space-between;padding:8px 4px;margin-top:6px;' +
			'border-top:1px solid #eee;font-size:13px;">' +
			"<div><strong>Total Items:</strong> " +
			this._scanned_items.length +
			" &nbsp;&middot;&nbsp; <strong>Total Qty:</strong> " +
			total_qty +
			"</div>" +
			'<div style="font-size:15px;font-weight:600;">Return Amount: &#8377; ' +
			total_amount.toFixed(2) +
			"</div></div>"
		);
	},

	_add_items_to_form: function (frm, dialog) {
		var self = this;

		if (!self._scanned_items.length) {
			frappe.show_alert(
				{ message: __("No items scanned"), indicator: "orange" },
				2
			);
			return;
		}

		// Check max return amount
		var total_amount = 0;
		for (var i = 0; i < self._scanned_items.length; i++) {
			total_amount +=
				self._scanned_items[i].return_qty *
				self._scanned_items[i].rate;
		}

		var max_limit = self._settings.max_return_without_approval || 0;
		if (max_limit > 0 && total_amount > max_limit) {
			frappe.confirm(
				__(
					"Return amount ({0}) exceeds limit ({1}). This may require manager approval. Continue?",
					[
						frappe.format_currency(total_amount),
						frappe.format_currency(max_limit),
					]
				),
				function () {
					self._do_add_items(frm, dialog);
				}
			);
			return;
		}

		self._do_add_items(frm, dialog);
	},

	_do_add_items: function (frm, dialog) {
		var self = this;

		// Clear existing items properly using Frappe API
		frm.clear_table("items");

		// Add each scanned item with NEGATIVE qty (skip zero-qty items)
		for (var i = 0; i < self._scanned_items.length; i++) {
			var item = self._scanned_items[i];
			if (!item.return_qty || item.return_qty <= 0) continue;
			var row = frm.add_child("items");

			row.item_code = item.item_code;
			row.item_name = item.item_name;
			row.qty = -Math.abs(item.return_qty);
			row.rate = parseFloat(item.rate) || 0;
			row.price_list_rate = parseFloat(item.price_list_rate || item.rate) || 0;
			row.uom = item.uom;
			row.stock_uom = item.uom;
			row.conversion_factor = 1;
			row.discount_percentage = parseFloat(item.discount_percentage) || 0;
			if (item.warehouse) {
				row.warehouse = item.warehouse;
			}
		}

		frm.refresh_field("items");
		frm.dirty();

		dialog.hide();

		frappe.show_alert(
			{
				message: __(
					"{0} items added to return with negative qty",
					[self._scanned_items.length]
				),
				indicator: "green",
			},
			4
		);

		// Trigger item_code change sequentially to avoid race conditions
		var rows = frm.doc.items.slice();
		var idx = 0;
		function set_next_item() {
			if (idx >= rows.length) return;
			var row = rows[idx];
			idx++;
			frappe.model.set_value(
				row.doctype, row.name, "item_code", row.item_code
			).then(function () {
				// Restore negative qty after ERPNext's handler may reset it
				setTimeout(function () {
					var scanned = self._scanned_items[idx - 1];
					if (scanned) {
						frappe.model.set_value(
							row.doctype, row.name, "qty",
							-Math.abs(scanned.return_qty)
						);
					}
					set_next_item();
				}, 200);
			});
		}
		setTimeout(set_next_item, 300);
	},

	_play_scan_sound: function () {
		if (!this._settings || !this._settings.play_sound_on_scan) return;
		try {
			var audio = new Audio(
				"/assets/frappe/sounds/click.mp3"
			);
			audio.volume = 0.3;
			audio.play();
		} catch (e) {
			// Ignore audio errors
		}
	},

	_play_error_sound: function () {
		if (!this._settings || !this._settings.play_sound_on_scan) return;
		try {
			var audio = new Audio(
				"/assets/frappe/sounds/error.mp3"
			);
			audio.volume = 0.5;
			audio.play();
		} catch (e) {
			// Ignore audio errors
		}
	},
};

// Auto-setup on form refresh
frappe.ui.form.on("Sales Invoice", {
	refresh: function (frm) {
		trustbit.return_scanner.setup(frm);
	},
	is_return: function (frm) {
		trustbit.return_scanner.setup(frm);
	},
});

frappe.ui.form.on("Purchase Invoice", {
	refresh: function (frm) {
		trustbit.return_scanner.setup(frm);
	},
	is_return: function (frm) {
		trustbit.return_scanner.setup(frm);
	},
});
