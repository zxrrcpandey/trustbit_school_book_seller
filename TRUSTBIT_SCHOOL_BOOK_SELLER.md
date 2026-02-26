# Trustbit School Book Seller - Technical Reference

## App Overview
Custom ERPNext app for **bulk book item creation** for school book sellers. Allows creating multiple Items (one per class) from a single form, with automatic Price List entries, Stock Entries (opening stock), and barcode assignment.

**GitHub:** https://github.com/zxrrcpandey/trustbit_school_book_seller
**Production:** kgs.trustbit.cloud
**Version:** 1.1.0

---

## DocTypes

| DocType | Type | Purpose |
|---------|------|---------|
| **Book Item Creator** | Submittable | Main form — define book details, add class rows, submit to create Items |
| **Book Class Detail** | Child Table | Per-class row (class, selling rate, valuation rate, ISBN, opening stock) |
| **Book Creation Log** | Child Table | Reserved for future audit trail functionality |
| **Publication** | Master | Publisher/Publication house (name, code, contact details) |
| **Subject** | Master | School subject (name, short code, sort order) |
| **Class Master** | Master | School class (Nursery, LKG, Class 1-12 with sort order) |

## Reports
| Report | Type | Purpose |
|--------|------|---------|
| **Book Creation Summary** | Script Report | Overview of all Book Item Creator submissions — status, success rate, stock value |
| **Book Items Report** | Script Report | List all created book items with current stock, selling rate, publication, class |

## Custom Fields Added to Item DocType
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
| `doctype/book_creation_log/` | Child table reserved for future audit trail |
| `report/book_creation_summary/` | Script report — summary of all book creation entries |
| `report/book_items_report/` | Script report — list all created book items |
| `fixtures/class_master.json` | Fixture data for Class Master |
| `fixtures/subject.json` | Fixture data for Subject |

---

## Known Issues & Future Improvements

### Book Creation Log Table (Unused)
**Severity:** Low (Dead Feature)
**Status:** By Design — reserved for future use
**Description:** The `Book Creation Log` child table DocType exists but is not currently populated by any code. Creation status tracking is handled directly on `Book Class Detail` rows. The DocType is kept for future detailed audit trail functionality.

### Race Condition in ISBN Duplicate Check
**Severity:** Low (Mitigated)
**Status:** Mitigated by DB constraint
**Description:** The `check_duplicate_isbn` validation runs during `validate()` but items are created during `on_submit()` (background job). If two Book Item Creators with overlapping ISBNs are submitted simultaneously, both could pass validation. However, the `custom_isbn_barcode` field has a `unique: 1` DB constraint that prevents actual duplicates. The error message in this rare case would be a database error rather than a user-friendly message, but the code includes a friendly message handler for `Duplicate entry` errors.

---

## Architecture Notes
- **Module:** Trustbit School Book
- **Naming:** `BOOK-ENTRY-.#####` (auto-naming series)
- **Item naming:** `{Publication} {Book Name} {Class}` (e.g., "NCERT Mathematics Class 10")
- **Background Jobs:** `frappe.enqueue()` on `default` queue, 600s timeout
- **Realtime event:** `book_item_creation_progress` (used for progress dialog updates)
- **Barcode type:** Empty string (accepts any format, not restricted to EAN-13)
- **Fixtures:** Subject, Class Master, Custom Field (exported via `bench export-fixtures`)
- **Custom fields** on Item are created both via `after_install` hook AND via fixtures — the fixtures approach is preferred for production

## Deployment Notes
- Automated via GitHub Actions on push to `main`
- **Mandatory backup** before every deployment (with file verification)
- Keeps last 10 backups automatically
- Deploy aborts if backup fails
- See [README.md](README.md) for full deployment documentation
