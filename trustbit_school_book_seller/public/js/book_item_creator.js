// Copyright (c) 2024, Trustbit and contributors
// For license information, please see license.txt

frappe.ui.form.on('Book Item Creator', {
    refresh: function(frm) {
        // Add Quick Add Classes buttons
        if (frm.doc.docstatus === 0) {
            add_quick_add_buttons(frm);
        }
        
        // Show progress bar for submitted documents
        if (frm.doc.docstatus === 1) {
            render_progress_bar(frm);
            
            // Add retry button if there are failed items
            if (frm.doc.status === 'Partially Created' || frm.doc.status === 'Failed') {
                frm.add_custom_button(__('Retry Failed Items'), function() {
                    retry_failed_items(frm);
                }, __('Actions'));
            }
            
            // Add view items button
            if (frm.doc.items_created > 0) {
                frm.add_custom_button(__('View Created Items'), function() {
                    frappe.set_route('List', 'Item', {
                        'custom_book_item_creator': frm.doc.name
                    });
                }, __('Actions'));
            }
        }
        
        // Setup realtime listener for progress updates
        setup_realtime_listener(frm);
    },
    
    setup: function(frm) {
        // Set query filters
        frm.set_query('publication', function() {
            return {
                filters: { 'disabled': 0 }
            };
        });
        
        frm.set_query('subject', function() {
            return {
                filters: { 'disabled': 0 }
            };
        });
        
        frm.set_query('class', 'class_details', function() {
            return {
                filters: { 'disabled': 0 }
            };
        });
        
        frm.set_query('selling_price_list', function() {
            return {
                filters: { 'selling': 1 }
            };
        });
        
        frm.set_query('buying_price_list', function() {
            return {
                filters: { 'buying': 1 }
            };
        });
    },
    
    validate: function(frm) {
        // Validate class details before save
        if (!frm.doc.class_details || frm.doc.class_details.length === 0) {
            frappe.throw(__('Please add at least one class detail'));
        }
        
        // Check for duplicate classes
        let classes = [];
        frm.doc.class_details.forEach(function(row) {
            if (classes.includes(row.class)) {
                frappe.throw(__('Duplicate class {0} found in row {1}', [row.class, row.idx]));
            }
            classes.push(row.class);
        });
    },
    
    before_submit: function(frm) {
        // Confirm before submit
        return new Promise((resolve, reject) => {
            frappe.confirm(
                __('This will create {0} items. Are you sure you want to proceed?', 
                    [frm.doc.class_details.length]),
                function() {
                    resolve();
                },
                function() {
                    reject();
                }
            );
        });
    }
});

frappe.ui.form.on('Book Class Detail', {
    isbn_barcode: function(frm, cdt, cdn) {
        // Check for duplicate ISBN when entered
        let row = locals[cdt][cdn];
        if (row.isbn_barcode) {
            check_isbn_duplicate(frm, row);
        }
    },
    
    rate: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    
    valuation_rate: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    
    opening_stock: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    
    class_details_remove: function(frm) {
        calculate_totals(frm);
    }
});

// Helper Functions

function add_quick_add_buttons(frm) {
    // Quick Add All Classes (1-12)
    frm.add_custom_button(__('All Classes (1-12)'), function() {
        quick_add_classes(frm, 'all');
    }, __('Quick Add Classes'));
    
    // Quick Add Primary Classes (Nursery - Class 5)
    frm.add_custom_button(__('Primary (Nursery-5)'), function() {
        quick_add_classes(frm, 'primary');
    }, __('Quick Add Classes'));
    
    // Quick Add Middle Classes (Class 6-10)
    frm.add_custom_button(__('Middle (6-10)'), function() {
        quick_add_classes(frm, 'middle');
    }, __('Quick Add Classes'));
    
    // Quick Add Senior Classes (Class 11-12)
    frm.add_custom_button(__('Senior (11-12)'), function() {
        quick_add_classes(frm, 'senior');
    }, __('Quick Add Classes'));
}

function quick_add_classes(frm, class_type) {
    frappe.call({
        method: 'trustbit_school_book_seller.trustbit_school_book_seller.doctype.book_item_creator.book_item_creator.get_classes_for_quick_add',
        args: { class_type: class_type },
        freeze: true,
        freeze_message: __('Loading classes...'),
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                // Get existing classes in the table
                let existing_classes = [];
                frm.doc.class_details.forEach(function(row) {
                    if (row.class) {
                        existing_classes.push(row.class);
                    }
                });
                
                // Add only classes that don't exist
                let added_count = 0;
                r.message.forEach(function(cls) {
                    if (!existing_classes.includes(cls.name)) {
                        let row = frm.add_child('class_details');
                        row.class = cls.name;
                        row.opening_stock = 0;
                        row.creation_status = 'Pending';
                        added_count++;
                    }
                });
                
                frm.refresh_field('class_details');
                
                if (added_count > 0) {
                    frappe.show_alert({
                        message: __('Added {0} classes', [added_count]),
                        indicator: 'green'
                    });
                } else {
                    frappe.show_alert({
                        message: __('All selected classes already exist in the table'),
                        indicator: 'orange'
                    });
                }
                
                calculate_totals(frm);
            }
        }
    });
}

