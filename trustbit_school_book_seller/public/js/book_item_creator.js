// Copyright (c) 2024, Trustbit and contributors
// For license information, please see license.txt

// BUG FIX: API paths must be: trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.function_name
// NOT: trustbit_school_book_seller.trustbit_school_book_seller.doctype...

let progress_dialog = null;

frappe.ui.form.on('Book Item Creator', {
    refresh: function(frm) {
        // BUG FIX: Clear progress bar on every refresh to prevent stale data
        $('#creation-progress').remove();
        frm.progress_bar_added = false;
        
        // For Draft documents
        if (frm.doc.docstatus === 0) {
            add_quick_add_buttons(frm);
            
            // Import from CSV button
            frm.add_custom_button(__('Import from CSV'), function() {
                import_from_csv(frm);
            }, __('Import/Export'));
            
            // Download Template button
            frm.add_custom_button(__('Download Template'), function() {
                download_csv_template();
            }, __('Import/Export'));
            
            // Custom submit button with progress dialog
            frm.page.set_primary_action(__('Submit & Create Items'), function() {
                submit_with_progress(frm);
            });
        }
        
        // For Submitted documents
        if (frm.doc.docstatus === 1) {
            render_progress_bar(frm);
            
            // Export to Excel button
            if (frm.doc.items_created > 0) {
                frm.add_custom_button(__('Export to Excel'), function() {
                    export_to_excel(frm);
                }, __('Import/Export'));
            }
            
            // Duplicate button
            frm.add_custom_button(__('Duplicate'), function() {
                duplicate_entry(frm);
            }, __('Actions'));
            
            // Retry Failed button
            if (frm.doc.status === 'Partially Created' || frm.doc.status === 'Failed') {
                frm.add_custom_button(__('Retry Failed Items'), function() {
                    retry_failed_items(frm);
                }, __('Actions'));
            }
            
            // View Items button
            if (frm.doc.items_created > 0) {
                frm.add_custom_button(__('View Created Items'), function() {
                    frappe.set_route('List', 'Item', {
                        'custom_book_item_creator': frm.doc.name
                    });
                }, __('Actions'));
            }
        }
        
        // For Cancelled - allow duplicate
        if (frm.doc.docstatus === 2) {
            frm.add_custom_button(__('Duplicate'), function() {
                duplicate_entry(frm);
            }, __('Actions'));
        }
        
        setup_realtime_listener(frm);
    },
    
    onload: function(frm) {
        // BUG FIX: Clear progress bar on load
        $('#creation-progress').remove();
        frm.progress_bar_added = false;
    },
    
    setup: function(frm) {
        frm.set_query('publication', function() {
            return { filters: { 'disabled': 0 } };
        });
        
        frm.set_query('subject', function() {
            return { filters: { 'disabled': 0 } };
        });
        
        frm.set_query('class', 'class_details', function() {
            return { filters: { 'disabled': 0 } };
        });
    }
});

// Child table events
frappe.ui.form.on('Book Class Detail', {
    rate: function(frm, cdt, cdn) {
        calculate_row_amount(frm, cdt, cdn);
    },
    valuation_rate: function(frm, cdt, cdn) {
        calculate_row_amount(frm, cdt, cdn);
    },
    opening_stock: function(frm, cdt, cdn) {
        calculate_row_amount(frm, cdt, cdn);
        calculate_totals(frm);
    },
    isbn_barcode: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.isbn_barcode) {
            check_isbn_duplicate(frm, row);
        }
    },
    class_details_add: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        row.creation_status = 'Pending';
    },
    class_details_remove: function(frm) {
        calculate_totals(frm);
    }
});

// ========== EXPORT TO EXCEL ==========
function export_to_excel(frm) {
    frappe.call({
        // BUG FIX: Correct API path
        method: 'trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.export_items_to_excel',
        args: { docname: frm.doc.name },
        freeze: true,
        freeze_message: __('Generating Excel file...'),
        callback: function(r) {
            if (r.message && r.message.file_url) {
                window.open(r.message.file_url);
                frappe.show_alert({
                    message: __('Excel file downloaded successfully!'),
                    indicator: 'green'
                });
            }
        }
    });
}

