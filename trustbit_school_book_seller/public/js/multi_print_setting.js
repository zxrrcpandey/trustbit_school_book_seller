// Multi Print Setting — Paper Size Preview
frappe.ui.form.on("Multi Print Setting", {
	refresh: function (frm) {
		// Add Preview button for each row
		frm.fields_dict.print_formats.grid.add_custom_button(
			__("Preview Selected"),
			function () {
				var selected = frm.fields_dict.print_formats.grid.get_selected_children();
				if (!selected.length) {
					frappe.msgprint(__("Please select a row to preview"));
					return;
				}
				var row = selected[0];
				preview_print_format(
					row.print_format,
					row.paper_size || "A4",
					row.custom_width_mm,
					row.custom_height_mm
				);
			}
		);
	},
});

frappe.ui.form.on("Multi Print Format", {
	// Add preview button when row is opened for editing
	form_render: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		var grid_row = frm.fields_dict.print_formats.grid.grid_rows_by_docname[cdn];
		if (!grid_row) return;

		// Remove existing preview button
		grid_row.wrapper.find(".btn-preview-row").remove();

		// Add preview button in the edit form
		var $btn = $('<button class="btn btn-sm btn-info btn-preview-row mt-2 mb-2">' +
			'<i class="fa fa-eye"></i> ' + __("Preview at this Paper Size") +
			"</button>");
		$btn.on("click", function () {
			preview_print_format(
				row.print_format,
				row.paper_size || "A4",
				row.custom_width_mm,
				row.custom_height_mm
			);
		});
		grid_row.wrapper.find(".frappe-control[data-fieldname='enabled']").after($btn);
	},
});

function preview_print_format(print_format, paper_size, custom_w, custom_h) {
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
			show_preview_dialog(r.message[0].name, print_format, paper_size, custom_w, custom_h);
		},
	});
}

function show_preview_dialog(docname, print_format, paper_size, custom_w, custom_h) {
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
	var px_per_mm = 3.78;
	var content_w = Math.round(size.w * px_per_mm);
	var max_h = is_receipt ? 400 : Math.round(size.h * px_per_mm * 0.6);
	var scale = Math.min(1, 650 / content_w);

	var dlg = new frappe.ui.Dialog({
		title: __("Preview: {0} — {1} ({2}×{3}mm)", [print_format, paper_size, size.w, size.h]),
		fields: [
			{
				fieldname: "preview_html",
				fieldtype: "HTML",
				options:
					'<div style="text-align:center;padding:10px 0;">' +
					'<div style="display:inline-block;border:2px solid #999;background:white;box-shadow:0 2px 8px rgba(0,0,0,0.15);' +
					"width:" + Math.round(content_w * scale) + "px;" +
					"height:" + Math.round(max_h * scale) + "px;" +
					'overflow:auto;">' +
					'<div class="preview-body" style="width:' + content_w + "px;" +
					"transform-origin:top left;transform:scale(" + scale + ');">' +
					'<div style="padding:40px;text-align:center;color:#999;">' +
					'<i class="fa fa-spinner fa-spin fa-2x"></i><br>Loading preview...</div>' +
					"</div></div></div>",
			},
		],
		size: "extra-large",
		primary_action_label: __("Close"),
		primary_action: function () {
			dlg.hide();
		},
	});
	dlg.show();

	$.ajax({
		url: "/printview?doctype=Sales%20Invoice"
			+ "&name=" + encodeURIComponent(docname)
			+ "&format=" + encodeURIComponent(print_format)
			+ "&no_letterhead=0",
		type: "GET",
		success: function (html) {
			dlg.$wrapper.find(".preview-body").html(html);
		},
		error: function () {
			dlg.$wrapper.find(".preview-body").html(
				'<div class="text-danger p-4">Preview failed. Check permissions.</div>'
			);
		},
	});
}
