# Copyright (c) 2024, Trustbit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, flt, cint
import csv
import os


class BookItemCreator(Document):
    def validate(self):
        self.validate_class_details()
        self.check_duplicate_isbn()
        self.check_duplicate_class()
        self.calculate_totals()
    
    def validate_class_details(self):
        """Validate that class details are filled properly"""
        if not self.class_details:
            frappe.throw(_("Please add at least one class detail"))
        
        for row in self.class_details:
            # BUG FIX: Use row.get('class') instead of row.class_field
            if not row.get('class'):
                frappe.throw(_("Class is mandatory in Row {0}").format(row.idx))
            if flt(row.rate) <= 0:
                frappe.throw(_("Selling Rate must be greater than 0 in Row {0}").format(row.idx))
            if flt(row.valuation_rate) <= 0:
                frappe.throw(_("Valuation Rate must be greater than 0 in Row {0}").format(row.idx))
            if not row.isbn_barcode:
                frappe.throw(_("ISBN/Barcode is mandatory in Row {0}").format(row.idx))
    
    def check_duplicate_isbn(self):
        """Check for duplicate ISBN in existing items and other book creators"""
        for row in self.class_details:
            # Check in existing Items
            existing_item = frappe.db.get_value(
                "Item", 
                {"custom_isbn_barcode": row.isbn_barcode}, 
                ["name", "item_name"],
                as_dict=True
            )
            if existing_item:
                frappe.throw(
                    _("ISBN/Barcode {0} already exists in Item {1} ({2})").format(
                        row.isbn_barcode, existing_item.name, existing_item.item_name
                    )
                )
            
            # Check in other submitted Book Item Creators
            duplicate = frappe.db.sql("""
                SELECT bic.name, bcd.class
                FROM `tabBook Class Detail` bcd
                INNER JOIN `tabBook Item Creator` bic ON bcd.parent = bic.name
                WHERE bcd.isbn_barcode = %s AND bic.name != %s AND bic.docstatus = 1
            """, (row.isbn_barcode, self.name), as_dict=True)
            
            if duplicate:
                frappe.throw(
                    _("ISBN/Barcode {0} already used in {1} for {2}").format(
                        row.isbn_barcode, duplicate[0].name, duplicate[0].get('class')
                    )
                )
    
    def check_duplicate_class(self):
        """Check for duplicate classes in the same document"""
        classes = []
        for row in self.class_details:
            class_name = row.get('class')
            if class_name in classes:
                frappe.throw(_("Duplicate Class {0} in Row {1}").format(class_name, row.idx))
            classes.append(class_name)
    
    def calculate_totals(self):
        """Calculate summary totals"""
        self.total_items_to_create = len(self.class_details)
        self.total_opening_stock = sum(flt(row.opening_stock) for row in self.class_details)
        self.total_stock_value = sum(
            flt(row.opening_stock) * flt(row.valuation_rate) for row in self.class_details
        )
    
    def on_submit(self):
        """Create items on submit"""
        # BUG FIX: Use db_set with update_modified=False for submitted docs
        self.db_set("status", "In Progress", update_modified=False)
        frappe.db.commit()
        self.create_items()
    
    def on_cancel(self):
        """Handle cancellation"""
        # BUG FIX: Use db_set with update_modified=False for submitted docs
        self.db_set("status", "Cancelled", update_modified=False)
    
    def create_items(self):
        """Create items for each class detail row"""
        success_count = 0
        failed_count = 0
        
        for row in self.class_details:
            try:
                # BUG FIX: Use frappe.db.set_value instead of row.db_set
                frappe.db.set_value("Book Class Detail", row.name, "creation_status", "Creating", update_modified=False)
                
                # Create the item
                item = self.create_single_item(row)
                
                if item:
                    # BUG FIX: Use frappe.db.set_value for updating child table rows
                    frappe.db.set_value("Book Class Detail", row.name, {
                        "generated_item_code": item.name,
                        "item_link": item.name,
                        "item_created": 1,
                        "creation_status": "Created",
                        "creation_timestamp": now_datetime()
                    }, update_modified=False)
                    
                    # Create price list entries
                    try:
                        self.create_price_list_entries(item.name, row)
                    except Exception as e:
                        frappe.log_error(f"Price List Error for {item.name}: {str(e)}")
                    
                    # Create stock entry if opening stock > 0
                    if flt(row.opening_stock) > 0:
                        try:
                            stock_entry = self.create_stock_entry(item.name, row)
                            frappe.db.set_value("Book Class Detail", row.name, "stock_entry_created", 1, update_modified=False)
                        except Exception as e:
                            frappe.log_error(f"Stock Entry Error for {item.name}: {str(e)}")
                    
                    success_count += 1
                else:
                    frappe.db.set_value("Book Class Detail", row.name, {
                        "creation_status": "Failed",
                        "remarks": "Item creation returned None"
                    }, update_modified=False)
                    failed_count += 1
                    
            except Exception as e:
                frappe.db.set_value("Book Class Detail", row.name, {
                    "creation_status": "Failed",
                    "remarks": str(e)[:200]
                }, update_modified=False)
                failed_count += 1
                frappe.log_error(title=f"Book Item Creation Failed: {self.name}", message=str(e))
            
            frappe.db.commit()
            
            # Publish realtime progress
            frappe.publish_realtime(
                "book_item_creation_progress",
                {
                    "docname": self.name,
                    "current": success_count + failed_count,
                    "total": len(self.class_details),
                    "success": success_count,
                    "failed": failed_count
                },
                user=frappe.session.user
            )
        
        # Update final status
        # BUG FIX: Use frappe.db.set_value for submitted documents
        if failed_count == 0:
            final_status = "Completed"
        elif success_count == 0:
            final_status = "Failed"
        else:
            final_status = "Partially Created"
        
        frappe.db.set_value("Book Item Creator", self.name, {
            "items_created": success_count,
            "status": final_status
        }, update_modified=False)
        
        frappe.db.commit()
        
        return {
            "success": success_count,
            "failed": failed_count,
            "total": len(self.class_details)
        }
    
    def create_single_item(self, row):
        """Create a single item from class detail row"""
        publication_name = frappe.db.get_value("Publication", self.publication, "publication_name")
        class_name = row.get('class')
        
        # Generate item name: Publication Book Class
        item_name = f"{publication_name} {self.book_name} {class_name}"
        
        # Create item
        item = frappe.get_doc({
            "doctype": "Item",
            "item_name": item_name,
            "item_group": self.item_group,
            "stock_uom": self.uom,
            "is_stock_item": 1,
            "include_item_in_manufacturing": 0,
            "default_warehouse": self.default_warehouse,
            "description": f"{item_name} - {self.subject}",
            
            # Custom fields
            "custom_publication": self.publication,
            "custom_subject": self.subject,
            "custom_class": class_name,
            "custom_author": self.author,
            "custom_edition": self.edition,
            "custom_publication_year": self.publication_year,
            "custom_isbn_barcode": row.isbn_barcode,
            "custom_sales_discount_percent": self.sales_discount_percent,
            "custom_purchase_discount_percent": self.purchase_discount_percent,
            "custom_book_item_creator": self.name,
            
            # BUG FIX: Use empty string for barcode_type to accept any format
            # Using "EAN" requires strict 13-digit format with checksum
            "barcodes": [{
                "barcode": row.isbn_barcode,
                "barcode_type": ""
            }]
        })
        
        # Add HSN code if provided
        if self.hsn_sac_code:
            item.gst_hsn_code = self.hsn_sac_code
        
        # Set valuation rate
        item.valuation_rate = row.valuation_rate
        
        item.insert(ignore_permissions=True)
        
        return item
    
    def create_price_list_entries(self, item_code, row):
        """Create selling and buying price list entries"""
        # Selling Price
        if self.selling_price_list:
            selling_price = frappe.get_doc({
                "doctype": "Item Price",
                "item_code": item_code,
                "price_list": self.selling_price_list,
                "price_list_rate": row.rate,
                "selling": 1
            })
            selling_price.insert(ignore_permissions=True)
        
        # Buying Price (using valuation rate)
        if self.buying_price_list:
            buying_price = frappe.get_doc({
                "doctype": "Item Price",
                "item_code": item_code,
                "price_list": self.buying_price_list,
                "price_list_rate": row.valuation_rate,
                "buying": 1
            })
            buying_price.insert(ignore_permissions=True)
    
    def create_stock_entry(self, item_code, row):
        """Create stock entry for opening stock"""
        stock_entry = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
            "items": [{
                "item_code": item_code,
                "qty": row.opening_stock,
                "t_warehouse": self.default_warehouse,
                "basic_rate": row.valuation_rate,
                "allow_zero_valuation_rate": 0
            }]
        })
        stock_entry.insert(ignore_permissions=True)
        stock_entry.submit()
        
        return stock_entry