// ========== IMPORT FROM CSV ==========
function import_from_csv(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Import Class Details from CSV'),
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'instructions',
                options: `
                    <div class="alert alert-info">
                        <h5><i class="fa fa-info-circle"></i> CSV Format Instructions:</h5>
                        <p>Your CSV file should have the following columns:</p>
                        <table class="table table-bordered table-sm">
                            <thead><tr>
                                <th>Class</th>
                                <th>Selling Rate</th>
                                <th>Valuation Rate</th>
                                <th>ISBN/Barcode</th>
                                <th>Opening Stock</th>
                            </tr></thead>
                            <tbody><tr>
                                <td>Class 1</td>
                                <td>150</td>
                                <td>100</td>
                                <td>9781234567890</td>
                                <td>50</td>
                            </tr></tbody>
                        </table>
                        <p><strong>Note:</strong> Class names must match exactly with Class Master entries.</p>
                        <button class="btn btn-sm btn-primary" onclick="download_csv_template()">
                            <i class="fa fa-download"></i> Download Template
                        </button>
                    </div>
                `
            },
            {
                fieldtype: 'Attach',
                fieldname: 'csv_file',
                label: __('Select CSV File'),
                reqd: 1,
                options: { restrictions: { allowed_file_types: ['.csv'] } }
            }
        ],
        primary_action_label: __('Import'),
        primary_action: function(values) {
            if (values.csv_file) {
                process_csv_import(frm, values.csv_file, d);
            }
        }
    });
    d.show();
}

function download_csv_template() {
    let csv_content = "Class,Selling Rate,Valuation Rate,ISBN/Barcode,Opening Stock\n";
    csv_content += "Class 1,150,100,9781234567001,50\n";
    csv_content += "Class 2,160,110,9781234567002,45\n";
    csv_content += "Class 3,170,120,9781234567003,40\n";
    
    let blob = new Blob([csv_content], { type: 'text/csv;charset=utf-8;' });
    let link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'book_class_details_template.csv';
    link.click();
    
    frappe.show_alert({
        message: __('Template downloaded!'),
        indicator: 'green'
    });
}

function process_csv_import(frm, file_url, dialog) {
    frappe.call({
        // BUG FIX: Correct API path
        method: 'trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.parse_csv_file',
        args: { file_url: file_url },
        freeze: true,
        freeze_message: __('Processing CSV...'),
        callback: function(r) {
            if (r.message && r.message.success) {
                let rows = r.message.data;
                let added = 0;
                let errors = [];
                
                rows.forEach(function(row, idx) {
                    if (row.class) {
                        let existing = (frm.doc.class_details || []).find(d => d.class === row.class);
                        if (!existing) {
                            let child = frm.add_child('class_details');
                            child.class = row.class;
                            child.rate = parseFloat(row.selling_rate) || 0;
                            child.valuation_rate = parseFloat(row.valuation_rate) || 0;
                            child.isbn_barcode = row.isbn_barcode || '';
                            child.opening_stock = parseFloat(row.opening_stock) || 0;
                            child.creation_status = 'Pending';
                            added++;
                        } else {
                            errors.push(`Row ${idx + 2}: Class "${row.class}" already exists`);
                        }
                    }
                });
                
                frm.refresh_field('class_details');
                calculate_totals(frm);
                dialog.hide();
                
                let msg = `<strong>${added} rows imported successfully!</strong>`;
                if (errors.length > 0) {
                    msg += `<br><br><strong>Skipped:</strong><br>` + errors.join('<br>');
                }
                
                frappe.msgprint({
                    title: __('Import Complete'),
                    message: msg,
                    indicator: added > 0 ? 'green' : 'orange'
                });
            } else {
                frappe.msgprint({
                    title: __('Import Failed'),
                    message: r.message.error || __('Failed to parse CSV file'),
                    indicator: 'red'
                });
            }
        }
    });
}

