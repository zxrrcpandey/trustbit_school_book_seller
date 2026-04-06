// User Print Config — QZ Tray Printer Detection & Status + Preview
frappe.ui.form.on("User Print Config", {
	refresh: function (frm) {
		// Detect Printers button
		frm.add_custom_button(__("Detect Printers"), function () {
			detect_and_select_printer(frm);
		});

		// Preview Selected button on grid
		frm.fields_dict.print_formats.grid.add_custom_button(
			__("Preview Selected"),
			function () {
				var selected = frm.fields_dict.print_formats.grid.get_selected_children();
				if (!selected.length) {
					frappe.msgprint(__("Please select a row to preview"));
					return;
				}
				var row = selected[0];
				preview_print(row.print_format, row.paper_size, row.custom_width_mm, row.custom_height_mm);
			}
		);

		// Check printer status on load
		check_all_printer_status(frm);
	},
});

frappe.ui.form.on("Multi Print Format", {
	form_render: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		var grid_row = frm.fields_dict.print_formats.grid.grid_rows_by_docname[cdn];
		if (!grid_row) return;
		grid_row.wrapper.find(".btn-preview-row").remove();
		var $btn = $('<button class="btn btn-sm btn-info btn-preview-row mt-2 mb-2">' +
			'<i class="fa fa-eye"></i> ' + __("Preview at this Paper Size") + "</button>");
		$btn.on("click", function () {
			preview_print(row.print_format, row.paper_size, row.custom_width_mm, row.custom_height_mm);
		});
		grid_row.wrapper.find(".frappe-control[data-fieldname='enabled']").after($btn);
	},
});

function preview_print(print_format, paper_size, custom_w, custom_h) {
	if (!print_format) {
		frappe.msgprint(__("Please select a Print Format first"));
		return;
	}
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Sales Invoice",
			filters: { docstatus: 1 },
			fields: ["name"],
			order_by: "creation desc",
			limit_page_length: 1,
		},
		callback: function (r) {
			if (!r.message || !r.message.length) {
				frappe.msgprint(__("No submitted Sales Invoice found for preview"));
				return;
			}
			show_preview(r.message[0].name, print_format, paper_size || "A4", custom_w, custom_h);
		},
	});
}

function show_preview(docname, print_format, paper_size, custom_w, custom_h) {
	var sizes = {
		"A4": { w: 210, h: 297 }, "A5": { w: 148, h: 210 }, "Letter": { w: 216, h: 279 },
		"80mm Receipt": { w: 80, h: 297 }, "72mm Receipt": { w: 72, h: 297 }, "58mm Receipt": { w: 58, h: 297 },
	};
	var size = sizes[paper_size];
	if (paper_size === "Custom" && custom_w && custom_h) size = { w: custom_w, h: custom_h };
	if (!size) size = sizes["A4"];

	var is_receipt = (paper_size || "").indexOf("Receipt") !== -1;
	var scale = Math.min(1, 650 / (size.w * 3.78));
	var dw = Math.round(size.w * 3.78 * scale);
	var dh = Math.round((is_receipt ? Math.min(size.h, 130) : size.h) * 3.78 * scale);

	var dlg = new frappe.ui.Dialog({
		title: __("Preview: {0} — {1} ({2}×{3}mm)", [print_format, paper_size, size.w, size.h]),
		fields: [{
			fieldname: "preview_html", fieldtype: "HTML",
			options: '<div style="text-align:center;padding:10px 0;">' +
				'<div style="display:inline-block;border:2px solid #999;background:white;box-shadow:0 2px 8px rgba(0,0,0,0.15);' +
				"width:" + dw + "px;height:" + dh + 'px;overflow:auto;">' +
				'<div class="preview-body" style="width:' + Math.round(size.w * 3.78) + "px;" +
				"transform-origin:top left;transform:scale(" + scale + ');">' +
				'<div style="padding:40px;text-align:center;color:#999;">' +
				'<i class="fa fa-spinner fa-spin fa-2x"></i><br>Loading...</div>' +
				"</div></div></div>",
		}],
		size: "extra-large",
		primary_action_label: __("Close"),
		primary_action: function () { dlg.hide(); },
	});
	dlg.show();

	$.ajax({
		url: "/printview?doctype=Sales%20Invoice&name=" + encodeURIComponent(docname) +
			"&format=" + encodeURIComponent(print_format) + "&no_letterhead=0",
		type: "GET",
		success: function (html) { dlg.$wrapper.find(".preview-body").html(html); },
		error: function () {
			dlg.$wrapper.find(".preview-body").html('<div class="text-danger p-4">Preview failed.</div>');
		},
	});
}

