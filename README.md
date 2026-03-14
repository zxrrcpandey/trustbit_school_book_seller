# Trustbit School Book Seller

A custom ERPNext application for school book sellers to manage bulk book item creation with class-wise pricing, ISBN tracking, and automated stock management.

**Production:** kgs.trustbit.cloud
**License:** MIT
**Compatibility:** ERPNext v14 / v15
**Python:** >= 3.10

---

## Table of Contents

- [Features](#features)
  - [Book Item Creation (1-14)](#1-bulk-book-item-creation)
  - [Product Bundle (15-16)](#15-get-items-from-product-bundle)
  - [Multi Print Master (17-20)](#17-multi-print-master-auto-print-on-sales-invoice)
  - [Supplier-Wise PO (21)](#21-supplier-wise-purchase-orders-from-sales-order)
  - [Workspace (22)](#22-workspace)
  - [Privilege Card (23-25)](#23-privilege-card-system)
  - [PO Follow Up (26-28)](#26-po-follow-up-tracking)
- [DocTypes](#doctypes)
- [Reports](#reports)
- [Custom Fields on Item](#custom-fields-on-item)
- [Pre-loaded Master Data](#pre-loaded-master-data)
- [Installation](#installation)
- [Usage Guide](#usage-guide)
- [CSV Import / Export](#csv-import--export)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Bugs Fixed](#bugs-fixed)
- [Changelog](#changelog)
- [License](#license)

---

## Features

### 1. Bulk Book Item Creation
Create multiple ERPNext Items (one per class) from a single **Book Item Creator** form. Fill in publication, subject, book name once — then add rows for each class with individual selling rates, valuation rates, ISBN/barcodes, and opening stock quantities.

- **Auto Item Naming:** Items are named as `{Publication} {Book Name} {Class}` (e.g., "NCERT Mathematics Class 10")
- **Background Processing:** Item creation runs as a background job via `frappe.enqueue()` to prevent HTTP timeouts on large batches
- **Per-Row Error Handling:** If one class row fails, the rest continue. Failed rows can be retried later

### 2. Automated Price List Entries
On item creation, the app automatically creates:
- **Selling Price** entry in the selected Selling Price List (using the row's Selling Rate)
- **Buying Price** entry in the selected Buying Price List (using the row's Valuation Rate)

### 3. Automated Stock Entries
When Opening Stock > 0, a **Material Receipt** Stock Entry is automatically created and submitted for each item, depositing stock into the selected Default Warehouse at the row's Valuation Rate.

### 4. ISBN / Barcode Tracking
- Each class row can have a unique **ISBN/Barcode**
- Duplicate ISBNs are validated at three levels:
  - Within the same document (no duplicate rows)
  - Against existing Items (`custom_isbn_barcode` field)
  - Against other submitted Book Item Creators
- ISBNs are also added to the Item's **Barcodes** child table for scanning
- Real-time duplicate check as you type (via whitelisted API)
- DB-level unique constraint on `custom_isbn_barcode` as final safety net

### 5. Quick Add Classes
Quickly populate class rows using predefined groups:

| Button | Classes Added |
|--------|-------------|
| **All Classes** | Nursery, LKG, UKG, Class 1-12 (15 total) |
| **Pre-Primary** | Nursery, LKG, UKG |
| **Primary (1-5)** | Class 1, Class 2, Class 3, Class 4, Class 5 |
| **Middle (6-8)** | Class 6, Class 7, Class 8 |
| **High (9-10)** | Class 9, Class 10 |
| **Hr. Sec. (11-12)** | Class 11, Class 12 |

- Skips classes already present in the form
- Shows accurate count of actually added classes (not total available)

### 6. Real-Time Progress Dialog
When submitting a Book Item Creator, a rich progress dialog shows:
- Animated spinner during creation
- Live progress bar (green = created, red = failed, grey = pending)
- Running counters for Created / Failed / Pending
- Percentage completion
- Color-coded final status (success/partial/failure icons)
- Powered by `frappe.publish_realtime` for live updates from the background job

### 7. CSV Import
Import class details from a CSV file:
- Upload a CSV with columns: Class, Selling Rate, Valuation Rate, ISBN/Barcode, Opening Stock
- Smart column name matching (case-insensitive, partial match)
- Validates each class against Class Master
- Skips duplicate classes already in the form
- Reports all skipped rows with reasons (invalid class, missing data, duplicates)
- Download a pre-formatted CSV template

### 8. CSV Export
Export all successfully created items to a CSV file:
- Includes: Item Code, Item Name, Class, Publication, Subject, Author, ISBN, Rates, Stock, Warehouse, Creation Date
- Files are stored as **private** attachments (not publicly accessible)

### 9. Duplicate Entry
Clone any submitted or cancelled Book Item Creator:
- Copies all fields: Publication, Subject, Book Name, Author, Edition, Rates, Price Lists, Item Group, Warehouse, UOM
- Copies class rows with rates and opening stock
- **Clears all ISBNs** (since they must be unique — user must enter new ones)
- Resets status to Draft

### 10. Retry Failed Items
If some items fail during creation (e.g., network error, validation issue):
- A **"Retry Failed Items"** button appears on Partially Created / Failed documents
- Only retries rows with `creation_status = "Failed"`
- Price list and stock entry errors are handled gracefully (logged, don't block the retry)
- Updates overall document status after retry

### 11. View Created Items
One-click button to view all Items created by a Book Item Creator — opens the Item List filtered by `custom_book_item_creator`.

### 12. Discount Management
- **Sales Discount %** and **Purchase Discount %** fields on the Book Item Creator
- Values are copied to each created Item's custom fields
- Useful for publisher-specific discount tracking

### 13. Submittable Workflow
Book Item Creator follows Frappe's submittable document pattern:
- **Draft** → Fill details, add classes, validate
- **Submitted** → Items created in background
- **Cancelled** → Status set to Cancelled (created items remain for audit)
- **Amended** → Create a corrected version linked to the original

Status values: `Draft` | `In Progress` | `Completed` | `Partially Created` | `Failed` | `Cancelled`

### 14. Smart Validations
- Class details table must have at least one row
- Selling Rate and Valuation Rate must be > 0
- No duplicate classes within the same document
- No duplicate ISBNs within the same document
- No duplicate ISBNs across existing Items and submitted Book Item Creators
- All validations run server-side (Python) and client-side (JavaScript) for immediate feedback

### 15. Get Items from Product Bundle
Fetch items from an ERPNext **Product Bundle** into transaction documents with a single click. Available on:
- Material Request
- Sales Invoice
- Sales Order
- Purchase Order
- Purchase Invoice

**How it works:**
1. Open a Draft document → click **Get Items → Product Bundle**
2. Select a Product Bundle — the dialog shows the **parent item name/description** and a **preview table** of all component items with quantities and UOMs
3. Enter **Number of Sets** — each item's quantity is multiplied by this number
4. Choose **Append** (add to existing items) or **Replace** (clear existing items first)
5. Click **Get Items** — items are added to the table and rates auto-populate from the document's Price List

### 16. Advanced Search on Product Bundle Form
The Product Bundle form includes **Ctrl+Q Quick Add** and **Ctrl+B Barcode Scan** for rapidly adding component items — the same advanced search experience as `trustbit_advance_search`.

**Quick Add (Ctrl+Q):**
- Fuzzy search across item code, name, group, description, and barcode
- Multi-word AND matching (e.g. "NCERT math" finds items matching both words)
- Results table: Item Code | Item Name | Group | UOM | Select button
- Barcodes shown below item code when available
- Select an item → enter qty → **Add to Bundle** → form resets for next item

**Scan Barcode (Ctrl+B):**
- Scan or type barcode → item auto-detected with details shown
- Enter qty → **Add to Bundle** → auto-resets for continuous scanning

**Smart duplicate handling:** If an item already exists in the bundle, qty is added to the existing row.

### 17. Multi Print Master (Auto-Print on Sales Invoice)
Automatically print multiple copies of a Sales Invoice to different printers using **QZ Tray**. Works from **any submission source**: standard form, POS Awesome, API, or background jobs.

**How it works (Realtime Architecture):**
```
Any source (Standard Form / POS Awesome / API)
    → Server: on_submit hook publishes realtime event
    → Client: frappe.realtime listener receives event
    → Client: QZ Tray prints silently (no browser dialog)
```

**Global Settings (Multi Print Setting):**

| Setting | Default | Purpose |
|---------|---------|---------|
| Enable Auto Print | Yes | Master on/off switch |
| Trigger Print On | Submitted Only | When to print: `Submitted Only` / `Draft (Save)` / `Both (Save + Submit)` |
| Show Token After Print | Yes | Display token dialog after printing |
| Token Digits | 3 | Number of digits from end of invoice name |
| Use Default Config as Fallback | Yes | If disabled, users without a User Print Config won't get auto-print |

**Default Print Formats table:** Configure fallback printer mapping for users without personal config:

| Print Format | Printer Name | Copies | Enabled |
|---|---|---|---|
| 80MM Token | Thermal Printer | 1 | Yes |
| A4 School Invoice | HP LaserJet | 1 | Yes |

**Trigger Timing:**

| Setting | On first Save (draft) | On Submit |
|---------|----------------------|-----------|
| Submitted Only | — | Prints |
| Draft (Save) | Prints | — |
| Both (Save + Submit) | Prints | Prints |

Draft trigger uses `after_insert` (fires once on creation only) — editing and re-saving a draft does not cause repeated prints.

**Manual Reprint:** On any submitted Sales Invoice, click **Print → Multi Print**

**POS Awesome Compatibility:** Auto-print works seamlessly with POS Awesome. To avoid double-printing, clear the **Print Format** field in POS Profile settings (so only QZ Tray handles printing, not the browser print dialog).

### 18. Per-User Printer Configuration
Each user can have their own printer mapping that **overrides the global default**.

**Priority:** User Print Config > Multi Print Setting (global default)

**Setup:**
1. Search **"User Print Config"** → New
2. Select user (defaults to current user)
3. Click **"Detect Printers"** → QZ Tray scans all connected printers
4. Select printer + print format + copies for each row
5. Save

**Printer Detection:**
- "Detect Printers" button connects to QZ Tray and lists all available printers
- Click "Add" next to any printer → select print format and copies
- Printer status shows green/red indicators for each configured printer

**Fallback Behavior:**
- If `Use Default Config as Fallback` is **enabled** in Multi Print Setting: users without a User Print Config use the global default printers
- If **disabled**: only users with their own config get auto-print

### 19. 80MM Token Print Format
A dedicated thermal receipt format (72mm width) for token printing:
- Company name, full invoice number
- Token number in **56px bold** (last 3 digits of invoice name)
- Customer name, date/time, items count, total amount
- Designed for 80mm thermal printers (TSC, TVS, etc.)

### 20. Printer Setup Recommendations
The Multi Print Setting page includes a built-in setup guide for the **Brother HL-B2180DW** network printer:
- Specs: 34 ppm, 30K duty cycle, 2,500 recommended monthly volume
- **Mandatory:** Use Ethernet (not Wi-Fi), set Static IP, install via TCP/IP port
- **High volume warning:** 900 prints/day = 18K/month = 7x recommended volume
- Paper tray (150 sheets) needs 6 refills per 900 prints
- QZ Tray setup steps for every PC
- Typical per-user config example (80MM Token → local thermal, A4 Invoice → Brother LAN)

### 21. Supplier-Wise Purchase Orders from Sales Order
On submitted Sales Orders, a **Create > PO (Supplier Wise)** button groups SO items by their default supplier and creates separate Purchase Orders for each supplier in one click.

**How it works:**
1. Open a submitted Sales Order → click **Create > PO (Supplier Wise)**
2. A dialog shows all SO items with: Item Code, Item Name, Qty, UOM, Supplier
3. Items without a default supplier are grouped under "No Supplier" — you can assign suppliers in the dialog
4. Select items → click **Create Purchase Orders** → confirmation shows how many POs will be created per supplier
5. POs are created and linked back to the SO. School Name is copied to each PO.

- Only shows items not yet ordered (pending qty > 0)
- If all items already have POs, prompts to re-create for all items
- Copies school name from SO to each created PO

### 22. Workspace
A dedicated **"School Book Seller"** workspace with:
- Quick shortcuts to Book Item Creator, Publication, Items, Privilege Cards, PO Follow Ups
- Links to all reports (Book Items, Book Creation Summary, Privilege Card Usage, PO Follow Up Report)
- Organized navigation for all app features

### 23. Privilege Card System
Issue discount cards to customers (students, parents, teachers) that automatically apply discounts on Sales Orders and Sales Invoices.

- **Privilege Card Type** — master for card categories (Student, Parent, Teacher) with configurable discount %
- **Privilege Card** — issued to a customer, links to card type, has expiry date and active/expired status
- **Auto-discount on SO/SI** — when a Privilege Card is selected, its discount % is applied and shown as a read-only field
- **Usage logging** — every SO/SI submission with a privilege card creates a usage log entry
- **Daily expiry check** — scheduler job automatically expires cards past their expiry date

### 24. Privilege Card Usage Report
- **Type:** Script Report
- **Based on:** Privilege Card
- **Shows:** Card usage across Sales Orders and Sales Invoices with dates, amounts, and discounts applied

### 25. Privilege Card Custom Fields
Added to Sales Order and Sales Invoice:
- `custom_privilege_card` — Link to Privilege Card
- `custom_privilege_card_discount` — Card Discount % (read-only, auto-populated)

### 26. PO Follow Up Tracking
A structured follow-up system for Purchase Managers to track supplier delivery commitments on Purchase Orders. Log each follow-up conversation with per-item quantity tracking, delivery dates, transport details, and contact information.

**Creating a Follow Up:**
1. Open a submitted Purchase Order → click **Create > Follow Up**
2. A new PO Follow Up form opens pre-filled with all PO items (item code, name, ordered qty)
3. Fill in: follow-up date, next follow-up date, overall status, contacted person, transport name
4. For each item: enter expected qty, expected delivery date, and per-item status
5. Save — the Purchase Order's summary fields are automatically updated

**PO Summary Fields (auto-updated):**
- Last Follow Up Date, Last Follow Up Status
- Next Follow Up Date, Total Follow Ups count
- Displayed in a collapsible "Follow Up Summary" section on the PO form

**Dashboard Indicators on PO:**
- Color-coded status indicator (green=Delivered, blue=Confirmed/Dispatched, orange=Pending, red=Delayed)
- Next follow-up date indicator (red if overdue, blue if upcoming)

**Previously Confirmed Qty:**
Each follow-up automatically computes the previously confirmed quantity per item from all prior follow-ups on the same PO, giving visibility into what was already committed.

### 27. PO Follow Up Report
- **Type:** Script Report
- **Based on:** PO Follow Up
- **Shows:** All follow-ups with Purchase Order, Supplier, dates, status, contacted person, transport, items count, remarks
- **Chart:** Bar chart grouped by status
- **Summary cards:** Total Follow Ups, Pending/Delayed count, Delivered count
- **Filters:** Supplier, Status, From Date, To Date

### 28. Auto-Reminders for Follow Ups
Two daily scheduler jobs keep Purchase Managers informed:

| Job | What it does |
|-----|--------------|
| **Follow Up Reminders** | Finds follow-ups where next follow-up date <= today AND status != Delivered. Sends a Notification Log to all users with Purchase Manager or Purchase User roles |
| **POs Without Follow Ups** | Finds submitted Purchase Orders older than 3 days with zero follow-ups. Alerts Purchase Managers to initiate first contact |

---

## DocTypes

| DocType | Type | Auto Name | Purpose |
|---------|------|-----------|---------|
| **Book Item Creator** | Submittable | `BOOK-ENTRY-.#####` | Main form for bulk book item creation |
| **Book Class Detail** | Child Table | — | Per-class row: class, selling rate, valuation rate, ISBN, opening stock, creation status |
| **Publication** | Master | By `publication_name` | Publisher information with contact details |
| **Subject** | Master | By `subject_name` | School subject with short code and sort order |
| **Class Master** | Master | By `class_name` | School class/grade with short code and sort order |
| **Book Creation Log** | Child Table | — | Reserved for future audit trail functionality |
| **Multi Print Setting** | Single (Settings) | — | Global auto-print config: trigger timing, token display, default fallback |
| **Multi Print Format** | Child Table | — | Print format + printer name + copies (shared by Multi Print Setting & User Print Config) |
| **User Print Config** | Master | By `user` (unique) | Per-user printer mapping — overrides global Multi Print Setting |
| **Privilege Card Type** | Master | By `card_type_name` | Card categories (Student, Parent, Teacher) with discount % |
| **Privilege Card** | Master | Auto | Issued to customer, links card type, expiry date, active/expired status |
| **PO Follow Up** | Master | `PO-FU-.#####` | Per-PO follow-up log: contact, transport, status, remarks |
| **PO Follow Up Item** | Child Table | — | Per-item tracking: ordered qty, expected qty, delivery date, status |

### Permissions

| Role | Book Item Creator | Publication / Subject / Class Master | PO Follow Up |
|------|-------------------|--------------------------------------|--------------|
| **System Manager** | Full access (create, read, write, submit, cancel, amend, delete) | Full access | Full access |
| **Stock Manager** | Full access | Full access | Full access |
| **Stock User** | Full access | Create, read, write, export, print (no delete) | Create, read, write (no delete) |
| **Purchase User** | — | — | Create, read, write (no delete) |

---

## Reports

### Book Creation Summary
- **Type:** Script Report
- **Based on:** Book Item Creator
- **Shows:** All submitted Book Item Creator entries with publication, book name, subject, status, total items, items created, success rate, total stock, stock value, created by, date
- **Chart:** Pie chart by status (Completed / Partially Created / Failed)
- **Summary cards:** Total Entries, Items Created, Completed count, Total Value
- **Filters:** Publication, Subject, Status, From Date, To Date

### Book Items Report
- **Type:** Script Report
- **Based on:** Item
- **Shows:** All book items created by the app with item code, name, publication, subject, class, author, ISBN, selling rate, valuation rate, current stock (aggregated across all warehouses), stock value
- **Chart:** Bar chart grouped by Publication
- **Summary cards:** Total Book Items, Total Stock Qty, Total Stock Value
- **Filters:** Publication, Subject, Class, From Date, To Date

### Privilege Card Usage
- **Type:** Script Report
- **Based on:** Privilege Card
- **Shows:** Card usage across Sales Orders and Sales Invoices

### PO Follow Up Report
- **Type:** Script Report
- **Based on:** PO Follow Up
- **Shows:** All follow-ups with PO link, supplier, follow-up date, next follow-up, status, contacted person, transport, items count, remarks
- **Chart:** Bar chart grouped by status (Pending, Confirmed, Dispatched, Delivered, Delayed)
- **Summary cards:** Total Follow Ups, Pending/Delayed, Delivered
- **Filters:** Supplier, Status, From Date, To Date

---

## Custom Fields on Item

The app adds 17 custom fields to the standard ERPNext **Item** doctype:

| Field | Type | Section | Options |
|-------|------|---------|---------|
| `custom_book_details_section` | Section Break | Book Details | Collapsible |
| `custom_publication` | Link | Book Details | Publication |
| `custom_subject` | Data | Book Details | — |
| `custom_class` | Data | Book Details | — |
| `custom_class_grades` | Table MultiSelect | Book Details | Item Class Grade |
| `custom_column_break_book` | Column Break | Book Details | — |
| `custom_author` | Data | Book Details | — |
| `custom_edition` | Data | Book Details | — |
| `custom_edition_year` | Data | Book Details | — |
| `custom_publication_year` | Data | Book Details | — |
| `custom_isbn` | Data (unique) | Book Details | — |
| `custom_isbn_barcode` | Data (unique) | Book Details | DB unique constraint |
| `custom_publisher` | Link | Book Details | Supplier |
| `custom_discount_section` | Section Break | Discount | Collapsible |
| `custom_sales_discount_percent` | Percent | Discount | — |
| `custom_purchase_discount_percent` | Percent | Discount | — |
| `custom_book_item_creator` | Link (read-only) | Discount | Book Item Creator |

### Custom Fields on Other DocTypes

| DocType | Field | Type | Options |
|---------|-------|------|---------|
| Sales Order | `custom_school_name` | Link | School |
| Sales Order | `custom_privilege_card` | Link | Privilege Card |
| Sales Order | `custom_privilege_card_discount` | Percent (read-only) | — |
| Purchase Order | `custom_school_name` | Link | School |
| Purchase Order | `custom_remark` | Small Text | — |
| Purchase Order | `custom_transport_name` | Data | — |
| Purchase Order | `custom_followup_section` | Section Break | Follow Up Summary (collapsible) |
| Purchase Order | `custom_last_followup_date` | Date (read-only) | — |
| Purchase Order | `custom_last_followup_status` | Data (read-only) | — |
| Purchase Order | `custom_column_break_followup` | Column Break | — |
| Purchase Order | `custom_next_followup_date` | Date (read-only) | — |
| Purchase Order | `custom_total_followups` | Int (read-only) | — |
| Sales Invoice | `custom_school_name` | Link | School |
| Sales Invoice | `custom_privilege_card` | Link | Privilege Card |
| Sales Invoice | `custom_privilege_card_discount` | Percent (read-only) | — |

**School Name Propagation:**
- Sales Order → Set School Name (linked to School master)
- "PO (Supplier Wise)" button → School Name copied to Purchase Order
- "Make Sales Invoice" → School Name copied to Sales Invoice (via `before_save` hook)

> **Dependency:** School Name fields require the `trustbit_school_pro` app (provides the `School` DocType). If not installed, these fields are created as Data type instead of Link.

**PO Follow Up Summary:** The 6 fields on Purchase Order (section + column break + 4 data fields) are auto-updated whenever a PO Follow Up is saved or deleted. They provide a quick-glance view of follow-up activity without opening the follow-up records.

---

## Pre-loaded Master Data

### Classes (15)

| Class | Short Code | Sort Order |
|-------|-----------|------------|
| Nursery | NUR | 1 |
| LKG | LKG | 2 |
| UKG | UKG | 3 |
| Class 1 | C1 | 4 |
| Class 2 | C2 | 5 |
| Class 3 | C3 | 6 |
| Class 4 | C4 | 7 |
| Class 5 | C5 | 8 |
| Class 6 | C6 | 9 |
| Class 7 | C7 | 10 |
| Class 8 | C8 | 11 |
| Class 9 | C9 | 12 |
| Class 10 | C10 | 13 |
| Class 11 | C11 | 14 |
| Class 12 | C12 | 15 |

### Subjects (20)

| Subject | Short Code | Subject | Short Code |
|---------|-----------|---------|-----------|
| Mathematics | MATH | Economics | ECO |
| English | ENG | Accountancy | ACC |
| Hindi | HIN | Business Studies | BST |
| Science | SCI | Geography | GEO |
| Social Science | SST | History | HIST |
| Physics | PHY | Political Science | POL |
| Chemistry | CHEM | Sanskrit | SANS |
| Biology | BIO | Physical Education | PE |
| Computer Science | CS | Art & Craft | ART |
| Music | MUS | General Knowledge | GK |

---

## Installation

### Prerequisites
- ERPNext v14 or v15 installed and running
- Frappe Bench configured
- Git installed
- sudo / root access

### Steps

```bash
# 1. Navigate to bench directory
cd ~/frappe-bench

# 2. Get the app
bench get-app https://github.com/zxrrcpandey/trustbit_school_book_seller.git

# 3. Install on your site
bench --site [your-site] install-app trustbit_school_book_seller

# 4. Run migrations
bench --site [your-site] migrate

# 5. Build assets
bench build --app trustbit_school_book_seller

# 6. Restart services
sudo supervisorctl restart all
```

### Verify Installation

1. Search **"Publication"** — should open the doctype
2. Search **"Subject"** — should show 20 pre-loaded subjects
3. Search **"Class Master"** — should show 15 pre-loaded classes
4. Search **"Book Item Creator"** — should open with Quick Add buttons
5. Search **"School Book Seller"** — workspace should appear in sidebar

---

## Usage Guide

### Creating Books (Step by Step)

1. **Create a Publication** (if new): Go to Publication → New → Enter name, code, contact → Save
2. **Open Book Item Creator**: Search "Book Item Creator" → New
3. **Fill Header Details**:
   - Publication (required)
   - Subject (required)
   - Book Name (required)
   - Author, Edition, Publication Year (optional)
4. **Set Pricing & Config**:
   - Selling Price List, Buying Price List (required)
   - Sales/Purchase Discount % (optional)
   - Item Group, Default Warehouse, UOM (required)
   - HSN/SAC Code (optional, for GST)
5. **Add Class Rows**: Use **Quick Add Classes** buttons or add manually
6. **Fill Per-Class Details**:
   - Selling Rate (required, > 0)
   - Valuation Rate (required, > 0)
   - ISBN/Barcode (optional but recommended)
   - Opening Stock (optional, default 0)
7. **Submit**: Click **"Submit & Create Items"** → Watch the progress dialog
8. **Review**: Check status, retry failures if any, export to CSV

---

## CSV Import / Export

### CSV Template Format

```csv
Class,Selling Rate,Valuation Rate,ISBN/Barcode,Opening Stock
Class 1,150,100,9781234567001,50
Class 2,160,110,9781234567002,45
Class 3,170,120,9781234567003,40
```

**Column matching is flexible:** The parser matches columns by keywords (case-insensitive):
- "class" → Class
- "selling" or "rate" → Selling Rate
- "valuation" → Valuation Rate
- "isbn" or "barcode" → ISBN/Barcode
- "stock" or "opening" → Opening Stock

### Import Steps
1. Click **Import/Export → Import from CSV** (on Draft documents)
2. Download the template if needed
3. Upload your CSV file
4. Review the import summary (added, skipped with reasons)

### Export Steps
1. Click **Import/Export → Export to Excel** (on Submitted documents with created items)
2. File downloads automatically (stored as private attachment)

---

## API Reference

All whitelisted API methods are at:
`trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator`

| Method | Arguments | Description |
|--------|-----------|-------------|
| `get_classes_for_quick_add` | `class_type` (all/pre_primary/primary/middle/high/hr_sec) | Returns filtered Class Master entries |
| `check_isbn_exists` | `isbn_barcode`, `exclude_doc` (optional) | Checks ISBN against Items and submitted Book Item Creators |
| `retry_failed_items` | `docname` | Retries failed item creation rows |
| `export_items_to_excel` | `docname` | Exports created items to CSV (private file) |
| `parse_csv_file` | `file_url` | Parses uploaded CSV, validates classes, returns data + skipped info |
| `duplicate_book_item_creator` | `docname` | Clones a Book Item Creator (clears ISBNs) |

**Sales Order API** (`trustbit_school_book_seller.api`):

| Method | Arguments | Description |
|--------|-----------|-------------|
| `get_so_items_with_suppliers` | `sales_order`, `include_ordered` (0/1) | Returns SO items with default suppliers and pending qty for supplier-wise PO creation |
| `create_po_supplier_wise` | `sales_order`, `items` (list) | Groups selected items by supplier and creates separate Purchase Orders. Copies school name from SO |

**Product Bundle & Search API** (`trustbit_school_book_seller.api`):

| Method | Arguments | Description |
|--------|-----------|-------------|
| `get_product_bundle_items` | `product_bundle`, `qty_sets` (default 1) | Returns list of items from a Product Bundle with quantities multiplied by `qty_sets` |
| `search_product_bundles` | `search_text`, `limit` (default 20) | Fuzzy search Product Bundles by name, item name, description, group |
| `search_items` | `search_text`, `limit` (default 50) | Fuzzy search Items by code, name, group, description, barcode (AND logic) |

**Multi Print API** (`trustbit_school_book_seller.api`):

| Method | Arguments | Description |
|--------|-----------|-------------|
| `get_multi_print_settings` | — | Returns user-aware print config (user config > global fallback). Includes: enabled, trigger_on, show_token, token_digits, source, print_formats |

**PO Follow Up API** (`trustbit_school_book_seller.followup_api`):

| Method | Arguments | Description |
|--------|-----------|-------------|
| `get_po_items` | `purchase_order` | Returns PO items with ordered qty, received qty, pending qty for pre-filling follow-up |
| `get_followup_summary` | `purchase_order` | Returns all follow-ups for a PO with status and dates |
| `create_followup_from_po` | `purchase_order` | Creates a pre-filled PO Follow Up with all PO items, returns name for routing |

**Privilege Card API** (`trustbit_school_book_seller.api` + `trustbit_school_book_seller.privilege_card`):

| Function | Trigger | Description |
|----------|---------|-------------|
| `validate_privilege_card` | Whitelisted API (api.py) | Client-callable: validates card and returns card details (name, type, discount %, status) |
| `validate_privilege_card_on_doc` | SO/SI before_validate | Server-side: validates card is active and not expired, populates discount % |
| `log_privilege_card_usage` | SO/SI on_submit | Creates usage log entry for the privilege card |
| `expire_cards_daily` | Daily scheduler | Expires cards past their expiry date |

**Server-side Hooks** (not whitelisted — called via doc_events):

| Function | Trigger | Description |
|----------|---------|-------------|
| `copy_school_name_to_invoice` | SI before_save | Copies School Name from linked Sales Order to Sales Invoice |
| `on_sales_invoice_save` | SI after_insert | Publishes realtime event for draft printing (if trigger_on includes draft) |
| `on_sales_invoice_submit` | SI on_submit | Publishes realtime event for submit printing (if trigger_on includes submit) |

**Scheduler Jobs** (daily):

| Function | Description |
|----------|-------------|
| `expire_cards_daily` | Expires privilege cards past their expiry date |
| `send_followup_reminders` | Notifies Purchase Manager/User roles of overdue follow-ups (next_followup_date <= today, status != Delivered) |
| `check_pos_without_followups` | Alerts Purchase Managers about submitted POs older than 3 days with zero follow-ups |

---

## Deployment

### Automated Deployment (GitHub Actions)

The app includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that deploys to production on every push to `main`:

1. **Full Backup** — `bench backup --with-files` (database + uploaded files)
2. **Backup Verification** — Checks backup file exists and size is reasonable; **aborts deploy if backup fails**
3. **Backup Retention** — Keeps last 10 backups, cleans up older ones
4. **Code Update** — `git fetch` + `git reset --hard` to latest `main`
5. **Permission Fix** — Sets correct ownership for `frappe_user`
6. **Migrate** — `bench migrate` to apply schema changes
7. **Build Assets** — `bench build --app` to compile JS/CSS
8. **Clear Cache** — `bench clear-cache`
9. **Restart** — `supervisorctl restart all`

### Required GitHub Secrets

| Secret | Value |
|--------|-------|
| `SERVER_HOST` | Server IP address |
| `SERVER_USER` | SSH username (e.g., `root`) |
| `SERVER_SSH_KEY` | Private SSH key (ED25519 recommended) |

### Manual Deployment

```bash
ssh user@your-server
cd /home/frappe_user/frappe-bench

# Always backup first!
su - frappe_user -c "bench --site kgs.trustbit.cloud backup --with-files"

# Update code
cd apps/trustbit_school_book_seller
git pull origin main

# Apply changes
su - frappe_user -c "cd /home/frappe_user/frappe-bench && bench --site kgs.trustbit.cloud migrate"
su - frappe_user -c "cd /home/frappe_user/frappe-bench && bench build --app trustbit_school_book_seller"
su - frappe_user -c "cd /home/frappe_user/frappe-bench && bench --site kgs.trustbit.cloud clear-cache"
sudo supervisorctl restart all
```

---

## Architecture

| Aspect | Detail |
|--------|--------|
| **Module** | Trustbit School Book |
| **Naming Series** | `BOOK-ENTRY-.#####` |
| **Item Naming** | `{Publication} {Book Name} {Class}` |
| **Background Jobs** | `frappe.enqueue()` on `default` queue, 600s timeout |
| **Realtime Events** | `book_item_creation_progress`, `multi_print_invoice` |
| **QZ Tray** | Required for multi-print (loaded globally by `trustbit_barcode` app) |
| **Barcode Type** | Empty string (accepts any format) |
| **Fixtures** | Subject, Class Master, Custom Field (32 fields), Print Format (KGS Purchase Order, 80MM Token) |
| **Build System** | Flit (`flit_core >= 3.4, < 4`) |

### File Structure

```
trustbit_school_book_seller/
├── .github/workflows/deploy.yml        # CI/CD deployment pipeline
├── .gitignore
├── LICENSE
├── README.md                           # This file
├── CHANGELOG.md                        # Version history
├── pyproject.toml                      # Python packaging (Flit)
├── setup.py                            # Legacy setuptools config
├── requirements.txt
└── trustbit_school_book_seller/
    ├── __init__.py                     # App version
    ├── hooks.py                        # App configuration
    ├── install.py                      # Post-install setup
    ├── api.py                          # Product Bundle, search, multi-print & hook APIs
    ├── privilege_card.py               # Privilege card validation, usage logging, expiry
    ├── followup_api.py                 # PO Follow Up APIs + scheduler functions
    ├── modules.txt
    ├── patches.txt
    ├── fixtures/
    │   ├── class_master.json           # 15 default classes
    │   ├── subject.json                # 20 default subjects
    │   ├── custom_field.json           # 32 custom field definitions (Item, SO, PO, SI)
    │   └── print_format.json           # Print formats (KGS Purchase Order, 80MM Token)
    ├── public/js/
    │   ├── book_item_creator.js        # Client-side logic (649 lines)
    │   ├── product_bundle.js           # Get Items from Product Bundle (MR, SI, SO, PO, PI)
    │   ├── product_bundle_form.js      # Advanced Search on Product Bundle form (Ctrl+Q, Ctrl+B)
    │   ├── sales_invoice_print.js      # Multi Print realtime listener + manual reprint (global JS)
    │   ├── sales_order.js              # Sales Order custom buttons
    │   ├── user_print_config.js        # Printer detection & status for User Print Config
    │   ├── privilege_card_so_si.js     # Privilege card discount handling on SO/SI
    │   └── purchase_order_followup.js  # PO Follow Up buttons + dashboard indicators
    └── trustbit_school_book/
        ├── doctype/
        │   ├── book_item_creator/      # Main transaction DocType
        │   ├── book_class_detail/      # Child table for class rows
        │   ├── book_creation_log/      # Child table (reserved)
        │   ├── multi_print_setting/    # Global auto-print settings (Single DocType)
        │   ├── multi_print_format/     # Print format + printer config (Child Table)
        │   ├── user_print_config/      # Per-user printer mapping (overrides global)
        │   ├── publication/            # Publisher master
        │   ├── subject/                # Subject master
        │   ├── class_master/           # Class/Grade master
        │   ├── privilege_card_type/    # Card categories with discount %
        │   ├── privilege_card/         # Issued cards with expiry
        │   ├── po_follow_up/           # PO Follow Up parent DocType
        │   └── po_follow_up_item/      # PO Follow Up child table
        ├── report/
        │   ├── book_creation_summary/  # Summary report
        │   ├── book_items_report/      # Items report
        │   ├── privilege_card_usage/   # Card usage report
        │   └── po_follow_up_report/    # Follow-up report with chart
        └── workspace/
            └── trustbit_school_book.json  # Workspace config
```

---

## Troubleshooting

### Custom fields not appearing on Item
```bash
bench --site [your-site] console
```
```python
from trustbit_school_book_seller.install import after_install
after_install()
```

### Fields showing in wrong order or hidden
This is usually caused by a `field_order` Property Setter created by Customize Form:
```bash
# Check for dangerous Property Setter
bench --site [your-site] execute frappe.get_all --args '["Property Setter", {"filters": {"doc_type": "Item", "property": "field_order"}, "fields": ["name"]}]'

# Delete it if found
bench --site [your-site] execute frappe.delete_doc --args '["Property Setter", "Item-main-field_order"]'

# Flush cache
redis-cli -p 11000 FLUSHALL && redis-cli -p 13000 FLUSHALL
sudo supervisorctl restart all
```

**Important:** NEVER use the Customize Form UI to reorder fields — it creates a permanent field position lock that overrides all `insert_after` settings.

### Brand field disappeared
Brand may be trapped inside the `book_sample_section` (which is hidden unless "Is Sample Book" is checked). Fix:
```bash
bench --site [your-site] execute frappe.db.set_value --args '["Custom Field", "Item-book_sample_section", "insert_after", "brand"]'
redis-cli -p 11000 FLUSHALL && redis-cli -p 13000 FLUSHALL
sudo supervisorctl restart all
```

### JavaScript not loading
```bash
bench build --app trustbit_school_book_seller --force
sudo supervisorctl restart all
# Clear browser cache: Ctrl+Shift+R (or Cmd+Shift+R on Mac)
```

### QZ Tray "Not Found" error
QZ Tray must be installed and running on the user's PC. It is loaded globally by the `trustbit_barcode` app.
1. Check QZ Tray is running (look for icon in system tray)
2. Refresh browser: `Ctrl+Shift+R`
3. If still failing, reinstall from [qz.io](https://qz.io)

### Multi Print not triggering from POS Awesome
The realtime approach requires **socketio** to be running:
```bash
sudo supervisorctl status  # Check frappe-bench-node-socketio is RUNNING
```
Also ensure POS Awesome's built-in print is disabled (clear Print Format in POS Profile) to avoid double printing.

### Printer not found in QZ Tray
- Printer name must match **exactly** what QZ Tray reports
- Go to **User Print Config** → click **"Detect Printers"** to see exact names
- For network printers: use Ethernet (not Wi-Fi), set static IP, install via TCP/IP port

### App not found in apps.txt
**NEVER manually edit apps.txt.** Use bench commands:
```bash
bench --site [your-site] install-app trustbit_school_book_seller
```

### Re-export fixtures after field changes
After fixing any custom field settings in the DB, re-export to prevent regression on next migrate:
```bash
bench --site [your-site] export-fixtures --app trustbit_school_book_seller
```

### Uninstallation
```bash
bench --site [your-site] uninstall-app trustbit_school_book_seller
bench remove-app trustbit_school_book_seller
```

---

## Bugs Fixed

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| **80MM Token `posting_time` error** | ERPNext stores `posting_time` as `datetime.timedelta`, not a string. Slicing `doc.posting_time[:5]` fails on timedelta objects. | Changed to `(doc.posting_time \| string)[:5]` in the Jinja template to convert timedelta to string before slicing. |
| **80MM Token `regex_replace` filter not found** | Frappe's Jinja environment does not include the `regex_replace` filter (unlike Ansible/Django). Template used `inv_digits \| regex_replace('[^0-9]', '')` which raised `ValidationError`. | Replaced with `doc.name.split('-')[-1]` and `last_part[-3:]` — pure Jinja string operations that work in Frappe. |
| **Multi Print not triggering from POS Awesome** | `frappe.ui.form.on("Sales Invoice", { on_submit: ... })` is a client-side form event that only fires when the standard Frappe form is open. POS Awesome uses its own Vue.js UI and never opens the standard form. | Replaced client-side `on_submit` with server-side `on_submit` doc_event hook that publishes a `frappe.publish_realtime` event. Client-side JS listens via `frappe.realtime.on()` which works on any page, including POS. |
| **Double printing with POS Awesome** | POS Awesome has its own print mechanism (`window.open(printview_url)` + `window.print()`) that triggers a browser print dialog. Combined with QZ Tray auto-print, this causes duplicate prints. | Solution: clear the Print Format field in POS Profile settings to disable POS Awesome's built-in print. Only QZ Tray handles printing. |

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

---

## License

MIT License - see [LICENSE](LICENSE)

## Author

**Trustbit** - info@trustbit.in
