// Multi Print Setting — Paper Size Preview
frappe.ui.form.on("Multi Print Setting", {
	refresh: function (frm) {
		frm.fields_dict.print_formats.grid.wrapper.on("click", ".btn-preview-print", function () {
			var row_name = $(this).data("row");
			var row = frm.fields_dict.print_formats.grid.grid_rows_by_docname[row_name];
			if (!row) return;
			var d = row.doc;
			preview_print_format(d.print_format, d.paper_size, d.custom_width_mm, d.custom_height_mm);
		});
	},
});

frappe.ui.form.on("Multi Print Format", {
	paper_size: function (frm, cdt, cdn) {
		add_preview_buttons(frm);
	},
	print_format: function (frm, cdt, cdn) {
		add_preview_buttons(frm);
	},
	print_formats_add: function (frm) {
		setTimeout(() => add_preview_buttons(frm), 300);
	},
	form_render: function (frm) {
		add_preview_buttons(frm);
	},
});

function add_preview_buttons(frm) {
	setTimeout(function () {
		// Remove existing preview buttons
		frm.fields_dict.print_formats.grid.wrapper.find(".btn-preview-print").remove();

		frm.fields_dict.print_formats.grid.grid_rows.forEach(function (grid_row) {
			if (!grid_row.doc.print_format) return;
			var $row = grid_row.row;
			// Add preview button in the row
			if (!$row.find(".btn-preview-print").length) {
				$row.find(".grid-row-check").after(
					'<button class="btn btn-xs btn-info btn-preview-print" data-row="' +
					grid_row.doc.name + '" title="Preview" style="margin: 2px 4px;">' +
					'<i class="fa fa-eye"></i></button>'
				);
			}
		});
	}, 200);
}

function preview_print_format(print_format, paper_size, custom_w, custom_h) {
	if (!print_format) {
		frappe.msgprint(__("Please select a Print Format first"));
		return;
	}

	// Get the last submitted Sales Invoice for preview
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
			var invoice_name = r.message[0].name;
			show_preview_dialog(invoice_name, print_format, paper_size, custom_w, custom_h);
		},
	});
}

function show_preview_dialog(docname, print_format, paper_size, custom_w, custom_h) {
	// Paper size dimensions
	var sizes = {
		"A4": { w: 210, h: 297 },
		"A5": { w: 148, h: 210 },
		"Letter": { w: 216, h: 279 },
		"80mm Receipt": { w: 80, h: 297 },
		"72mm Receipt": { w: 72, h: 297 },
		"58mm Receipt": { w: 58, h: 297 },
	};
	var size = sizes[paper_size];
	if (paper_size === "Custom" && custom_w && custom_h) {
		size = { w: custom_w, h: custom_h };
	}
	if (!size) size = sizes["A4"];

	var is_receipt = (paper_size || "").indexOf("Receipt") !== -1;

	// Scale for display (fit in dialog)
	var max_dialog_w = 700;
	var scale = Math.min(1, max_dialog_w / (size.w * 3.78)); // mm to px ~3.78
	var display_w = Math.round(size.w * 3.78 * scale);
	var display_h = Math.round(size.h * 3.78 * scale);

	// Cap height for receipts
	if (is_receipt) display_h = Math.min(display_h, 500);

	var dlg = new frappe.ui.Dialog({
		title: __("Print Preview: {0} ({1})", [print_format, paper_size || "A4"]),
		fields: [
			{
				fieldname: "info",
				fieldtype: "HTML",
				options: '<div class="text-muted small mb-2">' +
					__("Invoice: {0} | Paper: {1}mm × {2}mm", [docname, size.w, size.h]) +
					"</div>",
			},
			{
				fieldname: "preview",
				fieldtype: "HTML",
				options: '<div style="text-align:center;">' +
					'<div style="display:inline-block;border:2px solid #ccc;background:#fff;overflow:auto;' +
					"width:" + display_w + "px;height:" + display_h + 'px;">' +
					'<div class="preview-content" style="transform-origin:top left;transform:scale(' + scale + ');">' +
					'<i class="fa fa-spinner fa-spin"></i> Loading...' +
					"</div></div></div>",
			},
		],
		size: "extra-large",
		primary_action_label: __("Close"),
		primary_action: function () { dlg.hide(); },
	});
	dlg.show();

	// Fetch rendered HTML
	frappe.xcall("frappe.get_print", {
		doctype: "Sales Invoice",
		name: docname,
		print_format: print_format,
		no_letterhead: 0,
	}).then(function (html) {
		dlg.$wrapper.find(".preview-content").html(html);
	}).catch(function (err) {
		dlg.$wrapper.find(".preview-content").html(
			'<div class="text-danger p-3">Failed to load preview: ' + (err.message || err) + "</div>"
		);
	});
}
