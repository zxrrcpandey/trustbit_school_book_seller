# Trustbit School Book Seller - Complete Project Work Log

## Project Overview

**App:** Trustbit School Book Seller (ERPNext custom app)
**GitHub:** https://github.com/zxrrcpandey/trustbit_school_book_seller
**Production:** kgs.trustbit.cloud (82.25.105.136)
**Work Period:** February 2026
**Starting Version:** 1.0.0 | **Final Version:** 1.5.0

**POS Awesome App:**
**GitHub:** https://github.com/zxrrcpandey/POS-Awesome-V15-trustbit-2

---

## Task 1: Full Codebase Audit & Bug Fixes

**Request:** "Check this carefully, we need this modify, customize and make bugs free"

### Bugs Found & Fixed (v1.1.0)

| # | Bug | Severity | Root Cause | Fix |
|---|-----|----------|-----------|-----|
| 1 | `retry_failed_items` crashes on price list error | High | No try/except around price list and stock entry creation during retry | Added try/except blocks matching the pattern in `create_items()` |
| 2 | `retry_failed_items` loses data on partial failure | High | No `frappe.db.commit()` per row — if one row fails mid-loop, all prior successes roll back | Added `frappe.db.commit()` after each successful row |
| 3 | Report `to_date` filter cuts off same-day records | Medium | Date string compared against datetime `creation` field — records after midnight excluded | Appended `" 23:59:59"` to `to_date` filter value |
| 4 | Book Items Report shows duplicate rows | Medium | `LEFT JOIN` with `tabBin` produced duplicates for items in multiple warehouses | Changed to `SUM(bin.actual_qty)`, `SUM(bin.stock_value)` with `GROUP BY i.name` |
| 5 | Both reports crash when `filters=None` | Medium | `filters.get()` fails with `AttributeError` when filters is `None` | Added `if not filters: filters = {}` guard |
| 6 | CSV import silently skips invalid classes | Medium | `parse_csv_file` only logged errors, never told the user | Returns `skipped` array with row numbers and reasons, shown in import dialog |
| 7 | CSV parser crashes on `None` dictionary keys | Low | Malformed CSV files produce `None` keys | Added guard for `None` keys |
| 8 | Quick Add shows wrong count in alert | Low | Alert showed `r.message.length` (total from server) instead of actually added count | Tracks `added_count` separately, shows "All classes already added" when none were new |
| 9 | CSV template download causes memory leak | Low | `URL.createObjectURL()` never revoked | Added `URL.revokeObjectURL(url)` after download |
| 10 | ISBN/class duplicate checks are O(n) | Low | Used `list` for seen items (O(n) lookup per check) | Changed to `set` (O(1) lookup) |
| 11 | `setup.py` parses comment lines as dependencies | Low | `requirements.txt` contains only `# frappe` comment, parsed as real dependency | Added filter for empty lines and `#` comments |
| 12 | Unused `cint` import | Low | Dead import | Removed |

### Security Fix

| Issue | Risk | Fix |
|-------|------|-----|
| `export_items_to_excel` creates public files (`is_private=0`) | Business data accessible without authentication | Changed to `is_private=1` |

### Files Modified
- `trustbit_school_book_seller/trustbit_school_book/doctype/book_item_creator/book_item_creator.py`
- `trustbit_school_book_seller/public/js/book_item_creator.js`
- `trustbit_school_book_seller/trustbit_school_book/report/book_creation_summary/book_creation_summary.py`
- `trustbit_school_book_seller/trustbit_school_book/report/book_items_report/book_items_report.py`
- `setup.py`

---

## Task 2: Deployment Pipeline Hardening

**Request:** "Make sure on every push or update on production server first make backup, this is very important"

### Changes Made