# ========== WHITELISTED API FUNCTIONS ==========
# NOTE: These paths are called from JavaScript
# The correct path format is: trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.function_name

@frappe.whitelist()
def get_classes_for_quick_add(class_type="all"):
    """Get classes for quick add button"""
    filters = {"disabled": 0}
    
    if class_type == "primary":
        # Nursery to Class 5
        filters["sort_order"] = ["<=", 8]
    elif class_type == "middle":
        # Class 6 to Class 10
        filters["sort_order"] = ["between", [9, 13]]
    elif class_type == "senior":
        # Class 11 and 12
        filters["sort_order"] = [">=", 14]
    
    classes = frappe.get_all(
        "Class Master",
        filters=filters,
        fields=["name", "class_name", "short_code", "sort_order"],
        order_by="sort_order"
    )
    
    return classes


@frappe.whitelist()
def check_isbn_exists(isbn_barcode, exclude_doc=None):
    """Check if ISBN already exists"""
    # Check in Items
    item = frappe.db.get_value(
        "Item",
        {"custom_isbn_barcode": isbn_barcode},
        ["name", "item_name"],
        as_dict=True
    )
    if item:
        return {
            "exists": True,
            "type": "Item",
            "name": item.name,
            "item_name": item.item_name
        }
    
    # Check in submitted Book Item Creators
    duplicate = frappe.db.sql("""
        SELECT bic.name, bcd.class
        FROM `tabBook Class Detail` bcd
        INNER JOIN `tabBook Item Creator` bic ON bcd.parent = bic.name
        WHERE bcd.isbn_barcode = %s AND bic.docstatus = 1
    """, (isbn_barcode,), as_dict=True)
    
    if duplicate:
        return {
            "exists": True,
            "type": "Book Item Creator",
            "name": duplicate[0].name,
            "class": duplicate[0].get('class')
        }
    
    return {"exists": False}


