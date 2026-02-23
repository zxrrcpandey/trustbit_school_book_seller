# Trustbit School Book Seller - Details & Bug Tracker

## App Overview
Custom ERPNext app for **bulk book item creation** for school book sellers. Allows creating multiple Items (one per class) from a single form, with automatic Price List entries, Stock Entries (opening stock), and barcode assignment.

**GitHub:** https://github.com/zxrrcpandey/trustbit_school_book_seller
**Production:** kgs.trustbit.cloud

---

## Doctypes

| Doctype | Type | Purpose |
|---------|------|---------|
| **Book Item Creator** | Submittable | Main form — define book details, add class rows, submit to create Items |
| **Book Class Detail** | Child Table | Per-class row (class, selling rate, valuation rate, ISBN, opening stock) |
| **Book Creation Log** | Child Table | Detailed creation log (item status, stock entry status, price list status) |
| **Publication** | Master | Publisher/Publication house (name, code, contact details) |
| **Subject** | Master | School subject (name, short code, sort order) |
| **Class Master** | Master | School class (Nursery, LKG, Class 1-12 with sort order) |

## Reports
| Report | Purpose |
|--------|---------|
| **Book Creation Summary** | Overview of all Book Item Creator submissions — status, success rate, stock value |
| **Book Items Report** | List all created book items with current stock, selling rate, publication, class |

## Key Features
- **Bulk creation:** One form creates Items for multiple classes at once
- **Auto Price Lists:** Creates selling & buying Item Price entries
- **Auto Stock Entry:** Creates Material Receipt for opening stock
- **ISBN/Barcode:** Unique ISBN per class row, auto-creates Item barcode
- **Quick Add Classes:** Buttons for Primary (Nursery-5), Middle (6-10), Senior (11-12), All
- **CSV Import/Export:** Import class details from CSV, export created items to CSV
- **Duplicate:** Clone a Book Item Creator (clears ISBNs for re-entry)
- **Retry Failed:** Re-attempt failed item creation rows
- **Progress Dialog:** Real-time progress bar during item creation via `frappe.publish_realtime`
- **Custom Fields on Item:** Publication, Subject, Class, Author, Edition, Publication Year, ISBN, Discounts

## Custom Fields Added to Item Doctype
| Fieldname | Type | Options |
|-----------|------|---------|
| `custom_book_details_section` | Section Break | — |
| `custom_publication` | Link | Publication |
| `custom_subject` | Link | Subject |
| `custom_class` | Link | Class Master |
| `custom_author` | Data | — |
| `custom_edition` | Data | — |
| `custom_publication_year` | Data | — |
| `custom_isbn_barcode` | Data (unique) | — |
| `custom_discount_section` | Section Break | — |
| `custom_sales_discount_percent` | Percent | — |
| `custom_purchase_discount_percent` | Percent | — |
| `custom_book_item_creator` | Link (read-only) | Book Item Creator |

---

## Key Files
| File | Purpose |
|------|---------|
| `hooks.py` | App config — fixtures, after_install, doctype_js |
| `install.py` | Post-install — creates custom fields, default classes & subjects |
| `public/js/book_item_creator.js` | Client-side logic — progress dialog, CSV import, quick add, etc. |
| `doctype/book_item_creator/book_item_creator.py` | Server-side — item creation, price lists, stock entries, whitelisted APIs |
| `doctype/book_class_detail/` | Child table for class-wise book details |
| `doctype/book_creation_log/` | Child table for creation log (appears unused in Python code) |
| `report/book_creation_summary/` | Script report — summary of all book creation entries |
| `report/book_items_report/` | Script report — list all created book items |
| `fixtures/class_master.json` | Fixture data for Class Master |
| `fixtures/subject.json` | Fixture data for Subject |

---

## Bugs & Issues Found

### BUG 1: SQL Injection in Reports (CRITICAL)
**Status:** OPEN
**Severity:** Critical (Security)
**Files:** `report/book_creation_summary/book_creation_summary.py:39-47`, `report/book_items_report/book_items_report.py:39-47`
**Description:** Both reports build SQL queries using f-strings with user-supplied filter values directly interpolated:
```python
conditions += f" AND publication = '{filters.get('publication')}'"
```
This is vulnerable to SQL injection. A malicious filter value like `' OR 1=1 --` could expose or modify data.
**Fix:** Use parameterized queries with `%(param)s` placeholders and pass values dict to `frappe.db.sql()`.