| Enhancement | Before | After |
|-------------|--------|-------|
| Backup command | `bench backup` | `bench backup --with-files` (includes uploaded files) |
| Backup verification | None | Checks file exists AND size > 1KB |
| Backup failure | Deploy continues silently | **Deploy aborts** if backup fails |
| Backup retention | Unlimited (fills disk) | Keeps last 10, auto-cleans older |
| Logging | Minimal | Clear numbered step-by-step output |

### Bug Encountered: Deploy Script Failures

| Issue | Cause | Fix |
|-------|-------|-----|
| Deploy fails on first install | App directory doesn't exist yet | Added check: `if [ -d "app_dir" ]` |
| Stale app references crash build | `bench get-app` creates backup copies like `trustbit_*_backup_*` | Clean stale references from `apps/` and `sites/apps.txt` before build |
| `git pull origin main` fails | `bench get-app` names the remote `upstream`, not `origin` | Use `git pull upstream main` |

### File Modified
- `.github/workflows/deploy.yml`
- `.gitignore` (added `.deploy-keys/`)

---

## Task 3: SSH Key Setup for Automated Deployment

**Request:** "Deploy SSH keys"

### What Was Done
- Generated ED25519 SSH key pair in `.deploy-keys/` (gitignored)
- Provided instructions for:
  1. Adding public key to server's `/root/.ssh/authorized_keys`
  2. Configuring 3 GitHub Secrets: `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`

---

## Task 4: Documentation

**Request:** "I want every feature to be mentioned in README and every change log"

### Created/Updated
- **README.md** — Complete rewrite with 15 features, all DocTypes, reports, API reference, deployment guide, architecture, troubleshooting
- **CHANGELOG.md** — New file with v1.0.0 through v1.1.0 version history
- **TRUSTBIT_SCHOOL_BOOK_SELLER.md** — Cleaned up, removed 5 outdated/false bug reports
- **INSTALLATION.md** — Simplified to redirect to README.md

---

## Task 5: Add Default Supplier Feature

**Request:** "I want to add Default Supplier, it can be set into item master"

### Changes Made
1. **Added `default_supplier` Link field** to Book Item Creator DocType JSON — placed in "Item Configuration" section after `default_warehouse`
2. **Updated `create_single_item()`** — When default_supplier is set, populates `supplier_items` child table on the created Item
3. **Updated `duplicate_book_item_creator()`** — Copies `default_supplier` field to the duplicate

### Files Modified
- `trustbit_school_book_seller/trustbit_school_book/doctype/book_item_creator/book_item_creator.json`
- `trustbit_school_book_seller/trustbit_school_book/doctype/book_item_creator/book_item_creator.py`

---

## Task 6: Fix Redis Connection Error on Production

**Bug:** `redis.exceptions.ConnectionError: Error 111 connecting to 127.0.0.1:13000. Connection refused.`

### Root Cause
Redis cache service (port 13000) and queue service (port 11000) managed by Supervisor had crashed. This is a server infrastructure issue, not a code bug.

### Fix
```bash
supervisorctl restart all
```

### Verification
- Redis cache (port 13000): RUNNING, responds to PING
- Redis queue (port 11000): RUNNING, responds to PING
- Workers online: 2
- Site `kgs.trustbit.cloud`: HTTP 200

---

## Task 7: Sales Order to Purchase Order (Supplier Wise)

**Request:** "There is a feature in Sales Order where Sales Order can convert into Purchase Order supplier wise — please check carefully" + "Fix it, and if there is no supplier it should create separate PO with the name of No Suppliers"

### Investigation Findings

| Check | Result |
|-------|--------|
| Items with `Item Supplier` rows | 277 (non-book items like stationery) |
| Items with `Item Default > default_supplier` | **0** (zero!) |
| Book items (16 total) with any supplier set | **0** |
| Sales Order Items with supplier field filled | **All None** |

### Root Cause
The standard ERPNext "Against Default Supplier" feature reads `default_supplier` from `Item Default` child table → auto-populates `supplier` on Sales Order Item → groups by supplier to create POs. Since NO items had `default_supplier` set in `Item Default`, the feature was completely broken.