@frappe.whitelist()
def retry_failed_items(docname):
    """Retry creating failed items"""
    doc = frappe.get_doc("Book Item Creator", docname)
    
    if doc.docstatus != 1:
        frappe.throw(_("Document must be submitted to retry"))
    
    failed_rows = [row for row in doc.class_details if row.creation_status == "Failed"]
    
    if not failed_rows:
        frappe.throw(_("No failed items to retry"))
    
    success_count = 0
    
    for row in failed_rows:
        try:
            item = doc.create_single_item(row)
            if item:
                # BUG FIX: Use frappe.db.set_value for submitted docs
                frappe.db.set_value("Book Class Detail", row.name, {
                    "generated_item_code": item.name,
                    "item_link": item.name,
                    "item_created": 1,
                    "creation_status": "Created",
                    "creation_timestamp": now_datetime(),
                    "remarks": "Created on retry"
                }, update_modified=False)
                
                # Create price list entries
                doc.create_price_list_entries(item.name, row)
                
                # Create stock entry if needed
                if flt(row.opening_stock) > 0:
                    doc.create_stock_entry(item.name, row)
                    frappe.db.set_value("Book Class Detail", row.name, "stock_entry_created", 1, update_modified=False)
                
                success_count += 1
        except Exception as e:
            frappe.db.set_value("Book Class Detail", row.name, "remarks", f"Retry failed: {str(e)[:150]}", update_modified=False)
    
    # Update counts
    total_created = frappe.db.count("Book Class Detail", {"parent": docname, "creation_status": "Created"})
    total_rows = len(doc.class_details)
    
    if total_created == total_rows:
        new_status = "Completed"
    elif total_created > 0:
        new_status = "Partially Created"
    else:
        new_status = "Failed"
    
    frappe.db.set_value("Book Item Creator", docname, {
        "items_created": total_created,
        "status": new_status
    }, update_modified=False)
    
    frappe.db.commit()
    
    return {"success": success_count, "total_failed": len(failed_rows)}