function check_isbn_duplicate(frm, row) {
    frappe.call({
        method: 'trustbit_school_book_seller.trustbit_school_book_seller.doctype.book_item_creator.book_item_creator.check_isbn_exists',
        args: {
            isbn_barcode: row.isbn_barcode,
            exclude_doc: frm.doc.name
        },
        callback: function(r) {
            if (r.message && r.message.exists) {
                frappe.show_alert({
                    message: __('ISBN {0} already exists in {1}: {2}', 
                        [row.isbn_barcode, r.message.type, r.message.name]),
                    indicator: 'red'
                }, 10);
                
                // Clear the ISBN field
                frappe.model.set_value(row.doctype, row.name, 'isbn_barcode', '');
            }
        }
    });
}

function calculate_totals(frm) {
    let total_items = frm.doc.class_details.length;
    let total_opening_stock = 0;
    let total_stock_value = 0;
    
    frm.doc.class_details.forEach(function(row) {
        total_opening_stock += flt(row.opening_stock);
        total_stock_value += flt(row.opening_stock) * flt(row.valuation_rate);
    });
    
    frm.set_value('total_items_to_create', total_items);
    frm.set_value('total_opening_stock', total_opening_stock);
    frm.set_value('total_stock_value', total_stock_value);
}

function render_progress_bar(frm) {
    let total = frm.doc.total_items_to_create || 0;
    let created = frm.doc.items_created || 0;
    let failed = 0;
    let pending = 0;
    
    // Count statuses
    frm.doc.class_details.forEach(function(row) {
        if (row.creation_status === 'Failed') failed++;
        else if (row.creation_status === 'Pending' || row.creation_status === 'Creating') pending++;
    });
    
    let percentage = total > 0 ? Math.round((created / total) * 100) : 0;
    
    // Determine status color
    let status_color = 'blue';
    let status_text = frm.doc.status;
    
    if (frm.doc.status === 'Completed') {
        status_color = 'green';
    } else if (frm.doc.status === 'Failed') {
        status_color = 'red';
    } else if (frm.doc.status === 'Partially Created') {
        status_color = 'orange';
    } else if (frm.doc.status === 'In Progress') {
        status_color = 'blue';
    }
    
    let html = `
        <div class="progress-container" style="margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                <span class="text-muted">
                    <strong>Status:</strong> 
                    <span class="indicator-pill ${status_color}">${status_text}</span>
                </span>
                <span class="text-muted">
                    <strong>${created}</strong> of <strong>${total}</strong> items created (${percentage}%)
                </span>
            </div>
            
            <div class="progress" style="height: 25px; border-radius: 5px;">
                <div class="progress-bar bg-success" role="progressbar" 
                    style="width: ${(created/total)*100}%;" 
                    aria-valuenow="${created}" aria-valuemin="0" aria-valuemax="${total}">
                    ${created > 0 ? created + ' Created' : ''}
                </div>
                <div class="progress-bar bg-danger" role="progressbar" 
                    style="width: ${(failed/total)*100}%;" 
                    aria-valuenow="${failed}" aria-valuemin="0" aria-valuemax="${total}">
                    ${failed > 0 ? failed + ' Failed' : ''}
                </div>
                <div class="progress-bar bg-secondary" role="progressbar" 
                    style="width: ${(pending/total)*100}%;" 
                    aria-valuenow="${pending}" aria-valuemin="0" aria-valuemax="${total}">
                    ${pending > 0 ? pending + ' Pending' : ''}
                </div>
            </div>
            
            <div style="display: flex; justify-content: space-around; margin-top: 15px;">
                <div class="text-center">
                    <div class="h4 mb-0 text-success">${created}</div>
                    <small class="text-muted">Created</small>
                </div>
                <div class="text-center">
                    <div class="h4 mb-0 text-danger">${failed}</div>
                    <small class="text-muted">Failed</small>
                </div>
                <div class="text-center">
                    <div class="h4 mb-0 text-secondary">${pending}</div>
                    <small class="text-muted">Pending</small>
                </div>
            </div>
        </div>
    `;
    
    frm.fields_dict.progress_html.$wrapper.html(html);
}

function setup_realtime_listener(frm) {
    frappe.realtime.on('book_item_creation_progress', function(data) {
        if (data.docname === frm.doc.name) {
            // Update the progress display
            let current = data.current;
            let total = data.total;
            let percentage = Math.round((current / total) * 100);
            
            frappe.show_alert({
                message: __('Creating item for {0}: {1} ({2}/{3})', 
                    [data.class, data.status, current, total]),
                indicator: data.status === 'Created' ? 'green' : 'red'
            });
            
            // Refresh form if completed
            if (current === total) {
                setTimeout(function() {
                    frm.reload_doc();
                }, 1000);
            }
        }
    });
}

function retry_failed_items(frm) {
    frappe.confirm(
        __('This will retry creating all failed items. Continue?'),
        function() {
            frappe.call({
                method: 'trustbit_school_book_seller.trustbit_school_book_seller.doctype.book_item_creator.book_item_creator.retry_failed_items',
                args: { docname: frm.doc.name },
                freeze: true,
                freeze_message: __('Retrying failed items...'),
                callback: function(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: __('Successfully created {0} out of {1} failed items', 
                                [r.message.success, r.message.total_failed]),
                            indicator: r.message.success === r.message.total_failed ? 'green' : 'orange'
                        });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}

// Utility function
function flt(value) {
    return parseFloat(value) || 0;
}