Additionally, the standard ERPNext code throws: *"Please set a Supplier against the Items to be considered in the Purchase Order"* when any items lack suppliers — it doesn't handle them gracefully.

### Solution Implemented (v1.2.0)

#### New Files Created

**`api.py`** — Server-side APIs:
- `get_so_items_with_suppliers(sales_order, include_ordered=0)` — Fetches pending SO items with their default suppliers. Falls back through: Item Default (company-specific) → Item Default (any company) → Item Supplier table
- `create_po_supplier_wise(sales_order, items)` — Groups items by supplier, creates one PO per supplier. Items without supplier go to "No Supplier" placeholder
- `backfill_item_default_suppliers()` — One-time utility to populate `Item Default.default_supplier` from `Item Supplier` table for existing items

**`public/js/sales_order.js`** — Client-side dialog:
- Adds "Create > PO (Supplier Wise)" button on all submitted Sales Orders
- Dialog shows items with editable Supplier (Link field) and editable Qty
- Pre-fills suppliers from item defaults
- Confirmation summary shows supplier grouping before creating

#### Files Modified

**`book_item_creator.py`** — Fixed `create_single_item()`:
```python
# Before: only set supplier_items
if self.default_supplier:
    item_data["supplier_items"] = [{"supplier": self.default_supplier}]

# After: also set item_defaults for auto-population in Sales Orders
if self.default_supplier:
    company = frappe.db.get_value("Warehouse", self.default_warehouse, "company")
    item_data["supplier_items"] = [{"supplier": self.default_supplier}]
    item_data["item_defaults"] = [{
        "company": company,
        "default_supplier": self.default_supplier,
    }]
```

**`hooks.py`** — Added Sales Order JS hook:
```python
doctype_js = {
    "Book Item Creator": "public/js/book_item_creator.js",
    "Sales Order": "public/js/sales_order.js"
}
```

### Bugs Encountered During Implementation

| # | Bug | Cause | Fix |
|---|-----|-------|-----|
| 1 | "PO (Supplier Wise)" button not visible | JS had `has_pending` check — all items in test SO already had POs, so button was hidden | Removed `has_pending` check — button shows on all submitted SOs, API handles empty results |
| 2 | Clicking button shows "No pending items" even though items exist | All items in SAL-ORD-2026-00001 had `ordered_qty == stock_qty` (POs already created) | Added `include_ordered` parameter — when no pending items, prompts user to re-create POs for all items |
| 3 | JS not loading after deploy | `bench build` not run after code pull, and services not restarted | Added `bench build --app trustbit_school_book_seller && bench clear-cache && supervisorctl restart all` to deploy flow |

### How the Feature Works (Final)

1. Open a submitted Sales Order → click **Create > PO (Supplier Wise)**
2. **If there are pending items** → dialog shows them with editable Qty and Supplier
3. **If all items already have POs** → prompt: "Do you want to create new Purchase Orders for all items again?"
   - Yes → dialog opens with ALL items at original SO quantities
   - Qty and Supplier are editable for each item
4. Select items → click "Create Purchase Orders"
5. Confirmation shows supplier grouping (e.g., "Genius Publishing: 4 items, No Supplier: 2 items")
6. POs are created (one per supplier, grouped automatically)
7. Redirects to Purchase Order list filtered by Sales Order

---

## Task 8: School Name (Remark) Field + PO Print Format

**Request:** "In Sales Order I need School Name as a Remark (Master). That Remark should show in Purchase Order, Invoice and Print format. I also need a Purchase Order Print format."

### Custom Fields Created (v1.3.0 → upgraded v1.5.0)

