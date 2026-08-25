# Trustbit School Book Seller - Technical Reference

## App Overview
Custom ERPNext app for **bulk book item creation** for school book sellers. Allows creating multiple Items (one per class) from a single form, with automatic Price List entries, Stock Entries (opening stock), and barcode assignment. Since March 2026 the app has grown to also cover Privilege Cards, PO Follow Up, Return Scanner, Multi Print, Product Bundle helpers, and desk dashboards.

**GitHub:** https://github.com/zxrrcpandey/trustbit_school_book_seller
**Production:** splashbox.in (200.234.38.57) since 2026-08-23 — the old `kgs.trustbit.cloud` box is parked and being deleted; never deploy to it
**Version:** 1.0.0 (code metadata — `__init__.py`, `setup.py`, `hooks.py` all declare 1.0.0; CHANGELOG.md documents releases through 1.6.0 as documentation-only versions — the bumps were never applied to the code, so `bench version` reports 1.0.0)

---

## DocTypes (15)

| DocType | Type | Purpose |
|---------|------|---------|
| **Book Item Creator** | Submittable | Main form — define book details, add class rows, submit to create Items |
| **Book Class Detail** | Child Table | Per-class row (class, selling rate, valuation rate, ISBN, opening stock) |
| **Book Creation Log** | Child Table | Reserved for future audit trail functionality |
| **Publication** | Master | Publisher/Publication house (name, code, contact details) |
| **Subject** | Master | School subject (name, short code, sort order) |
| **Class Master** | Master | School class (Nursery, LKG, Class 1-12 with sort order) |
| **Privilege Card** | Document | Customer discount card — holder, school/class, card type, discount %, issue/expiry dates, status |
| **Privilege Card Type** | Master | Card type (name, discount %, description, disabled flag) |
| **Privilege Card Usage Log** | Child Table | Usage entries logged on the Privilege Card per SO/SI submit |
| **PO Follow Up** | Document | Follow-up record against a Purchase Order — contact person, status, next follow-up date, expected delivery |
| **PO Follow Up Item** | Child Table | Per-item rows on a PO Follow Up |
| **Return Scanner Settings** | Single | Config for barcode-based return scanning on SI/PI (return mode, qty limits, scan sound) |
| **Multi Print Setting** | Single | Multi Print config — trigger, token settings, format list, per-user config HTML |
| **Multi Print Format** | Child Table | Print format rows inside Multi Print Setting |
| **User Print Config** | Document | Per-user print format/printer configuration |

## Reports (4)
| Report | Type | Purpose |
|--------|------|---------|
| **Book Creation Summary** | Script Report | Overview of all Book Item Creator submissions — status, success rate, stock value |
| **Book Items Report** | Script Report | List all created book items with current stock, selling rate, publication, class |
| **PO Follow Up Report** | Script Report | Follow-up status across Purchase Orders (last/next follow-up, overall status) |
| **Privilege Card Usage** | Script Report | Card usage history from Privilege Card Usage Log entries |

## Desk Pages (3)
| Page | Purpose |
|------|---------|
| **owner_dashboard** | Owner-facing sales/business dashboard |
| **employee_dashboard** | Employee-facing dashboard |
| **wall_display** | Shop wall display — polls every 8 minutes (reduced from 30s, Jul 2026), clock is client-side |

## Custom Fields (32 in fixture)

### Item (17 fields — the insert_after chain, must stay unbroken)
| Fieldname | Type | Options |
|-----------|------|---------|
| `custom_book_details_section` | Section Break | — |
| `custom_publication` | Link | Publication |
| `custom_subject` | Data | — (see divergence note below) |
| `custom_class` | Data | — (see divergence note below) |
| `custom_class_grades` | Table MultiSelect | Item Class Grade |
| `custom_column_break_book` | Column Break | — |
| `custom_author` | Data | — |
| `custom_edition` | Data | — |
| `custom_edition_year` | Data | — |
| `custom_publication_year` | Data | — |
| `custom_isbn` | Data (unique) | — |
| `custom_isbn_barcode` | Data (unique) | — |
| `custom_publisher` | Link | Supplier |
| `custom_discount_section` | Section Break | — |
| `custom_sales_discount_percent` | Percent | — |
| `custom_purchase_discount_percent` | Percent | — |
| `custom_book_item_creator` | Link (read-only) | Book Item Creator |