// ========== DUPLICATE ENTRY ==========
function duplicate_entry(frm) {
    frappe.confirm(
        __('This will create a new Book Item Creator with the same details (except ISBN). Continue?'),
        function() {
            frappe.call({
                // BUG FIX: Correct API path
                method: 'trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.duplicate_book_item_creator',
                args: { docname: frm.doc.name },
                freeze: true,
                freeze_message: __('Creating duplicate...'),
                callback: function(r) {
                    if (r.message && r.message.name) {
                        frappe.show_alert({
                            message: __('Duplicate created: {0}', [r.message.name]),
                            indicator: 'green'
                        });
                        frappe.set_route('Form', 'Book Item Creator', r.message.name);
                    }
                }
            });
        }
    );
}

// ========== SUBMIT WITH PROGRESS ==========
function submit_with_progress(frm) {
    // Validate before submit
    if (!frm.doc.class_details || frm.doc.class_details.length === 0) {
        frappe.throw(__('Please add at least one class detail'));
        return;
    }
    
    for (let row of frm.doc.class_details) {
        if (!row.class) {
            frappe.throw(__('Class is mandatory in Row {0}', [row.idx]));
            return;
        }
        if (!row.rate || row.rate <= 0) {
            frappe.throw(__('Selling Rate must be greater than 0 in Row {0}', [row.idx]));
            return;
        }
        if (!row.valuation_rate || row.valuation_rate <= 0) {
            frappe.throw(__('Valuation Rate must be greater than 0 in Row {0}', [row.idx]));
            return;
        }
        if (!row.isbn_barcode) {
            frappe.throw(__('ISBN/Barcode is mandatory in Row {0}', [row.idx]));
            return;
        }
    }
    
    let total = frm.doc.class_details.length;
    
    // BUG FIX: Show dialog BEFORE submit, not after
    progress_dialog = new frappe.ui.Dialog({
        title: __('📚 Creating Book Items'),
        size: 'large',
        static: true,
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'progress_html',
                options: get_progress_html(0, 0, total)
            }
        ],
        primary_action_label: __('Close'),
        primary_action: function() {
            progress_dialog.hide();
            frm.reload_doc();
        }
    });
    
    progress_dialog.get_primary_btn().prop('disabled', true);
    progress_dialog.show();
    
    // Now submit
    frm.save('Submit').then(() => {
        // Realtime will update the dialog
    }).catch((err) => {
        progress_dialog.hide();
        frappe.msgprint(__('Error submitting document'));
    });
}

function get_progress_html(success, failed, total) {
    let current = success + failed;
    let pending = total - current;
    let percentage = total > 0 ? Math.round((current / total) * 100) : 0;
    let success_pct = total > 0 ? (success / total) * 100 : 0;
    let failed_pct = total > 0 ? (failed / total) * 100 : 0;
    let pending_pct = total > 0 ? (pending / total) * 100 : 0;
    
    let status_text = '⏳ Creating Items... Please wait';
    let status_class = 'text-primary';
    let icon_html = `<div class="spinner-border text-primary" style="width: 60px; height: 60px;" role="status"></div>`;
    
    if (current === total && total > 0) {
        if (failed === 0) {
            status_text = '✅ All Items Created Successfully!';
            status_class = 'text-success';
            icon_html = `<i class="fa fa-check-circle text-success" style="font-size: 60px;"></i>`;
        } else if (success === 0) {
            status_text = '❌ All Items Failed!';
            status_class = 'text-danger';
            icon_html = `<i class="fa fa-times-circle text-danger" style="font-size: 60px;"></i>`;
        } else {
            status_text = '⚠️ Completed with Some Errors';
            status_class = 'text-warning';
            icon_html = `<i class="fa fa-exclamation-circle text-warning" style="font-size: 60px;"></i>`;
        }
    }
    
    return `
        <div class="text-center mb-4 pt-3">
            ${icon_html}
            <h4 class="mt-3 ${status_class}">${status_text}</h4>
            <p class="text-muted mb-0">${current} of ${total} items processed</p>
            <h3 class="text-primary">${percentage}%</h3>
        </div>
        
        <div class="progress mb-4" style="height: 35px; border-radius: 20px; overflow: hidden;">
            ${success > 0 ? `<div class="progress-bar bg-success" style="width: ${success_pct}%; transition: width 0.5s ease;"><strong>${success}</strong></div>` : ''}
            ${failed > 0 ? `<div class="progress-bar bg-danger" style="width: ${failed_pct}%; transition: width 0.5s ease;"><strong>${failed}</strong></div>` : ''}
            ${pending > 0 ? `<div class="progress-bar bg-light text-dark" style="width: ${pending_pct}%; transition: width 0.5s ease;"><strong>${pending}</strong></div>` : ''}
        </div>
        
        <div class="row text-center mt-4">
            <div class="col-4">
                <div class="p-3" style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border-radius: 15px;">
                    <h2 class="text-success mb-1">${success}</h2>
                    <small class="text-success font-weight-bold">✓ Created</small>
                </div>
            </div>
            <div class="col-4">
                <div class="p-3" style="background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%); border-radius: 15px;">
                    <h2 class="text-danger mb-1">${failed}</h2>
                    <small class="text-danger font-weight-bold">✗ Failed</small>
                </div>
            </div>
            <div class="col-4">
                <div class="p-3" style="background: linear-gradient(135deg, #e2e3e5 0%, #d6d8db 100%); border-radius: 15px;">
                    <h2 class="text-secondary mb-1">${pending}</h2>
                    <small class="text-secondary font-weight-bold">◷ Pending</small>
                </div>
            </div>
        </div>
        
        ${current === total && total > 0 ? `
        <div class="mt-4 text-center p-3" style="background: #e8f4fd; border-radius: 10px;">
            <p class="mb-0"><i class="fa fa-info-circle text-primary"></i> Click "Close" to view results.</p>
        </div>
        ` : `
        <div class="mt-4 text-center">
            <p class="text-muted mb-0"><i class="fa fa-clock-o"></i> Please do not close this window...</p>
        </div>
        `}
    `;
}

