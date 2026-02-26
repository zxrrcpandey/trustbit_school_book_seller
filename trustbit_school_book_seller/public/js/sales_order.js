// ════════════════════════════════════════════════════════════════════════
// TRUSTBIT SCHOOL BOOK SELLER - SALES ORDER
// Custom: Create Purchase Orders Supplier Wise
// ════════════════════════════════════════════════════════════════════════

frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		if (frm.doc.docstatus !== 1) return;

		// Check if there are pending items (not fully ordered)
		let has_pending = frm.doc.items.some(function(item) {
			return (flt(item.stock_qty) - flt(item.ordered_qty)) > 0;
		});

		if (has_pending && frappe.model.can_create("Purchase Order")) {
			frm.add_custom_button(__('PO (Supplier Wise)'), function() {
				create_po_supplier_wise(frm);
			}, __('Create'));
		}
	}
});


function create_po_supplier_wise(frm) {
	frappe.call({
		method: 'trustbit_school_book_seller.api.get_so_items_with_suppliers',
		args: { sales_order: frm.doc.name },
		freeze: true,
		freeze_message: __('Fetching items and suppliers...'),
		callback: function(r) {
			if (!r.message || !r.message.length) {
				frappe.msgprint(__('No pending items to order.'));
				return;
			}
			show_supplier_wise_dialog(frm, r.message);
		}
	});
}


function show_supplier_wise_dialog(frm, items) {
	// Count items with and without suppliers
	let with_supplier = items.filter(function(d) { return d.supplier; }).length;
	let without_supplier = items.length - with_supplier;

	let help_html = '<p class="text-muted small">' +
		__('Total: {0} items. {1} with supplier, {2} without supplier.', [items.length, with_supplier, without_supplier]);

	if (without_supplier > 0) {
		help_html += ' ' + __('Items without a supplier will be grouped under "No Supplier".');
	}
	help_html += '</p>';

	var dialog = new frappe.ui.Dialog({
		title: __('Create Purchase Orders (Supplier Wise)'),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'help_text',
				options: help_html
			},
			{
				fieldname: 'items_for_po',
				fieldtype: 'Table',
				label: __('Select Items'),
				cannot_add_rows: true,
				in_place_edit: true,
				data: items,
				fields: [
					{
						fieldtype: 'Data',
						fieldname: 'item_code',
						label: __('Item Code'),
						read_only: 1,
						in_list_view: 1,
						columns: 2
					},
					{
						fieldtype: 'Data',
						fieldname: 'item_name',
						label: __('Item Name'),
						read_only: 1,
						in_list_view: 1,
						columns: 3
					},
					{
						fieldtype: 'Float',
						fieldname: 'pending_qty',
						label: __('Qty'),
						read_only: 1,
						in_list_view: 1,
						columns: 1
					},
					{
						fieldtype: 'Data',
						fieldname: 'uom',
						label: __('UOM'),
						read_only: 1,
						in_list_view: 1,
						columns: 1
					},
					{
						fieldtype: 'Link',
						fieldname: 'supplier',
						label: __('Supplier'),
						options: 'Supplier',
						in_list_view: 1,
						columns: 3
					}
				]
			}
		],
		primary_action_label: __('Create Purchase Orders'),
		primary_action: function() {
			let selected_items = dialog.fields_dict.items_for_po.grid.get_selected_children();

			if (!selected_items || selected_items.length === 0) {
				frappe.throw({
					message: __('Please select items from the table.'),
					title: __('Items Required'),
					indicator: 'blue'
				});
				return;
			}

			// Prepare items data for the API
			let items_to_send = selected_items.map(function(d) {
				return {
					so_detail: d.so_detail,
					item_code: d.item_code,
					item_name: d.item_name,
					pending_qty: d.pending_qty,
					uom: d.uom,
					stock_uom: d.stock_uom,
					conversion_factor: d.conversion_factor,
					warehouse: d.warehouse,
					delivery_date: d.delivery_date,
					supplier: d.supplier || ''
				};
			});

			// Show confirmation with supplier grouping summary
			let supplier_summary = {};
			items_to_send.forEach(function(d) {
				let s = d.supplier || 'No Supplier';
				if (!supplier_summary[s]) {
					supplier_summary[s] = 0;
				}
				supplier_summary[s]++;
			});

			let summary_html = '<p>' + __('The following Purchase Orders will be created:') + '</p><ul>';
			Object.keys(supplier_summary).forEach(function(s) {
				summary_html += '<li><strong>' + s + '</strong>: ' + supplier_summary[s] + ' item(s)</li>';
			});
			summary_html += '</ul>';

			frappe.confirm(
				summary_html,
				function() {
					dialog.hide();

					frappe.call({
						method: 'trustbit_school_book_seller.api.create_po_supplier_wise',
						args: {
							sales_order: frm.doc.name,
							items: items_to_send
						},
						freeze: true,
						freeze_message: __('Creating Purchase Orders...'),
						callback: function(r) {
							if (r.message && r.message.length) {
								frappe.show_alert({
									message: __('Created {0} Purchase Order(s)', [r.message.length]),
									indicator: 'green'
								});

								frappe.route_options = {
									'sales_order': frm.doc.name
								};
								frappe.set_route('List', 'Purchase Order');
								frm.reload_doc();
							}
						}
					});
				}
			);
		}
	});

	// Select all rows by default
	dialog.fields_dict.items_for_po.grid.wrapper
		.find('.grid-heading-row .grid-row-check').click();

	dialog.show();
}
