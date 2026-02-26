# Trustbit School Book Seller - Complete Project Work Log

## Project Overview

**App:** Trustbit School Book Seller (ERPNext custom app)
**GitHub:** https://github.com/zxrrcpandey/trustbit_school_book_seller
**Production:** kgs.trustbit.cloud (82.25.105.136)
**Work Period:** February 2026
**Starting Version:** 1.0.0 | **Final Version:** 1.2.0

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

## Complete Commit History

```
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

## Pending / Recommended Actions

1. **Run backfill** to set default suppliers for existing 277 items:
   ```
   bench --site kgs.trustbit.cloud console
   >>> frappe.call("trustbit_school_book_seller.api.backfill_item_default_suppliers")
   ```
2. **Configure GitHub Secrets** for automated deployment: `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`
3. **Add server SSH public key** to `/root/.ssh/authorized_keys`
4. **Change server root password** (was shared in conversation)