function update_progress_dialog(success, failed, total) {
    if (progress_dialog && progress_dialog.$wrapper.is(':visible')) {
        progress_dialog.fields_dict.progress_html.$wrapper.html(get_progress_html(success, failed, total));
        if ((success + failed) === total && total > 0) {
            progress_dialog.get_primary_btn().prop('disabled', false);
        }
    }
}

function calculate_row_amount(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    row.amount = flt(row.opening_stock) * flt(row.valuation_rate);
    frm.refresh_field('class_details');
}

function calculate_totals(frm) {
    let total_opening_stock = 0;
    let total_stock_value = 0;
    
    (frm.doc.class_details || []).forEach(function(row) {
        total_opening_stock += flt(row.opening_stock);
        total_stock_value += flt(row.opening_stock) * flt(row.valuation_rate);
    });
    
    frm.set_value('total_opening_stock', total_opening_stock);
    frm.set_value('total_stock_value', total_stock_value);
    frm.set_value('total_items_to_create', (frm.doc.class_details || []).length);
}

function add_quick_add_buttons(frm) {
    frm.add_custom_button(__('All Classes'), function() {
        quick_add_classes(frm, 'all');
    }, __('Quick Add Classes'));
    
    frm.add_custom_button(__('Primary (Nursery-5)'), function() {
        quick_add_classes(frm, 'primary');
    }, __('Quick Add Classes'));
    
    frm.add_custom_button(__('Middle (6-10)'), function() {
        quick_add_classes(frm, 'middle');
    }, __('Quick Add Classes'));
    
    frm.add_custom_button(__('Senior (11-12)'), function() {
        quick_add_classes(frm, 'senior');
    }, __('Quick Add Classes'));
}

function quick_add_classes(frm, class_type) {
    frappe.call({
        // BUG FIX: Correct API path
        method: 'trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.get_classes_for_quick_add',
        args: { class_type: class_type },
        freeze: true,
        freeze_message: __('Loading classes...'),
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                let existing_classes = (frm.doc.class_details || []).map(row => row.class);
                
                r.message.forEach(function(cls) {
                    if (!existing_classes.includes(cls.name)) {
                        let row = frm.add_child('class_details');
                        row.class = cls.name;
                        row.creation_status = 'Pending';
                    }
                });
                
                frm.refresh_field('class_details');
                calculate_totals(frm);
                
                frappe.show_alert({
                    message: __('Added {0} classes', [r.message.length]),
                    indicator: 'green'
                });
            }
        }
    });
}

