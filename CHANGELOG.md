# Changelog

All notable changes to the **Trustbit School Book Seller** app are documented here.

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
