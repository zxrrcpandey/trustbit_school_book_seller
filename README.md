# Trustbit School Book Seller

A custom ERPNext application for school book sellers to manage bulk book item creation with class-wise pricing, ISBN tracking, and automated stock management.

**Production:** kgs.trustbit.cloud
**License:** MIT
**Compatibility:** ERPNext v14 / v15
**Python:** >= 3.10

---

## Table of Contents

- [Features](#features)
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

### 15. Workspace
A dedicated **"School Book Seller"** workspace with:
- Quick shortcuts to Book Item Creator, Publication, Class Master, Subject
- Links to both reports
- Organized navigation for all app features

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

### Permissions

| Role | Book Item Creator | Publication / Subject / Class Master |
|------|-------------------|--------------------------------------|
| **System Manager** | Full access (create, read, write, submit, cancel, amend, delete) | Full access |
| **Stock Manager** | Full access | Full access |
| **Stock User** | Full access | Create, read, write, export, print (no delete) |

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

---

## Custom Fields on Item

The app adds 12 custom fields to the standard ERPNext **Item** doctype:

| Field | Type | Section | Options |
|-------|------|---------|---------|
| `custom_book_details_section` | Section Break | Book Details | Collapsible |
| `custom_publication` | Link | Book Details | Publication |
| `custom_subject` | Link | Book Details | Subject |
| `custom_class` | Link | Book Details | Class Master |
| `custom_author` | Data | Book Details | — |
| `custom_edition` | Data | Book Details | — |
| `custom_publication_year` | Data | Book Details | — |
| `custom_isbn_barcode` | Data (unique) | Book Details | DB unique constraint |
| `custom_discount_section` | Section Break | Discount | Collapsible |
| `custom_sales_discount_percent` | Percent | Discount | — |
| `custom_purchase_discount_percent` | Percent | Discount | — |
| `custom_book_item_creator` | Link (read-only) | Discount | Book Item Creator |

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
| **Realtime Event** | `book_item_creation_progress` |
| **Barcode Type** | Empty string (accepts any format) |
| **Fixtures** | Subject, Class Master, Custom Field (exported via `bench export-fixtures`) |
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
    ├── modules.txt
    ├── patches.txt
    ├── fixtures/
    │   ├── class_master.json           # 15 default classes
    │   └── subject.json                # 20 default subjects
    ├── public/js/
    │   └── book_item_creator.js        # Client-side logic (649 lines)
    └── trustbit_school_book/
        ├── doctype/
        │   ├── book_item_creator/      # Main transaction DocType
        │   ├── book_class_detail/      # Child table for class rows
        │   ├── book_creation_log/      # Child table (reserved)
        │   ├── publication/            # Publisher master
        │   ├── subject/                # Subject master
        │   └── class_master/           # Class/Grade master
        ├── report/
        │   ├── book_creation_summary/  # Summary report
        │   └── book_items_report/      # Items report
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

### JavaScript not loading
```bash
bench build --app trustbit_school_book_seller --force
sudo supervisorctl restart all
# Clear browser cache: Ctrl+Shift+R (or Cmd+Shift+R on Mac)
```

### App not found in apps.txt
```bash
cat ~/frappe-bench/sites/apps.txt
echo "trustbit_school_book_seller" >> ~/frappe-bench/sites/apps.txt
bench --site [your-site] install-app trustbit_school_book_seller
```

### Module not found error
```bash
bench --site [your-site] migrate
bench --site [your-site] clear-cache
sudo supervisorctl restart all
```

### Uninstallation
```bash
bench --site [your-site] uninstall-app trustbit_school_book_seller
bench remove-app trustbit_school_book_seller
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

---

## License

MIT License - see [LICENSE](LICENSE)

## Author

**Trustbit** - info@trustbit.in