function check_isbn_duplicate(frm, row) {
    frappe.call({
        // BUG FIX: Correct API path
        method: 'trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.check_isbn_exists',
        args: {
            isbn_barcode: row.isbn_barcode,
            exclude_doc: frm.doc.name
        },
        callback: function(r) {
            if (r.message && r.message.exists) {
                frappe.show_alert({
                    message: __('ISBN {0} already exists in {1}: {2}', 
                        [row.isbn_barcode, r.message.type, r.message.name]),
                    indicator: 'orange'
                });
            }
        }
    });
}

function render_progress_bar(frm) {
    // BUG FIX: Only show for submitted documents
    if (frm.doc.docstatus !== 1) {
        $('#creation-progress').remove();
        return;
    }
    
    // BUG FIX: Calculate from actual child table rows, not summary fields
    let total = (frm.doc.class_details || []).length;
    let created = 0, failed = 0, pending = 0;
    
    (frm.doc.class_details || []).forEach(function(row) {
        if (row.creation_status === 'Created') created++;
        else if (row.creation_status === 'Failed') failed++;
        else pending++;
    });
    
    if (total === 0) {
        $('#creation-progress').remove();
        return;
    }
    
    let created_pct = (created / total) * 100;
    let failed_pct = (failed / total) * 100;
    let pending_pct = (pending / total) * 100;
    
    let html = `
        <div class="progress-section mb-4 mt-4 p-3" style="background: #f8f9fa; border-radius: 8px;">
            <div class="d-flex justify-content-between mb-2">
                <span><strong>Status:</strong> <span class="indicator-pill ${get_status_color(frm.doc.status)}">${frm.doc.status || 'Pending'}</span></span>
                <span><strong>${created}</strong> of <strong>${total}</strong> items created</span>
            </div>
            <div class="progress" style="height: 25px;">
                ${created > 0 ? `<div class="progress-bar bg-success" style="width: ${created_pct}%">${created} Created</div>` : ''}
                ${failed > 0 ? `<div class="progress-bar bg-danger" style="width: ${failed_pct}%">${failed} Failed</div>` : ''}
                ${pending > 0 ? `<div class="progress-bar bg-secondary" style="width: ${pending_pct}%">${pending} Pending</div>` : ''}
            </div>
        </div>
    `;
    
    // BUG FIX: Always remove and re-add
    $('#creation-progress').remove();
    $(frm.fields_dict.status.$wrapper).after(`<div id="creation-progress">${html}</div>`);
}

function get_status_color(status) {
    switch(status) {
        case 'Completed': return 'green';
        case 'Partially Created': return 'orange';
        case 'Failed': return 'red';
        case 'In Progress': return 'blue';
        default: return 'grey';
    }
}

function setup_realtime_listener(frm) {
    // BUG FIX: Remove existing listener to prevent duplicates
    frappe.realtime.off('book_item_creation_progress');
    
    frappe.realtime.on('book_item_creation_progress', function(data) {
        if (data.docname === frm.doc.name) {
            // BUG FIX: Use correct field names from Python
            update_progress_dialog(data.success || 0, data.failed || 0, data.total || 0);
        }
    });
}

function retry_failed_items(frm) {
    let failed_count = (frm.doc.class_details || []).filter(r => r.creation_status === 'Failed').length;
    
    progress_dialog = new frappe.ui.Dialog({
        title: __('🔄 Retrying Failed Items'),
        size: 'large',
        static: true,
        fields: [{ fieldtype: 'HTML', fieldname: 'progress_html', options: get_progress_html(0, 0, failed_count) }],
        primary_action_label: __('Close'),
        primary_action: function() { progress_dialog.hide(); frm.reload_doc(); }
    });
    
    progress_dialog.get_primary_btn().prop('disabled', true);
    progress_dialog.show();
    
    frappe.call({
        // BUG FIX: Correct API path
        method: 'trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.retry_failed_items',
        args: { docname: frm.doc.name },
        callback: function(r) {
            if (r.message) {
                update_progress_dialog(r.message.success, r.message.total_failed - r.message.success, r.message.total_failed);
                progress_dialog.get_primary_btn().prop('disabled', false);
            }
        }
    });
}

// Make template download function global for HTML onclick
window.download_csv_template = download_csv_template;
