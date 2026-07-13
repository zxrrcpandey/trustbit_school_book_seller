# Changelog

All notable changes to the **Trustbit School Book Seller** app are documented here.

> **Note:** In-code version metadata (`trustbit_school_book_seller/__init__.py`, `setup.py`) still reads `1.0.0` and has never been bumped. The version numbers below are release milestones tracked in this changelog only — syncing the code metadata is a known open issue.

---

## [1.6.1] - 2026-07-13

### Fixed
- **Return Scanner non-barcode lookups no longer crash:** removed the stray `item_code = scan_result["item_code"]` reassignment after the fallback chain (`return_scanner_api.py`). Lookups by item code, exact item name, and fuzzy item name now work as documented instead of raising `KeyError` (bug was open since the feature shipped in March; tracked in [1.4.0] Known Issues)

---

## [1.6.0] - 2026-07-13

### New Features
- **Purchase Order PDF filenames:** PDF downloads of Purchase Orders are now named `<PO ID> - <Supplier Name>.pdf` instead of the generic default. Implemented by overriding `frappe.utils.print_format.download_pdf` via `override_whitelisted_methods` (`trustbit_school_book_seller.api.download_pdf`). Only Purchase Order filenames are rewritten — all other DocTypes keep Frappe's default naming. Supplier name is sanitized to printable ASCII because Frappe's PDF response helper mangles non-ASCII in `Content-Disposition`
- **PO system-print-dialog filenames:** the browser print dialog (Ctrl+P / Print → Save as PDF) names files from the page title, not the download header, so page titles are now set to `<PO ID> - <Supplier Name>` on both the desk print page (`po_print_title.js` via `app_include_js`) and `/printview` (via `update_website_context` hook)

### Performance
- **Wall Display polling reduced from 30s to 8 minutes:** the 30-second refresh fired 6 aggregate API calls per tick, 24/7 — roughly 8,700 requests/day (~37% of all server traffic) on the 1-core production server. The clock now updates client-side between refreshes so the display stays live

### Known Limitations (accepted)
- Bulk PDF download from the Purchase Order list view still produces a single merged `Purchase-Order.pdf`
- Print Format Builder (Beta) formats render via a different path (weasyprint) and bypass the filename override

### Notes
- The production DB backup cron was rescheduled in early July (09:00 / 22:00 IST, niced, DB-only) to keep heavy jobs out of shop hours — this is a server-side change, not part of this app

---

## [1.5.0] - 2026-04-10

### New Features
- **Privilege Card system:** discount cards for students, parents, and teachers. New DocTypes: Privilege Card Type (master), Privilege Card (barcode, usage tracking, auto-expiry), Privilege Card Usage Log (child table). Custom fields on Sales Order/Sales Invoice for card selection and discount display. "Apply Privilege Card" button with barcode scan support, server-side card validation and usage logging on submit, daily scheduler to auto-expire cards, usage report with chart, and a printable card format. Follow-up fixes: discount applied via `before_validate` hook with item rate recalculation, and `discount_percent` made non-mandatory
- **Multi Print Setting (Sales Invoice auto-printing):** auto-print Sales Invoices on submit via QZ Tray, configured in a Multi Print Setting single DocType with a Multi Print Format child table (print format + printer + copies). Realtime-based multi-print works from POS Awesome as well as standard forms, with a default-fallback toggle, trigger timing setting, configurable paper size per print format, and iframe-based print preview. Adds the 80MM Token print format for Sales Invoice thermal receipts
- **User Print Config:** per-user printer configuration with QZ Tray printer detection and availability checking, plus print preview
- **Dashboards:** three new dashboards — Owner (`/app/owner-dashboard`), Employee, and Wall Display — backed by `dashboard_api.py` with 9 whitelisted endpoints (KPIs, bundle stock report, short items, PO status, employee performance, loose sales, revenue trend, payment breakdown, recent invoices). Adds `custom_sell_goal` field on Product Bundle. Wall Display is a fullscreen dark-theme view for the shop TV
- **Product Bundle printing:** Print button on the Product Bundle form plus Bulk Print in List View, with wkhtmltopdf-compatible PDF layout

### Bug Fixes
- **Fix duplicate prints from POS:** realtime multi-print is skipped when Fast Print already handled the invoice, and matching uses `doc.owner` instead of `session.user` so prints fire correctly from POS submissions
- **Fix 80MM receipt blank space and A4 shrinking:** receipts print via QZ Tray at true 80mm height with the Frappe HTML wrapper stripped; A4 formats use browser print so content is no longer scaled down

---

## [1.4.0] - 2026-03-29