function detect_and_select_printer(frm) {
	if (typeof qz === "undefined") {
		frappe.msgprint({
			title: __("QZ Tray Not Found"),
			message: __("QZ Tray is not loaded. Please ensure:<br>1. QZ Tray is installed and running<br>2. The trustbit_barcode app is installed<br>3. Refresh the browser page"),
			indicator: "red",
		});
		return;
	}

	var connect_promise = qz.websocket.isActive()
		? Promise.resolve()
		: qz.websocket.connect();

	frappe.show_alert({
		message: __("Connecting to QZ Tray..."),
		indicator: "blue",
	});

	connect_promise
		.then(function () {
			return qz.printers.find();
		})
		.then(function (printers) {
			if (!printers || !printers.length) {
				frappe.msgprint(__("No printers detected. Check if printers are installed and turned on."));
				return;
			}

			show_printer_dialog(frm, printers);
		})
		.catch(function (err) {
			frappe.msgprint({
				title: __("QZ Tray Connection Failed"),
				message: __(
					"Cannot connect to QZ Tray: {0}<br><br>"
					+ "Make sure QZ Tray is running (check system tray icon).",
					[err.message || err]
				),
				indicator: "red",
			});
		});
}

function show_printer_dialog(frm, printers) {
	var html =
		'<div style="margin-bottom:8px;font-size:13px;color:#555;">'
		+ __("{0} printer(s) detected on this machine", [printers.length])
		+ "</div>"
		+ '<div style="max-height:300px;overflow-y:auto;border:1px solid #d1d8dd;border-radius:4px;">'
		+ '<table class="table table-hover" style="margin-bottom:0;">'
		+ '<thead style="position:sticky;top:0;background:#f5f7fa;z-index:1;">'
		+ "<tr>"
		+ '<th style="font-size:12px;padding:8px 10px;">' + __("Printer Name") + "</th>"
		+ '<th style="font-size:12px;padding:8px 10px;width:100px;text-align:center;">'
		+ __("Action") + "</th>"
		+ "</tr></thead><tbody>";

	// Check which printers are already configured
	var configured = {};
	(frm.doc.print_formats || []).forEach(function (row) {
		configured[row.printer_name] = true;
	});

	printers.forEach(function (printer) {
		var is_configured = configured[printer];
		var badge = is_configured
			? '<span class="badge" style="background:#28a745;color:#fff;font-size:10px;">Configured</span>'
			: "";

		html +=
			'<tr class="printer-row" data-printer="'
			+ frappe.utils.escape_html(printer)
			+ '" style="cursor:pointer;">'
			+ '<td style="padding:8px 10px;font-size:12px;">'
			+ '<span style="color:#28a745;margin-right:6px;">&#9679;</span>'
			+ frappe.utils.escape_html(printer)
			+ " " + badge + "</td>"
			+ '<td style="padding:8px 10px;text-align:center;">'
			+ '<button class="btn btn-xs btn-primary select-printer-btn" style="font-size:11px;">'
			+ __("Add") + "</button></td></tr>";
	});

	html += "</tbody></table></div>";

	var d = new frappe.ui.Dialog({
		title: __("Detected Printers"),
		fields: [
			{
				fieldname: "printer_list",
				fieldtype: "HTML",
			},
			{
				fieldname: "print_format",
				fieldtype: "Link",
				label: __("Print Format to Map"),
				options: "Print Format",
				description: __("Select which print format to assign to the printer"),
			},
			{
				fieldname: "copies",
				fieldtype: "Int",
				label: __("Copies"),
				default: 1,
			},
		],
		size: "large",
	});

	d.fields_dict.printer_list.$wrapper.html(html);

	// Click handler
	d.fields_dict.printer_list.$wrapper.find(".select-printer-btn").on("click", function (e) {
		e.stopPropagation();
		var printer_name = $(this).closest(".printer-row").data("printer");
		var print_format = d.get_value("print_format");
		var copies = d.get_value("copies") || 1;

		if (!print_format) {
			frappe.msgprint(__("Please select a Print Format first"));
			return;
		}

		// Add row to child table
		var row = frm.add_child("print_formats");
		row.print_format = print_format;
		row.printer_name = printer_name;
		row.copies = copies;
		row.enabled = 1;
		frm.refresh_field("print_formats");
		frm.dirty();

		frappe.show_alert({
			message: __("Added: {0} → {1}", [print_format, printer_name]),
			indicator: "green",
		});

		// Update badge
		$(this).closest("tr").find("td:first").append(
			' <span class="badge" style="background:#28a745;color:#fff;font-size:10px;">Configured</span>'
		);
	});

	d.show();
}