> **install.py vs fixture divergence:** `install.py` creates `custom_subject` as Link→Subject and `custom_class` as Link→Class Master, but the exported fixture (`fixtures/custom_field.json`) defines both as plain **Data** fields with no options — and the fixture wins on every `bench migrate`. On production these fields are effectively Data with **no link validation** against the Subject/Class Master masters. If Link behavior is wanted, fix the fixture (not just install.py) and re-export.

### Other DocTypes (15 fields)
| DocType | Fields |
|---------|--------|
| Sales Order (3) | `custom_school_name` (Link→School), `custom_privilege_card` (Link→Privilege Card), `custom_privilege_card_discount` (Percent, read-only) |
| Sales Invoice (3) | Same three as Sales Order |
| Purchase Order (9) | `custom_school_name` (Link→School), `custom_remark` (Small Text), `custom_transport_name` (Data), plus 6 follow-up summary fields: `custom_followup_section`, `custom_last_followup_date`, `custom_last_followup_status`, `custom_column_break_followup`, `custom_next_followup_date`, `custom_total_followups` (all read-only) |

> **Note:** the fixture filter in `hooks.py` also lists a 33rd field name, `Product Bundle-custom_sell_goal`, which is not yet present in `fixtures/custom_field.json` — re-exporting fixtures will pick it up.

---

## Key Files
| File | Purpose |
|------|---------|
| `hooks.py` | App config — fixtures, after_install, doctype_js (9 DocTypes), app_include_js (`sales_invoice_print.js`, `po_print_title.js`), doc_events (SI/SO/PO/PI), scheduler_events (3 daily jobs), `override_whitelisted_methods` (PDF download), `update_website_context` |
| `install.py` | Post-install — creates custom fields, default classes & subjects |
| `api.py` | Product Bundle items (batch rates/UOM discounts/Item Default accounts), SO→PO Supplier Wise, fill_missing_item_defaults hook, school-name copy to SI, `download_pdf` override (PO PDFs named "\<PO ID\> - \<Supplier Name\>.pdf", Jul 13 2026), `update_website_context` (PO /printview page title) |
| `privilege_card.py` | Privilege Card validation on SO/SI, usage logging on submit, daily card expiry job |
| `followup_api.py` | PO Follow Up APIs + daily reminder/missing-followup scheduler jobs |
| `return_scanner_api.py` | Return Scanner barcode lookup + return invoice creation (see Known Issues) |
| `dashboard_api.py` | Data APIs for owner/employee dashboards and wall display |
| `public/js/product_bundle.js` | Get Items from Product Bundle dialog (MR, SI, SO, PO, PI) — batch rates/discounts/accounts |
| `public/js/product_bundle_form.js` | Product Bundle form — print button / bulk print |
| `public/js/book_item_creator.js` | Client-side logic — progress dialog, CSV import, quick add, etc. |
| `public/js/sales_order.js` | Sales Order customization — "PO (Supplier Wise)" button and dialog |
| `public/js/privilege_card_so_si.js` | Privilege Card selection + discount on SO/SI |
| `public/js/purchase_order_followup.js` | PO Follow Up buttons/summary on Purchase Order |
| `public/js/return_scanner.js` | Return Scanner UI on SI/PI |
| `public/js/multi_print_setting.js`, `public/js/user_print_config.js` | Multi Print configuration UIs |
| `public/js/sales_invoice_print.js` | Global (app_include_js) — SI print behavior |
| `public/js/po_print_title.js` | Global (app_include_js) — sets desk print page title so system print dialog suggests "\<PO ID\> - \<Supplier Name\>" (Jul 13 2026) |
| `doctype/book_item_creator/book_item_creator.py` | Server-side — item creation, price lists, stock entries, whitelisted APIs |
| `doctype/book_class_detail/` | Child table for class-wise book details |
| `doctype/book_creation_log/` | Child table reserved for future audit trail |
| `report/` | 4 script reports (see Reports table) |
| `fixtures/class_master.json` | Fixture data for Class Master |
| `fixtures/subject.json` | Fixture data for Subject |
| `fixtures/custom_field.json` | 32 Custom Field records (see Custom Fields section) |
| `fixtures/print_format.json` | Print Format fixture — "KGS Purchase Order", "80MM Token" |