### New Features
- **PO Follow Up:** new DocType for the Purchase Manager to track supplier follow-ups on Purchase Orders — per-item delivery tracking, summary fields on the PO form, automatic reminders via scheduler, and a filterable report with chart
- **Return Scanner:** barcode-driven scanning page for building Sales/Purchase Returns. Strict mode pulls rate and qty from the original invoice; also intended to support lookup by item code and item name for items without barcodes (see Known Issues below)
- **Product Bundle rate/discount/account fetching:** when pulling bundle items into PO/SO, rates are fetched with a single batched Item Price query instead of one server call per item; discounts come from the Item UOM Discount child table (same source as POS Awesome); income/expense accounts fall back to Company defaults when Item Default is empty; server-side `fill_missing_item_defaults` runs on `before_validate`
- **Advanced Search for Product Bundle:** advanced item search in the bundle selection dialog and on the Product Bundle form (Ctrl+Q quick add, Ctrl+B)

### Bug Fixes
- **Fix duplicate Item Price entries:** when multiple Item Price rows exist for an item, use the latest (`order_by modified desc`)
- **Fix Product Bundle "Not Available" items:** NA items are skipped when pulling bundle items, the async call is fixed, `custom_bundle_id` is set on inserted rows, and `product_bundle.js` was added to the Sales Order hooks

### Known Issues
- **Return Scanner non-barcode lookups crash:** `return_scanner_api.py:186` re-reads `scan_result["item_code"]` after the fallback lookups, so any scan resolved via item code or item name (anything that is not a direct barcode hit) raises `KeyError` instead of returning the item. ~~Open bug, fix pending~~ **Fixed in [1.6.1] (2026-07-13)**

---

## [1.3.0] - 2026-02-28

### New Features
- **Get Items from Product Bundle:** "Get Items from Product Bundle" button on Sales Order, Sales Invoice, Purchase Order, Purchase Invoice, and Material Request — select a bundle and its child items are appended to the item table. The dialog previews the bundle's items and shows the parent item name and description
- **School Name field on SO/PO/SI:** new `custom_school_name` field on Sales Order, Purchase Order, and Sales Invoice, plus the KGS Purchase Order print format and a `setup_school_fields` API for remote deployment. Initially added as a Data field, then converted to a Link to the School master — Frappe forbids fieldtype changes on save, so the old Data fields are deleted and recreated as Link, with upgrade logic in `setup_school_fields()` for production
- **Transport Name field on Purchase Order** plus Remark field rename, and KGS Purchase Order print format enhancements: Rate and Amount columns, purchase manager contact info in the header, company-standard footer layout with reduced spacing

### Bug Fixes
- **Fix Brand field hidden by book_sample_section:** repaired the Item field chain and re-exported fixtures; also added missing custom fields to the `custom_field.json` fixture
- **Fix PO print format crash on missing supplier address:** `s_addr` was undefined when the supplier had no address; the format is now hardened against missing data generally

---

## [1.2.0] - 2026-02-26

### New Features
- **Sales Order to Purchase Order (Supplier Wise):** Custom "Create > PO (Supplier Wise)" button on submitted Sales Orders. Opens a dialog showing all pending items with their default suppliers (editable). Creates one Purchase Order per supplier. Items without a default supplier are grouped under a "No Supplier" placeholder PO
- **Auto-populate supplier on Sales Order items:** Book Item Creator now sets `default_supplier` in the Item Default table (in addition to Item Supplier table). This allows ERPNext to auto-fill the supplier when items are added to Sales Orders
- **Backfill item default suppliers:** One-time utility API (`backfill_item_default_suppliers`) to populate `Item Default.default_supplier` from `Item Supplier` table for all existing items

---

## [1.1.0] - 2026-02-26

### Bug Fixes
- **Fix retry_failed_items crash:** Added missing try/except around price list and stock entry creation during retry. Previously, a price list error would crash the entire retry for that item, even though the item was already created successfully
- **Fix retry_failed_items data loss:** Added `frappe.db.commit()` after each row during retry. Previously, if one row failed mid-loop, all prior successful rows could be rolled back
- **Fix report date filter:** Reports using `to_date` filter were cutting off same-day records because a date string was compared against a datetime `creation` field. Now appends `23:59:59` to include the full day
- **Fix duplicate rows in Book Items Report:** LEFT JOIN with `tabBin` produced duplicate rows for items with stock in multiple warehouses. Fixed by using `SUM()` with `GROUP BY`
- **Fix report crash on empty filters:** Both reports crashed with `AttributeError` when `filters=None`. Added null guard
- **Fix CSV import silent failures:** `parse_csv_file` silently skipped invalid classes (only logged errors). Now returns a `skipped` array with row numbers and reasons, displayed to the user in the import dialog
- **Fix CSV parser crash on None keys:** Added guard for `None` dictionary keys from malformed CSV files
- **Fix Quick Add count display:** Alert showed total classes from server instead of actually added count. Now tracks and displays the correct number of newly added classes, and shows "All classes already added" when none were new
- **Fix CSV template memory leak:** `URL.createObjectURL()` was never revoked after template download. Added `URL.revokeObjectURL()` cleanup
- **Fix duplicate check performance:** ISBN and class duplicate checks used `list` (O(n) lookup) instead of `set` (O(1) lookup)
- **Fix setup.py requirements parsing:** `requirements.txt` contains only a comment line, which was incorrectly parsed as a dependency. Now filters empty lines and `#` comments
- **Remove unused `cint` import** from book_item_creator.py