function check_all_printer_status(frm) {
	var $status = frm.fields_dict.printer_status_html.$wrapper;

	if (!frm.doc.print_formats || !frm.doc.print_formats.length) {
		$status.html(
			'<div style="padding:8px 12px;background:#f5f7fa;border-radius:4px;font-size:12px;color:#888;">'
			+ __('No printers configured. Click "Detect Printers" to add.')
			+ "</div>"
		);
		return;
	}

	if (typeof qz === "undefined") {
		$status.html(
			'<div style="padding:8px 12px;background:#fff3cd;border-radius:4px;border-left:3px solid #ffc107;font-size:12px;">'
			+ '<b>' + __("QZ Tray not loaded") + "</b> — Cannot check printer status. "
			+ __("Make sure QZ Tray is running and refresh the page.")
			+ "</div>"
		);
		return;
	}

	$status.html(
		'<div style="padding:8px 12px;background:#f5f7fa;border-radius:4px;font-size:12px;">'
		+ '<i class="fa fa-spinner fa-spin"></i> ' + __("Checking printer status...")
		+ "</div>"
	);

	var connect_promise = qz.websocket.isActive()
		? Promise.resolve()
		: qz.websocket.connect();

	connect_promise
		.then(function () {
			return qz.printers.find();
		})
		.then(function (available_printers) {
			var available_set = {};
			available_printers.forEach(function (p) {
				available_set[p] = true;
			});

			var html =
				'<div style="padding:8px 12px;background:#f5f7fa;border-radius:4px;">'
				+ '<div style="font-size:12px;font-weight:600;margin-bottom:6px;">'
				+ __("Printer Status") + "</div>";

			var all_ok = true;
			frm.doc.print_formats.forEach(function (row) {
				if (!row.enabled) return;
				var is_available = available_set[row.printer_name];
				if (!is_available) all_ok = false;

				var dot_color = is_available ? "#28a745" : "#dc3545";
				var status_text = is_available ? __("Available") : __("NOT FOUND");
				var status_style = is_available
					? "color:#28a745;"
					: "color:#dc3545;font-weight:bold;";

				html +=
					'<div style="font-size:12px;padding:3px 0;">'
					+ '<span style="color:' + dot_color + ';margin-right:6px;">&#9679;</span>'
					+ frappe.utils.escape_html(row.printer_name)
					+ ' <span style="' + status_style + '">(' + status_text + ")</span>"
					+ ' <span style="color:#888;"> → ' + frappe.utils.escape_html(row.print_format)
					+ "</span></div>";
			});

			if (!all_ok) {
				html +=
					'<div style="margin-top:6px;padding:6px 8px;background:#fff3cd;border-radius:3px;font-size:11px;">'
					+ __("Some printers are not found. Check connections and printer names.")
					+ "</div>";
			}

			html += "</div>";
			$status.html(html);
		})
		.catch(function () {
			$status.html(
				'<div style="padding:8px 12px;background:#f8d7da;border-radius:4px;border-left:3px solid #dc3545;font-size:12px;">'
				+ '<b>' + __("QZ Tray offline") + "</b> — Cannot check printer status."
				+ "</div>"
			);
		});
}
