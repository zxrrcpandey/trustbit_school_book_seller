# Copyright (c) 2024, Trustbit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, flt, cint


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
            if not row.class_field if hasattr(row, 'class_field') else not row.get('class'):
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
                        row.isbn_barcode, 
                        existing_item.name,
                        existing_item.item_name
                    )
                )
            
            # Check in other submitted Book Item Creators
            duplicate = frappe.db.sql("""
                SELECT bic.name, bcd.class
                FROM `tabBook Class Detail` bcd
                INNER JOIN `tabBook Item Creator` bic ON bcd.parent = bic.name
                WHERE bcd.isbn_barcode = %s 
                AND bic.name != %s 
                AND bic.docstatus = 1
            """, (row.isbn_barcode, self.name), as_dict=True)
            
            if duplicate:
                frappe.throw(
                    _("ISBN/Barcode {0} already used in {1} for {2}").format(
                        row.isbn_barcode,
                        duplicate[0].name,
                        duplicate[0].get('class')
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
            flt(row.opening_stock) * flt(row.valuation_rate) 
            for row in self.class_details
        )
    
    def on_submit(self):
        """Create items on submit"""
        self.status = "In Progress"
        self.db_set("status", "In Progress")
        frappe.db.commit()
        
        # Create items
        self.create_items()
    
    def on_cancel(self):
        """Handle cancellation"""
        self.status = "Cancelled"
        self.db_set("status", "Cancelled")
    
    def create_items(self):
        """Create items for each class detail row"""
        success_count = 0
        failed_count = 0
        
        # Clear existing creation log
        self.creation_log = []
        
        for row in self.class_details:
            log_entry = {
                "class": row.get('class'),
                "timestamp": now_datetime(),
                "item_creation_status": "Pending",
                "stock_entry_status": "Pending",
                "price_list_status": "Pending"
            }
            
            try:
                # Update row status
                row.creation_status = "Creating"
                row.db_set("creation_status", "Creating")
                
                # Create the item
                item = self.create_single_item(row)
                
                if item:
                    # Update row with created item details
                    row.generated_item_code = item.name
                    row.item_link = item.name
                    row.item_created = 1
                    row.creation_status = "Created"
                    row.creation_timestamp = now_datetime()
                    row.db_update()
                    
                    log_entry["item_code"] = item.name
                    log_entry["item_creation_status"] = "Created"
                    
                    # Create price list entries
                    try:
                        self.create_price_list_entries(item.name, row)
                        log_entry["price_list_status"] = "Created"
                    except Exception as e:
                        log_entry["price_list_status"] = "Failed"
                        log_entry["remarks"] = str(e)
                    
                    # Create stock entry if opening stock > 0
                    if flt(row.opening_stock) > 0:
                        try:
                            stock_entry = self.create_stock_entry(item.name, row)
                            row.stock_entry_created = 1
                            row.db_set("stock_entry_created", 1)
                            log_entry["stock_entry_status"] = "Created"
                            log_entry["stock_entry_link"] = stock_entry.name
                        except Exception as e:
                            log_entry["stock_entry_status"] = "Failed"
                            if log_entry.get("remarks"):
                                log_entry["remarks"] += f"; Stock Entry Error: {str(e)}"
                            else:
                                log_entry["remarks"] = f"Stock Entry Error: {str(e)}"
                    else:
                        log_entry["stock_entry_status"] = "Skipped"
                    
                    success_count += 1
                else:
                    row.creation_status = "Failed"
                    row.remarks = "Item creation returned None"
                    row.db_update()
                    log_entry["item_creation_status"] = "Failed"
                    log_entry["remarks"] = "Item creation returned None"
                    failed_count += 1
                    
            except Exception as e:
                row.creation_status = "Failed"
                row.remarks = str(e)
                row.db_update()
                log_entry["item_creation_status"] = "Failed"
                log_entry["remarks"] = str(e)
                failed_count += 1
                frappe.log_error(
                    title=f"Book Item Creation Failed: {self.name}",
                    message=str(e)
                )
            
            # Add log entry
            self.append("creation_log", log_entry)
            frappe.db.commit()
            
            # Publish realtime progress
            frappe.publish_realtime(
                "book_item_creation_progress",
                {
                    "docname": self.name,
                    "current": success_count + failed_count,
                    "total": len(self.class_details),
                    "status": log_entry["item_creation_status"],
                    "item_code": log_entry.get("item_code", ""),
                    "class": row.get('class')
                },
                user=frappe.session.user
            )
        
        # Update final status
        self.items_created = success_count
        
        if failed_count == 0:
            self.status = "Completed"
        elif success_count == 0:
            self.status = "Failed"
        else:
            self.status = "Partially Created"
        
        self.save()
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
            
            # Barcode
            "barcodes": [{
                "barcode": row.isbn_barcode,
                "barcode_type": "EAN"
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


@frappe.whitelist()
def get_classes_for_quick_add(class_type="all"):
    """Get classes for quick add button"""
    filters = {"disabled": 0}
    
    if class_type == "primary":
        # Nursery to Class 5
        filters["display_order"] = ["<=", 8]
    elif class_type == "middle":
        # Class 6 to Class 10
        filters["display_order"] = ["between", [9, 13]]
    elif class_type == "senior":
        # Class 11 and 12
        filters["display_order"] = [">=", 14]
    
    classes = frappe.get_all(
        "Class Master",
        filters=filters,
        fields=["name", "class_name", "short_code", "display_order"],
        order_by="display_order"
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
    filters = {"isbn_barcode": isbn_barcode, "docstatus": 1}
    
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
                row.generated_item_code = item.name
                row.item_link = item.name
                row.item_created = 1
                row.creation_status = "Created"
                row.creation_timestamp = now_datetime()
                row.remarks = "Created on retry"
                row.db_update()
                
                # Create price list entries
                doc.create_price_list_entries(item.name, row)
                
                # Create stock entry if needed
                if flt(row.opening_stock) > 0:
                    doc.create_stock_entry(item.name, row)
                    row.stock_entry_created = 1
                    row.db_set("stock_entry_created", 1)
                
                success_count += 1
        except Exception as e:
            row.remarks = f"Retry failed: {str(e)}"
            row.db_update()
    
    # Update counts
    doc.items_created = len([r for r in doc.class_details if r.creation_status == "Created"])
    
    if doc.items_created == len(doc.class_details):
        doc.status = "Completed"
    else:
        doc.status = "Partially Created"
    
    doc.db_update()
    frappe.db.commit()
    
    return {"success": success_count, "total_failed": len(failed_rows)}