### Security
- **Fix exported CSV files exposed publicly:** `export_items_to_excel` used `is_private=0`, making business data accessible without authentication. Changed to `is_private=1`

### Deployment
- **Enhanced backup before deploy:** Changed from basic `bench backup` to `bench backup --with-files` (includes uploaded files, not just database)
- **Backup verification:** Deploy now checks that backup file exists and has reasonable size (> 1KB). If backup fails, deployment is **aborted** to protect production data
- **Backup retention:** Automatically keeps the last 10 backups and cleans up older ones to prevent disk space issues
- **Improved logging:** Clear numbered step-by-step output in deployment logs for easier debugging

### Other
- Added `.deploy-keys/` to `.gitignore`
- Comprehensive README rewrite with full feature documentation
- Added CHANGELOG.md

---

## [1.0.3] - 2026-02-23

### Bug Fixes
- **Fix Quick Add class filters:** Changed from `BETWEEN` to `>=` and `<=` filters for sort_order ranges to correctly match class groupings

### Changes
- **Updated Quick Add class groupings:** Reorganized to match Indian school structure:
  - Pre-Primary: Nursery, LKG, UKG (sort_order 1-3)
  - Primary: Class 1-5 (sort_order 4-8)
  - Middle: Class 6-8 (sort_order 9-11)
  - High: Class 9-10 (sort_order 12-13)
  - Hr. Sec.: Class 11-12 (sort_order 14-15)

---

## [1.0.2] - 2026-02-23

### Deployment Fixes
- **Fix stale app cleanup:** Clean stale backup app references (`*_backup_*`) from `apps/` directory and `sites/apps.txt` before building
- **Fix upstream remote:** Handle `upstream` remote name (used by `bench get-app`) instead of assuming `origin`
- **Fix first-time install:** Handle case where app directory doesn't exist yet (fresh installation vs update)

---

## [1.0.1] - 2026-02-23

### New Features
- **GitHub Actions CI/CD:** Added automated deployment workflow that triggers on push to `main` branch
  - SSH-based deployment to production server
  - Automatic backup, code pull, migrate, build, cache clear, restart

### Bug Fixes (from v1.0.0 audit)
- **Fix SQL injection in reports:** Replaced f-string SQL interpolation with parameterized queries using `%(param)s` placeholders
- **Fix ISBN made non-mandatory:** ISBN/Barcode is now optional (not all books have ISBNs)
- **Fix synchronous item creation:** Moved item creation to background job using `frappe.enqueue()` to prevent HTTP timeouts
- **Fix API paths in JavaScript:** Corrected all `frappe.call` method paths from incorrect module paths to correct `trustbit_school_book_seller.trustbit_school_book.doctype.book_item_creator.book_item_creator.*`
- **Fix progress bar stale data:** Clear progress bar on every `refresh` and `onload` event to prevent showing outdated information
- **Fix realtime listener duplicates:** Remove existing `book_item_creation_progress` listener before adding new one to prevent duplicate event handlers
- **Fix progress bar calculation:** Calculate status from actual child table rows instead of summary fields for accuracy

---

## [1.0.0] - 2025-12-25

### Initial Release
- **Book Item Creator:** Submittable transaction DocType for bulk book item creation
- **Book Class Detail:** Child table for per-class pricing, ISBN, and opening stock
- **Publication:** Master DocType for publisher information with contact details
- **Subject:** Master DocType with 20 pre-loaded school subjects
- **Class Master:** Master DocType with 15 pre-loaded classes (Nursery to Class 12)
- **Auto Item Creation:** Creates ERPNext Items with custom fields for book metadata
- **Auto Price Lists:** Creates selling and buying Item Price entries
- **Auto Stock Entries:** Creates Material Receipt stock entries for opening stock
- **ISBN/Barcode Support:** Unique ISBN tracking with duplicate validation
- **Quick Add Classes:** Buttons to quickly add class groups
- **Real-Time Progress:** Live progress dialog during item creation
- **CSV Import/Export:** Import class details from CSV, export created items
- **Duplicate Entry:** Clone Book Item Creator with cleared ISBNs
- **Retry Failed:** Re-attempt failed item creation rows
- **Reports:** Book Creation Summary and Book Items Report
- **Workspace:** Dedicated "School Book Seller" workspace
- **12 Custom Fields on Item:** Publication, Subject, Class, Author, Edition, Year, ISBN, Discounts, Creator reference
- **Fixtures:** Auto-export for Subject, Class Master, and Custom Field data
- **Post-Install Setup:** Automatic creation of custom fields, default classes, and subjects