| DocType | Fieldname | Type | Label | Placement |
|---------|-----------|------|-------|-----------|
| Sales Order | `custom_school_name` | Link (School) | School Name | After `customer_name` |
| Purchase Order | `custom_school_name` | Link (School) | School Name | After `supplier_name` |
| Purchase Order | `custom_remark` | Small Text | Remark & Requisitioner | After `custom_school_name` |
| Purchase Order | `custom_transport_name` | Data | Transport Name | After `custom_remark` |
| Sales Invoice | `custom_school_name` | Link (School) | School Name | After `customer_name` |

**Notes:**
- All three DocTypes (SO, PO, SI) use **Link** fields to `School` DocType (from `trustbit_school_pro` app) — user picks from the School master
- Falls back to Data field if School DocType is not installed
- **v1.5.0 upgrade:** PO and SI school fields changed from Data → Link. Frappe doesn't allow fieldtype change via save, so the upgrade deletes the old Custom Field and recreates it as Link

### Data Propagation

| Flow | Mechanism |
|------|-----------|
| SO → PO (via "PO Supplier Wise") | `_create_po_for_supplier()` in `api.py` copies `custom_school_name` and `custom_remark` |
| SO → Sales Invoice | `doc_events` hook on Sales Invoice `before_save` — `copy_school_name_to_invoice()` finds linked SO and copies school name |

### KGS Purchase Order Print Format

Created a Jinja HTML print format for Purchase Order matching the company's standard layout:

| Section | Content |
|---------|---------|
| **Company Header** | Company name (uppercase), Purchase Manager mobile & email, address, GSTIN |
| **Title** | "PURCHASE ORDER" with border lines |
| **Left Column** | Party Details — supplier name, address, email, mobile |
| **Right Column** | Order No, Date, Transport, Remark/School, Shipping Address |
| **Items Table** | S.NO, Description, REMARK (item's class), Rate, Qty, Amount |
| **Grand Total** | Total qty and total amount |
| **Terms & Conditions** | From PO's terms field |
| **Signatures** | Authorised Signatory (left), Receiver Name/Date (right) |

### Print Format Enhancements (Multiple Iterations)

| # | Enhancement | Commit |
|---|-------------|--------|
| 1 | Added Rate and Amount columns to items table | `24e6cef` |
| 2 | Added Transport Name field, renamed Remark to "Remark & Requisitioner" | `45c871f` |
| 3 | Added supplier email/mobile from Address or Contact fallback | `45c871f` |
| 4 | Added company GSTIN, email, and phone from Company doc | `45c871f` |
| 5 | Fixed `s_addr is undefined` error when no supplier address | `71277fb` |
| 6 | Hardened template against missing data (None checks, `doc.get()` for custom fields, `or 0` for numerics) | `cbaf919` |
| 7 | Added hardcoded Purchase Manager contact: `8989434243` and `info@khandelwalgeneralstores.com` | `1927dac` |
| 8 | Updated footer to two-column bordered table: Terms & Conditions (left), Receiver's Signature + Authorised Signatory (right) | `6edc548` |
| 9 | Reduced footer vertical spacing — fewer `<br>` tags, smaller padding/margin | `ff70ea1` |

### Deployment Method

SSH port 22 was blocked on the server, so deployment was done via:
1. **GitHub Actions** — auto-deploy on push to `main` (pulls code, runs `bench migrate`, builds assets, restarts services)
2. **Frappe REST API** — called `setup_school_fields` API via HTTP to create custom fields without SSH access
3. **Frappe REST API** — updated print format HTML directly via `PUT /api/resource/Print Format/KGS Purchase Order`

### Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `install.py` | Modified | Added `create_school_custom_fields()` function |
| `hooks.py` | Modified | Added 4 custom field fixtures, `doc_events` for Sales Invoice, Print Format fixture |
| `api.py` | Modified | Added school field copy in `_create_po_for_supplier()`, new `copy_school_name_to_invoice()`, new `setup_school_fields()` API |
| `fixtures/print_format.json` | Created | KGS Purchase Order Jinja HTML print format |

### Bugs Encountered

| # | Bug | Cause | Fix |
|---|-----|-------|-----|
| 1 | Custom fields not appearing after deploy | `install.py`'s `after_install` only runs on first app install, not on `bench migrate` | Created whitelisted `setup_school_fields()` API endpoint callable via HTTP |
| 2 | SSH port 22 blocked | Server firewall blocks SSH from external networks | Used Frappe REST API + GitHub Actions (which has SSH access via secrets) |
| 3 | Print format error: `s_addr is undefined` (line 71) | `s_addr` defined inside `{% if %}` block but referenced outside | Moved variable definitions outside conditionals, set to `None` first |
| 4 | Intermittent Internal Server Error in print format | Missing data: no supplier address, no contact, None values for rate/qty on older POs | Hardened template with explicit None checks, `doc.get()` for custom fields, `or 0` fallback for numerics |

---

## Task 9: Fix wkhtmltopdf on Production

**Bug:** `Invalid wkhtmltopdf version: 'wkhtmltopdf 0.12.6-2 (with unpatched Qt)'`

### Root Cause
ERPNext requires the **patched Qt** version of wkhtmltopdf (0.12.6.1) for PDF generation. The server had the standard Ubuntu package (0.12.6-2 with unpatched Qt).

### Fix
```bash
wget -O /tmp/wkhtmltox.deb https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_amd64.deb
apt-get install -y -f /tmp/wkhtmltox.deb
```

### Verification
```
wkhtmltopdf 0.12.6.1 (with patched qt)
```

---

## Task 10: Redis Auto-Recovery Watchdog

**Problem:** Redis cache service (port 13000) keeps crashing intermittently, taking down the entire site with `ConnectionRefusedError: Error 111 connecting to 127.0.0.1:13000`.

### Solution
Set up a cron-based watchdog on the production server:

**Script:** `/usr/local/bin/check_redis.sh`
```bash
#!/bin/bash
if ! redis-cli -p 13000 ping > /dev/null 2>&1; then
    echo "$(date): Redis cache down, restarting all services" >> /var/log/redis_watchdog.log
    supervisorctl restart all >> /var/log/redis_watchdog.log 2>&1
fi
```

**Cron:** Runs every 1 minute
```
* * * * * /usr/local/bin/check_redis.sh
```

**Log:** `/var/log/redis_watchdog.log` — logs each auto-restart with timestamp

**Result:** If Redis crashes, the site auto-recovers within ~1 minute without manual intervention.

---

## Task 11: Fix Email Sending Issues

**Problem:** Emails not sending from ERPNext. Queue stuck with errors.

### Root Causes Found

| # | Issue | Cause | Fix |
|---|-------|-------|-----|
| 1 | 4 stuck emails with wrong senders | Senders `admin@example.com` and `saransh42@yahoo.in` not authorized on Zoho SMTP | Deleted stuck emails from queue |
| 2 | Zoho relay rejection (`553 Sender not allowed to relay`) | ERPNext was using the triggering user's email as sender instead of the account email | Enabled `always_use_account_email_id_as_sender` on KGS Support email account |
| 3 | Emails stuck as "Not Sent" after Redis restart | Background workers lost job queue after Redis restart | Manually flushed with `frappe.email.queue.flush()` and restarted workers |

### Result
All outgoing emails now use `info@khandelwalgeneralstores.com` as sender regardless of which user triggers them.

---

## Task 12: Upgrade School Name Fields to Link Type (v1.5.0)

**Request:** "In Purchase Order school section should be fetch from master"

### Problem
The `custom_school_name` field on Purchase Order and Sales Invoice was a **Data** (plain text) field. Users wanted it to be a **Link** field to the `School` DocType so they can select from the School master (dropdown/search).

### Solution

1. Updated `install.py` — PO and SI school fields now use `Link` type with `options: "School"` (guarded by `frappe.db.exists("DocType", "School")`)
2. Updated `api.py` `setup_school_fields()` — Added upgrade logic that **deletes** old Data custom field and **recreates** as Link (Frappe doesn't allow fieldtype change via save)
3. Deployed and ran `setup_school_fields()` on production via `bench execute`

### Verification
All three DocTypes confirmed as Link → School:
```
Sales Order:     fieldtype=Link, options=School
Purchase Order:  fieldtype=Link, options=School
Sales Invoice:   fieldtype=Link, options=School
```

### Files Modified
- `install.py` — Changed PO and SI field definitions from Data to Link
- `api.py` — Added delete-and-recreate upgrade logic in `setup_school_fields()`

---

## Task 13: POS Awesome — Fix Discount System & Add Toggle

**App:** POS Awesome (separate repo: `POS-Awesome-V15-trustbit-2`)
**Request:** "Check carefully in this we have problem with discount not offers (offers is old option)" + "discount not showing in submit form after clicking Pay-> Proceed to pay" + "can we do something switch between old and new one in settings (POS Profile) where user can choose which one to use"

### Background

POS Awesome has **three discount systems**:
1. **Item UOM Discount** (new Trustbit feature) — Auto-applies based on item UOM and quantity tiers, configured per item in `posa_uom_discounts` child table
2. **POS Offers** (old) — Auto/manual offers with types: Item Price, Grand Total, Buy-Get-Free. 11 active offers existed on production (10%, 7%, 20%, 5%, 15%, 12.5%, 50%, 40%, 30%, 28%, 16%)
3. **Manual Item Discount** — Cashier enters discount_percentage or discount_amount directly

Both UOM Discount and POS Offers were running simultaneously, causing conflicts.

### Bug 1: "Offer?" Column Instead of "Discount" Column

**File:** `Invoice.vue`
**Problem:** Items table showed an "Offer?" checkbox column (`posa_is_offer`) instead of showing the actual discount percentage.
**Fix:** Replaced with "Disc%" column displaying `discount_percentage` value.

### Bug 2: UOM Discount Not Recalculated on Repeat Scan

**File:** `Invoice.vue` → `add_item()` method
**Problem:** When the same item was scanned again (quantity incremented), `apply_item_uom_discount()` was only called for NEW items, not for existing items whose quantity changed. This meant quantity-tier discounts wouldn't update.
**Fix:** Added `await this.apply_item_uom_discount(cur_item)` in the existing-item branch of `add_item()`.

### Bug 3: Debug Console.logs Left in Code

**File:** `Invoice.vue` → `calc_prices()` discount_amount handler
**Problem:** 9 `console.log` debug statements left from development.
**Fix:** Removed all 9 statements.

### Bug 4: Discount Not Showing in Payment Screen

**File:** `Payments.vue` → `total_items_discount_amount` computed property
**Problem:** Used `this.items` which **doesn't exist** in Payments.vue scope. Payments.vue receives the invoice data via event bus as `this.invoice_doc`, and items are nested inside `this.invoice_doc.items`.
Also had `!item.posa_is_offer` filter that excluded offer discounts unnecessarily.
**Fix:** Changed `this.items` → `this.invoice_doc?.items` and removed the `posa_is_offer` filter.

### Feature: Discount System Toggle (Offers vs UOM Discount)

**Problem:** Both POS Offers (old) and UOM Discount (new) were running simultaneously. 11 auto-apply POS Offers were conflicting with UOM discounts.
**Solution:** The existing `posa_use_item_uom_discount` checkbox in POS Profile now acts as a **switch** between the two systems:

| Setting | Behavior |
|---------|----------|
| **Checked (ON)** | UOM Discount active, POS Offers **skipped** |
| **Unchecked (OFF)** | POS Offers active, UOM Discounts **skipped** |

**Implementation:** Added guards at the top of `handelOffers()` and `processBuyGetOffers()` in Invoice.vue:
```javascript
if (this.pos_profile && this.pos_profile.posa_use_item_uom_discount) {
  return; // Skip POS Offers when UOM Discount is active
}
```

Both POS Profiles on production ("CASH POS 80mm" and "A4 StandardPrint") have `posa_use_item_uom_discount = 1`, so old offers are now automatically skipped.

### Production Stats
- 6,464 Item UOM Discount records across 17,245 total items
- 11 active POS Offers (all auto-apply) — now skipped when UOM Discount is ON

### Files Modified
- `posawesome/public/js/posapp/components/pos/Invoice.vue` — Bugs 1-3, discount toggle
- `posawesome/public/js/posapp/components/pos/Payments.vue` — Bug 4 (payment screen discount)

### POS Awesome Commit History
```
e46282e Remove temporary debug logging from Payments.vue
469c178 Add temporary debug logging to Payments.vue discount computation
02e3594 Add discount system toggle: skip POS Offers when UOM Discount is active
1b83f0d Fix discount amount not showing in payment screen
cf62fa1 Fix discount display and recalculation in POS
ed72bf2 Fix 15 bugs: SQL injection, logic errors, race conditions, dead code
```

---

## Task 14: POS Awesome — Fix UOM Dropdown Removing Discount & UI Improvements

**App:** POS Awesome (separate repo: `POS-Awesome-V15-trustbit-2`)
**Request:** "new bug when i add item into cart its applies uom discount but when use dropdown its remove the discount" + "can we add something in sales invoice to how much discount given" + "what we do to prevent or not show internal server message if connection loses"

### Bug Fix: UOM Dropdown Removing Applied Discount

**File:** `Invoice.vue` → `update_item_detail()`, `apply_item_uom_discount()`, `calc_uom()`

**Problem:** When user changed the UOM dropdown on an item, the UOM discount was correctly re-applied by `apply_item_uom_discount()` via `calc_prices()`, but then `update_item_detail()` would fire (triggered by Vuetify data table expand events or async callbacks) and unconditionally reset `item.rate = item.price_list_rate`, wiping out the discount. The only existing guard was `!item.posa_offer_applied`, which didn't protect UOM discounts.

**Root Cause Analysis:**
1. `calc_uom()` resets discount → fetches new UOM price → calls `apply_item_uom_discount()`
2. `apply_item_uom_discount()` applies discount via `calc_prices()` and does `this.items = [...this.items]` for Vue reactivity
3. Array reassignment triggers Vuetify's `@update:expanded` → `handleExpandedUpdate()` → schedules `update_item_detail()` via `$nextTick`
4. `update_item_detail()` synchronously resets `item.rate = item.price_list_rate` (line 2352) → **discount wiped out**
5. Its async callback also overwrites `item.rate = data.price_list_rate` (line 2416) → **discount wiped out again**

**Fix (4 changes in `update_item_detail`):**
- Added `!item.posa_uom_discount_applied` guard to synchronous rate reset (line 2351)
- Added same guard to async callback rate overwrite (line 2406)
- Added guard to customer discount section to not override UOM discount (line 2431)
- Added `posa_uom_discount_applied = false` reset in `calc_uom()` before re-applying (clean slate)

### Feature: Sales Invoice Discount Column Visibility

**Problem:** Discount information (price_list_rate, discount_percentage, discount_amount) was saved on Sales Invoice items but not visible in the items table on the form.

**Solution:** Created 3 Property Setters via Frappe REST API to set `in_list_view = 1` on Sales Invoice Item fields:
- `price_list_rate` — shows original price before discount
- `discount_percentage` — shows discount % applied
- `discount_amount` — shows discount amount per item

### Feature: Connection Error Handler (Suppress 502/Internal Server Error Dialogs)

**File:** `posapp.js`

**Problem:** During server restarts or network issues, Frappe's default error handler showed ugly "Internal Server Error" dialog boxes that confused POS users and required manual dismissal.

**Solution:** Added global AJAX error interceptor in `posapp.js`:
- Intercepts HTTP 502, 503, and 0 (network loss) errors
- Shows friendly "Connection lost. Reconnecting..." orange toast
- Auto-retries every 3 seconds (max 30 retries)
- Shows "Connection restored!" green toast when connection returns
- Also patches `frappe.request.report_error` to skip connection errors

### Files Modified
- `posawesome/public/js/posapp/components/pos/Invoice.vue` — UOM discount fix
- `posawesome/public/js/posapp/posapp.js` — Connection error handler

### POS Awesome Commit History (Task 14)
```
bdd1e63 Restore items array reassignment for Vue reactivity on add-item discount
ad21e5e Fix UOM dropdown removing discount: guard update_item_detail from overwriting UOM discount
7afb79e Add connection error handler to suppress Internal Server Error dialogs
```

---

## Complete Commit History

```
84d855a Fix: delete and recreate custom fields to change Data→Link type
8d5db34 Change PO School Name field from Data to Link (School master)
ff70ea1 Reduce footer vertical spacing in PO print format
6edc548 Update PO print format footer to match company standard layout
8f86fda Update work log with Tasks 9-10: wkhtmltopdf fix, Redis watchdog
1927dac Add purchase manager contact info to PO print format header
cbaf919 Harden print format against missing data
71277fb Fix print format error: s_addr undefined when no supplier address
45c871f Add Transport Name field, rename Remark, enhance PO print format
a30360f Update work log with Task 8: School Name field and PO print format
24e6cef Add Rate and Amount columns to KGS Purchase Order print format
a8d4b28 Add setup_school_fields API for remote deployment
ed81015 Add School Name field to SO/PO/Invoice and KGS Purchase Order print format
81e96d0 Add complete project work log with all tasks, bugs, and solutions
dd8335b Allow creating POs for already ordered items
1d33261 Show PO (Supplier Wise) button on all submitted Sales Orders
cfe917a Add Sales Order to Purchase Order (Supplier Wise) feature
91f9ac4 Add Default Supplier field to Book Item Creator
bf69c76 Add comprehensive README, CHANGELOG, and updated technical docs
f12372a Fix bugs, improve security, and harden deployment pipeline
46ceb7a Fix Quick Add: use >= and <= filters instead of between
b5d92df Update Quick Add class groupings to match school structure
86c6d6a Fix deploy: clean stale apps first, handle upstream remote
65ae46d Fix deploy: clean stale backup app references before build
79919a4 Fix deploy: handle first-time app installation
8bc7690 Add GitHub Actions auto-deploy workflow
9446645 Fix 7 bugs: SQL injection, ISBN non-mandatory, background processing
54f5de0 v1.0.0 - Complete bug-free release with all features
3f94ce8 Fix: Added __version__ and renamed app to Trustbit School Book
3c60ec6 Initial commit: Trustbit School Book Seller App v1.0.0
```

---

## Production Server Details

- **Site:** kgs.trustbit.cloud
- **Server:** 82.25.105.136 (Ubuntu 22.04)
- **Bench path:** `/home/frappe_user/frappe-bench`
- **User:** frappe_user
- **Git remote on server:** `upstream` (not `origin`)
- **Redis cache:** port 13000
- **Redis queue:** port 11000
- **Company:** Khandelwal General Stores

## Installed Apps on Server
frappe, erpnext, payments, webshop, india_compliance, hrms, posawesome, trustbit_advance_search, trustbit_barcode, trustbit_school_pro, trustbit_school_book_seller

---

## Completed Previously Pending Items

| Item | Status | Details |
|------|--------|---------|
| Run backfill for default suppliers | Done | 3907 out of 3919 items updated |
| Change server root password | Done | Password changed |
| Investigate Redis crashes | Done | Fixed 3 root causes: `vm.overcommit_memory=1`, Redis queue maxmemory limit, THP disabled. Watchdog cron runs every 1 minute for auto-recovery. |

## Pending / Recommended Actions

_(None at this time — all tasks completed)_
