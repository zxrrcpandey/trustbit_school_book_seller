// Multi Print Master — Auto-print Sales Invoice on Submit
// Uses QZ Tray (loaded globally by trustbit_barcode) to print
// multiple formats to configured printers.
// Priority: User Print Config (per-user) > Multi Print Setting (global default)
//
// Triggered via realtime event from server-side on_submit hook.
// Works from ANY submission source: standard form, POS Awesome, API.

// ── Realtime listener (global — fires on any page) ──────────────
frappe.realtime.on("multi_print_invoice", function (data) {
	if (!data || !data.docname) return;

	// Skip if Fast Print already handled this invoice (POS Awesome)
	if (window._pos_fast_print_handled === data.docname) {
		console.info("Skipping realtime print — Fast Print already handled:", data.docname);
		window._pos_fast_print_handled = null;
		return;
	}

	frappe.call({
		method: "trustbit_school_book_seller.api.get_multi_print_settings",
		callback: function (r) {
			var settings = r.message;
			if (!settings || !settings.enabled) return;
			if (!settings.print_formats || !settings.print_formats.length) return;

			var enabled_formats = settings.print_formats.filter(function (pf) {
				return pf.enabled;
			});
			if (!enabled_formats.length) return;

			multi_print_invoice(data.docname, settings, enabled_formats);
		},
	});
});

// ── Manual "Multi Print" button on submitted Sales Invoice form ──
frappe.ui.form.on("Sales Invoice", {
	refresh: function (frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Multi Print"), function () {
				frappe.call({
					method: "trustbit_school_book_seller.api.get_multi_print_settings",
					callback: function (r) {
						var settings = r.message;
						if (!settings || !settings.print_formats || !settings.print_formats.length) {
							frappe.msgprint({
								title: __("No Print Config"),
								message: __("No print formats configured.<br><br>"
									+ "Create a <b>User Print Config</b> for your account, "
									+ "or configure defaults in <b>Multi Print Setting</b>."),
								indicator: "orange",
							});
							return;
						}
						var enabled_formats = settings.print_formats.filter(function (pf) {
							return pf.enabled;
						});
						if (!enabled_formats.length) {
							frappe.msgprint(__("No enabled print formats found."));
							return;
						}
						multi_print_invoice(frm.doc.name, settings, enabled_formats);
					},
				});
			}, __("Print"));
		}
	},
});

// ── Core print function (accepts docname, not frm) ──────────────
function multi_print_invoice(docname, settings, enabled_formats) {
	var token = extract_token(docname, settings.token_digits || 3);
	var source_label = settings.source === "user" ? "your config" : "global default";

	if (typeof qz === "undefined") {
		frappe.msgprint({
			title: __("QZ Tray Not Found"),
			message: __("QZ Tray is not loaded.<br><br>"
				+ "1. Make sure QZ Tray is installed and running (check system tray)<br>"
				+ "2. Refresh the browser page (Ctrl+Shift+R)"),
			indicator: "red",
		});
		if (settings.show_token) {
			show_token_dialog(docname, token);
		}
		return;
	}

	frappe.show_alert({
		message: __("Printing {0} format(s) using {1}...", [enabled_formats.length, source_label]),
		indicator: "blue",
	});

	var qz_connect = qz.websocket.isActive()
		? Promise.resolve()
		: qz.websocket.connect();

	qz_connect
		.then(function () {
			return qz.printers.find();
		})
		.then(function (available_printers) {
			var available_set = {};
			available_printers.forEach(function (p) {
				available_set[p] = true;
			});

			var valid_formats = [];
			var skipped = [];
			enabled_formats.forEach(function (pf) {
				if (available_set[pf.printer_name]) {
					valid_formats.push(pf);
				} else {
					skipped.push(pf);
				}
			});

			if (skipped.length) {
				var skip_names = skipped.map(function (pf) {
					return pf.printer_name + " (" + pf.print_format + ")";
				}).join(", ");
				frappe.show_alert({
					message: __("Printer not found: {0}", [skip_names]),
					indicator: "orange",
				});
			}

			if (!valid_formats.length) {
				frappe.msgprint({
					title: __("No Printers Available"),
					message: __("None of the configured printers are available:<br><br>"
						+ skipped.map(function (pf) {
							return "&#9679; " + pf.printer_name + " → " + pf.print_format;
						}).join("<br>")
						+ "<br><br>Check printer connections and QZ Tray."),
					indicator: "red",
				});
				if (settings.show_token) {
					show_token_dialog(docname, token);
				}
				return Promise.resolve();
			}

			return print_all_formats(docname, valid_formats, 0).then(function () {
				frappe.show_alert({
					message: __("All prints sent successfully!"),
					indicator: "green",
				});
				if (settings.show_token) {
					show_token_dialog(docname, token);
				}
			});
		})
		.catch(function (err) {
			console.error("QZ Tray print error:", err);
			frappe.msgprint({
				title: __("Print Error"),
				message: __("Failed to print: {0}<br><br>"
					+ "Make sure QZ Tray is running and printers are connected.",
					[err.message || err]),
				indicator: "red",
			});
			if (settings.show_token) {
				show_token_dialog(docname, token);
			}
		});
}

function print_all_formats(docname, formats, index) {
	if (index >= formats.length) {
		return Promise.resolve();
	}

	var pf = formats[index];

	return fetch_print_html(docname, pf.print_format)
		.then(function (html) {
			var config_opts = {
				copies: pf.copies || 1,
			};

			// Detect paper size from print format name
			var fmt_lower = (pf.print_format || "").toLowerCase();
			var data;

			if (fmt_lower.indexOf("80mm") !== -1 || fmt_lower.indexOf("token") !== -1) {
				// 72mm receipt printer (80mm roll, 72mm printable area)
				config_opts.units = "mm";
				config_opts.size = { width: 72, height: 297 };
				config_opts.margins = { top: 0, right: 0, bottom: 0, left: 0 };
				config_opts.scaleContent = false;
				config_opts.rasterize = true;

				data = [{
					type: "pixel",
					format: "html",
					flavor: "plain",
					data: html,
				}];
			} else {
				// A4 for all other formats
				config_opts.size = { width: 8.27, height: 11.69 }; // A4
				config_opts.margins = { top: 0.15, right: 0.4, bottom: 0.4, left: 0.4 };
				config_opts.scaleContent = true;

				data = [{
					type: "pixel",
					format: "html",
					flavor: "plain",
					data: html,
				}];
			}

			return qz.print(config, data);
		})
		.then(function () {
			frappe.show_alert({
				message: __("Printed: {0} → {1}", [pf.print_format, pf.printer_name]),
				indicator: "green",
			});
			return print_all_formats(docname, formats, index + 1);
		});
}

function fetch_print_html(docname, print_format) {
	return new Promise(function (resolve, reject) {
		// Use Frappe API to get clean rendered HTML (no toolbar, no "Print Get PDF")
		frappe.xcall("frappe.get_print", {
			doctype: "Sales Invoice",
			name: docname,
			print_format: print_format,
			no_letterhead: 0,
		}).then(function (html) {
			if (html) {
				resolve(html);
			} else {
				reject(new Error("Empty HTML for: " + print_format));
			}
		}).catch(function (err) {
			reject(new Error("Failed to fetch: " + print_format + " - " + (err.message || err)));
		});
	});
}

function extract_token(invoice_name, digits) {
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