@frappe.whitelist()
def export_items_to_excel(docname):
    """Export created items to Excel/CSV"""
    doc = frappe.get_doc("Book Item Creator", docname)
    
    if doc.docstatus != 1:
        frappe.throw(_("Document must be submitted to export"))
    
    # Get created items
    items_data = []
    for row in doc.class_details:
        if row.creation_status == "Created" and row.generated_item_code:
            item = frappe.get_doc("Item", row.generated_item_code)
            items_data.append({
                "Item Code": item.name,
                "Item Name": item.item_name,
                "Class": row.get('class'),
                "Publication": doc.publication,
                "Subject": doc.subject,
                "Author": doc.author,
                "ISBN/Barcode": row.isbn_barcode,
                "Selling Rate": row.rate,
                "Valuation Rate": row.valuation_rate,
                "Opening Stock": row.opening_stock,
                "Stock Value": flt(row.opening_stock) * flt(row.valuation_rate),
                "Item Group": item.item_group,
                "UOM": item.stock_uom,
                "Warehouse": doc.default_warehouse,
                "Creation Date": str(row.creation_timestamp) if row.creation_timestamp else ""
            })
    
    if not items_data:
        frappe.throw(_("No items to export"))
    
    # Create CSV file
    from frappe.utils.file_manager import save_file
    import io
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=items_data[0].keys())
    writer.writeheader()
    writer.writerows(items_data)
    
    file_content = output.getvalue().encode('utf-8')
    file_name = f"Book_Items_{docname}_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.csv"
    
    file_doc = save_file(
        file_name,
        file_content,
        "Book Item Creator",
        docname,
        is_private=0
    )
    
    return {"file_url": file_doc.file_url, "file_name": file_name}


@frappe.whitelist()
def parse_csv_file(file_url):
    """Parse uploaded CSV file for import"""
    try:
        # Get file path
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()
        
        if not os.path.exists(file_path):
            return {"success": False, "error": "File not found"}
        
        data = []
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalize column names
                normalized = {}
                for key, value in row.items():
                    key_lower = key.lower().strip()
                    if 'class' in key_lower:
                        normalized['class'] = value.strip() if value else ''
                    elif 'selling' in key_lower or key_lower == 'rate':
                        normalized['selling_rate'] = value.strip() if value else '0'
                    elif 'valuation' in key_lower:
                        normalized['valuation_rate'] = value.strip() if value else '0'
                    elif 'isbn' in key_lower or 'barcode' in key_lower:
                        normalized['isbn_barcode'] = value.strip() if value else ''
                    elif 'stock' in key_lower or 'opening' in key_lower:
                        normalized['opening_stock'] = value.strip() if value else '0'
                
                if normalized.get('class'):
                    # Validate class exists
                    if frappe.db.exists("Class Master", normalized['class']):
                        data.append(normalized)
                    else:
                        frappe.log_error(f"Class not found: {normalized['class']}")
        
        return {"success": True, "data": data}
    
    except Exception as e:
        frappe.log_error(title="CSV Parse Error", message=str(e))
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def duplicate_book_item_creator(docname):
    """Create a duplicate of Book Item Creator"""
    source_doc = frappe.get_doc("Book Item Creator", docname)
    
    new_doc = frappe.new_doc("Book Item Creator")
    
    # Copy main fields
    fields_to_copy = [
        'publication', 'subject', 'book_name', 'author', 'edition',
        'publication_year', 'sales_discount_percent', 'purchase_discount_percent',
        'selling_price_list', 'buying_price_list', 'item_group', 'hsn_sac_code',
        'default_warehouse', 'uom'
    ]
    
    for field in fields_to_copy:
        if hasattr(source_doc, field):
            setattr(new_doc, field, getattr(source_doc, field))
    
    # Copy class details WITHOUT ISBN (user must enter new ISBNs)
    for row in source_doc.class_details:
        new_row = new_doc.append('class_details')
        new_row.set('class', row.get('class'))
        new_row.rate = row.rate
        new_row.valuation_rate = row.valuation_rate
        new_row.opening_stock = row.opening_stock
        new_row.isbn_barcode = ''  # Clear ISBN - must be unique
        new_row.creation_status = 'Pending'
    
    new_doc.status = 'Draft'
    new_doc.items_created = 0
    new_doc.insert(ignore_permissions=True)
    
    return {"name": new_doc.name, "message": _("Duplicate created. Please enter new ISBN/Barcodes.")}