### BUG 2: Book Creation Log Table Never Populated
**Status:** OPEN
**Severity:** Low (Dead Feature)
**File:** `doctype/book_item_creator/book_item_creator.json` (field: `creation_log`)
**Description:** The `Book Creation Log` child table is defined in the doctype JSON and has fields (class, item_code, timestamp, statuses, remarks, stock_entry_link), but the Python code in `book_item_creator.py` never writes to it. The `create_items()` method updates `Book Class Detail` rows directly but never appends to `creation_log`. This means the "Creation Log" section on the form is always empty.
**Fix:** Either populate the creation_log table during `create_items()`, or remove the unused doctype and field.

### BUG 3: `check_isbn_exists` Doesn't Exclude Current Document Rows
**Status:** OPEN
**Severity:** Low
**File:** `book_item_creator.py:329-334`
**Description:** The `check_isbn_exists` whitelisted function checks for ISBN in submitted Book Item Creators but doesn't use the `exclude_doc` parameter to filter out the current document's own rows:
```python
WHERE bcd.isbn_barcode = %s AND bic.docstatus = 1
```
Should be:
```python
WHERE bcd.isbn_barcode = %s AND bic.docstatus = 1 AND bic.name != %s
```
The `exclude_doc` arg is accepted but never used in the query.

### BUG 4: Stock User Gets Cancel + Amend But No Delete
**Status:** OPEN
**Severity:** Low (Permissions)
**File:** `book_item_creator.json` permissions
**Description:** Stock User role can cancel and amend Book Item Creator documents but cannot delete them. This is inconsistent — typically users who can cancel should also be able to delete, or neither.

### BUG 5: Potential Race Condition in ISBN Duplicate Check
**Status:** OPEN
**Severity:** Low
**File:** `book_item_creator.py:35-65`
**Description:** The `check_duplicate_isbn` validation runs during `validate()` but items are created during `on_submit()`. If two Book Item Creators with overlapping ISBNs are submitted simultaneously, both could pass validation before either creates items. The `custom_isbn_barcode` field is `unique: 1` on the Custom Field which provides a DB-level safety net, but the error message would be a raw database error rather than a user-friendly message.

### ISSUE 6: Synchronous Item Creation Blocks Request
**Status:** OPEN (Enhancement)
**Severity:** Medium
**File:** `book_item_creator.py:96-184`
**Description:** The `create_items()` method runs synchronously in `on_submit()`. For documents with many classes (e.g., 15 rows), this means the HTTP request stays open for the entire duration of creating 15 items + 15 price list entries + 15 stock entries. This could timeout on slow servers.
**Recommendation:** Consider using `frappe.enqueue()` for background processing, with realtime updates already in place.

### ISSUE 7: `.DS_Store` in Repository
**Status:** OPEN (Cleanup)
**File:** `.DS_Store`
**Description:** macOS `.DS_Store` file committed to repo. Should be in `.gitignore`.

---

## Deployment Notes
- This app uses `fixtures` in hooks.py for Subject, Class Master, and Custom Field data
- After install: `bench --site kgs.trustbit.cloud migrate` (to create doctypes)
- Fixtures auto-import on `bench --site kgs.trustbit.cloud migrate`
- Custom fields on Item doctype are created both via `after_install` hook AND via fixtures — the fixtures approach is preferred for production
- The `after_install` hook also creates default classes (Nursery-Class 12) and subjects (20 common subjects)

## Architecture Notes
- Module: `Trustbit School Book`
- Naming: `BOOK-ENTRY-.#####` (auto-naming series)
- Item naming: `{Publication} {Book Name} {Class}` (e.g., "NCERT Mathematics Class 10")
- Barcode type: Empty string (accepts any format, not restricted to EAN-13)
- Realtime event: `book_item_creation_progress` (used for progress dialog updates)
