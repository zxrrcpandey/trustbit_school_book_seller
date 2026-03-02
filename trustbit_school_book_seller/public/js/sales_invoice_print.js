// Multi Print Master — Auto-print Sales Invoice on Submit
// Uses QZ Tray (loaded globally by trustbit_barcode) to print
// multiple formats to configured printers.

frappe.ui.form.on("Sales Invoice", {
	on_submit: function (frm) {
		// Fetch multi print settings
		frappe.call({
			method: "trustbit_school_book_seller.api.get_multi_print_settings",
			async: false,
			callback: function (r) {
				var settings = r.message;
				if (!settings || !settings.enabled) return;
				if (!settings.print_formats || !settings.print_formats.length) return;

				var enabled_formats = settings.print_formats.filter(function (pf) {
					return pf.enabled;
				});
				if (!enabled_formats.length) return;

				// Start printing
				multi_print_invoice(frm, settings, enabled_formats);
			},
		});
	},

	refresh: function (frm) {
		// Add manual reprint button on submitted invoices
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Multi Print"), function () {
				frappe.call({
					method: "trustbit_school_book_seller.api.get_multi_print_settings",
					callback: function (r) {
						var settings = r.message;
						if (!settings || !settings.print_formats || !settings.print_formats.length) {
							frappe.msgprint(__("No print formats configured. Go to Multi Print Setting to configure."));
							return;
						}
						var enabled_formats = settings.print_formats.filter(function (pf) {
							return pf.enabled;
						});
						if (!enabled_formats.length) {
							frappe.msgprint(__("No enabled print formats found."));
							return;
						}
						multi_print_invoice(frm, settings, enabled_formats);
					},
				});
			}, __("Print"));
		}
	},
});

function multi_print_invoice(frm, settings, enabled_formats) {
	// Show token first if enabled
	var token = extract_token(frm.doc.name, settings.token_digits || 3);

	if (typeof qz === "undefined") {
		frappe.msgprint(__("QZ Tray is not loaded. Please ensure QZ Tray is running and trustbit_barcode app is installed."));
		return;
	}

	frappe.show_alert({
		message: __("Printing {0} format(s)...", [enabled_formats.length]),
		indicator: "blue",
	});

	// Connect to QZ Tray and print
	var qz_connect;
	if (qz.websocket.isActive()) {
		qz_connect = Promise.resolve();
	} else {
		qz_connect = qz.websocket.connect();
	}

	qz_connect
		.then(function () {
			return print_all_formats(frm, enabled_formats, 0);
		})
		.then(function () {
			frappe.show_alert({
				message: __("All prints sent successfully!"),
				indicator: "green",
			});

			// Show token dialog
			if (settings.show_token) {
				show_token_dialog(frm.doc.name, token);
			}
		})
		.catch(function (err) {
			console.error("QZ Tray print error:", err);
			frappe.msgprint({
				title: __("Print Error"),
				message: __("Failed to print: {0}", [err.message || err]),
				indicator: "red",
			});

			// Still show token even if print fails
			if (settings.show_token) {
				show_token_dialog(frm.doc.name, token);
			}
		});
}

function print_all_formats(frm, formats, index) {
	if (index >= formats.length) {
		return Promise.resolve();
	}

	var pf = formats[index];

	return fetch_print_html(frm.doc.name, pf.print_format)
		.then(function (html) {
			var config = qz.configs.create(pf.printer_name, {
				copies: pf.copies || 1,
			});

			var data = [
				{
					type: "pixel",
					format: "html",
					flavor: "plain",
					data: html,
				},
			];

			return qz.print(config, data);
		})
		.then(function () {
			frappe.show_alert({
				message: __("Printed: {0} → {1}", [pf.print_format, pf.printer_name]),
				indicator: "green",
			});
			// Print next format
			return print_all_formats(frm, formats, index + 1);
		});
}

function fetch_print_html(docname, print_format) {
	return new Promise(function (resolve, reject) {
		var url =
			"/api/method/frappe.utils.print_format.download_pdf?"
			+ "doctype=Sales%20Invoice"
			+ "&name=" + encodeURIComponent(docname)
			+ "&format=" + encodeURIComponent(print_format)
			+ "&no_letterhead=0"
			+ "&_type=html";

		// Use frappe.call to get print HTML
		$.ajax({
			url:
				"/printview?doctype=Sales%20Invoice"
				+ "&name=" + encodeURIComponent(docname)
				+ "&format=" + encodeURIComponent(print_format)
				+ "&no_letterhead=0",
			type: "GET",
			success: function (html) {
				resolve(html);
			},
			error: function (xhr, status, error) {
				reject(new Error("Failed to fetch print format: " + print_format));
			},
		});
	});
}

function extract_token(invoice_name, digits) {
	// Extract last N digits from the invoice name
	// e.g. "ACC-SINV-2026-00345" → "345"
	var numbers = invoice_name.replace(/[^0-9]/g, "");
	if (numbers.length <= digits) {
		return numbers;
	}
	return numbers.slice(-digits);
}

function show_token_dialog(invoice_name, token) {
	var d = new frappe.ui.Dialog({
		title: __("Token Number"),
		fields: [
			{
				fieldname: "token_html",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("OK"),
		primary_action: function () {
			d.hide();
		},
	});

	var html =
		'<div style="text-align:center;padding:20px 0;">'
		+ '<div style="font-size:14px;color:#888;margin-bottom:8px;">'
		+ frappe.utils.escape_html(invoice_name) + "</div>"
		+ '<div style="font-size:72px;font-weight:700;color:#5e64ff;'
		+ 'letter-spacing:8px;font-family:monospace;line-height:1.2;">'
		+ frappe.utils.escape_html(token) + "</div>"
		+ '<div style="font-size:14px;color:#888;margin-top:12px;">'
		+ __("Token") + "</div>"
		+ "</div>";

	d.fields_dict.token_html.$wrapper.html(html);
	d.show();
}