---

## Known Issues & Future Improvements

### Return Scanner Fallback Lookup Crashes (FIXED 2026-07-13)
**Severity:** High
**Status:** Fixed in v1.6.1 — the full fallback chain (barcode → item code → item name → fuzzy LIKE) now works
**Description:** In `return_scanner_api.py`, after the fallback lookups succeeded, the code re-executed `item_code = scan_result["item_code"]` — but `scan_result` only contains `item_code` when the original barcode lookup matched, so every fallback path crashed with a `KeyError`. Fixed by removing the stray reassignment.

### Book Creation Log Table (Unused)
**Severity:** Low (Dead Feature)
**Status:** By Design — reserved for future use
**Description:** The `Book Creation Log` child table DocType exists but is not currently populated by any code. Creation status tracking is handled directly on `Book Class Detail` rows. The DocType is kept for future detailed audit trail functionality.

### Race Condition in ISBN Duplicate Check
**Severity:** Low (Mitigated)
**Status:** Mitigated by DB constraint
**Description:** The `check_duplicate_isbn` validation runs during `validate()` but items are created during `on_submit()` (background job). If two Book Item Creators with overlapping ISBNs are submitted simultaneously, both could pass validation. However, the `custom_isbn_barcode` field has a `unique: 1` DB constraint that prevents actual duplicates. The error message in this rare case would be a database error rather than a user-friendly message, but the code includes a friendly message handler for `Duplicate entry` errors.

### PO PDF Filename — Accepted Gaps (Jul 2026)
**Severity:** Low (By Design)
**Description:** The PO PDF filename override covers single-document downloads and print flows. Bulk list-view PDF export still produces a merged "Purchase-Order.pdf", and Print Format Builder Beta formats would bypass the override (they route to weasyprint). Both accepted as-is.

---

## Architecture Notes
- **Module:** Trustbit School Book
- **Naming:** `BOOK-ENTRY-.#####` (auto-naming series)
- **Item naming:** `{Publication} {Book Name} {Class}` (e.g., "NCERT Mathematics Class 10")
- **Background Jobs:** `frappe.enqueue()` on `default` queue, 600s timeout
- **Realtime event:** `book_item_creation_progress` (used for progress dialog updates)
- **Barcode type:** Empty string (accepts any format, not restricted to EAN-13)
- **Scheduler:** 3 daily jobs — privilege card expiry, PO follow-up reminders, POs-without-followups check
- **Fixtures:** Subject, Class Master, Custom Field, **Print Format** ("KGS Purchase Order", "80MM Token") — exported via `bench export-fixtures`
  - **WARNING:** fixtures are reimported on every `bench migrate`, which silently **overwrites any DB-only edits** to these records. Never edit the fixture-managed Print Formats only in the DB — update the fixture JSON in the repo (or edit in DB *and* re-export before the next migrate).
- **Custom fields** on Item are created both via `after_install` hook AND via fixtures — the fixtures approach is preferred for production (and is what governs field types; see the install.py/fixture divergence note above)

## Deployment Notes
- Automated via GitHub Actions on push to `main`
- **Mandatory backup** before every deployment (with file verification)
- Keeps last 10 backups automatically
- Deploy aborts if backup fails
- See [README.md](README.md) for full deployment documentation
