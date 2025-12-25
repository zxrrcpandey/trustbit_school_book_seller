# Trustbit School Book Seller App

Advanced Item Creation System for School Book Shops built on ERPNext.

## Overview

This app provides a streamlined bulk item creation system specifically designed for school book shops. It allows you to create multiple book items for different classes in a single transaction, with automatic price list integration, stock opening entries, and comprehensive progress tracking.

## Features

### Core Features
- **Bulk Item Creation**: Create items for multiple classes in one go
- **Master Data Management**: Publication, Subject, and Class Master
- **Quick Add Classes**: One-click buttons to add classes (Primary, Middle, Senior, All)
- **Duplicate ISBN Detection**: Prevents duplicate ISBN/Barcode entries
- **Progress Tracking**: Real-time progress bar with detailed creation log

### Automated Processes
- **Price List Integration**: Auto-creates entries in Selling and Buying Price Lists
- **Stock Opening Entry**: Automatic Material Receipt stock entry for opening stock
- **Item Group Mapping**: Consistent item group assignment
- **HSN/SAC Code**: GST compliance with HSN code support

### Additional Features
- Edition and Publication Year tracking
- Valuation Rate for accurate costing
- Retry mechanism for failed items
- Linked document navigation

## Installation

### Prerequisites
- ERPNext v14 or later
- Frappe Framework v14 or later

### Install via Bench

```bash
# Navigate to your bench directory
cd /path/to/frappe-bench

# Get the app
bench get-app https://github.com/your-repo/trustbit_school_book_seller.git

# Install on your site
bench --site your-site.local install-app trustbit_school_book_seller

# Run migrations
bench --site your-site.local migrate

# Clear cache
bench --site your-site.local clear-cache

# Restart bench
bench restart
```

### Manual Installation

1. Clone the repository into the `apps` folder:
```bash
cd /path/to/frappe-bench/apps
git clone https://github.com/your-repo/trustbit_school_book_seller.git
```

2. Install the app:
```bash
bench --site your-site.local install-app trustbit_school_book_seller
```

## Usage

### Step 1: Setup Masters

#### Publication Master
Navigate to **Trustbit School Book Seller > Publication**
- Add book publishers (NCERT, Oxford, Cambridge, etc.)
- Set short codes for reference
- Optionally link default supplier

#### Subject Master
Navigate to **Trustbit School Book Seller > Subject**
- Pre-populated with common subjects
- Add custom subjects as needed

#### Class Master
Navigate to **Trustbit School Book Seller > Class Master**
- Pre-populated with Nursery, LKG, UKG, Class 1-12
- Add custom classes if needed

### Step 2: Create Book Items

1. Navigate to **Trustbit School Book Seller > Book Item Creator**
2. Click **+ Add Book Item Creator**

#### Fill Header Details
| Field | Description |
|-------|-------------|
| Publication | Select book publisher |
| Subject | Select subject |
| Book Name | Enter book title |
| Author | Optional author name |
| Edition | Book edition |
| Publication Year | Year of publication |
| UOM | Unit of Measure (default: Nos) |

#### Discount & Pricing
| Field | Description |
|-------|-------------|
| Sales Discount % | Discount for customers |
| Purchase Discount % | Discount from supplier |
| Selling Price List | Select selling price list |
| Buying Price List | Select buying price list |

#### Item Configuration
| Field | Description |
|-------|-------------|
| Item Group | Category for items |
| Default Warehouse | Warehouse for stock |
| HSN/SAC Code | GST HSN code |

### Step 3: Add Class Details

#### Using Quick Add
Click on the **Quick Add Classes** dropdown:
- **All Classes (1-12)**: Adds Nursery through Class 12
- **Primary (Nursery-5)**: Adds Nursery, LKG, UKG, Class 1-5
- **Middle (6-10)**: Adds Class 6-10
- **Senior (11-12)**: Adds Class 11-12

#### Manual Entry
Add rows manually and fill:
| Field | Description |
|-------|-------------|
| Class | Select class |
| Selling Rate | Price for customers |
| Valuation Rate | Cost/Purchase price |
| ISBN/Barcode | Unique ISBN or barcode |
| Opening Stock | Initial stock quantity |

### Step 4: Submit

1. Review all details
2. Click **Submit**
3. Watch the progress bar as items are created
4. Check the Creation Log for detailed status

## Generated Items

Each class detail row creates an Item with:

- **Item Code**: Auto-generated (BOOK-00001, BOOK-00002, etc.)
- **Item Name**: `{Publication} {Book Name} {Class}`
- **Barcode**: ISBN/Barcode from class detail
- **Custom Fields**: Publication, Subject, Class, Author, Edition, Year, Discounts

## Troubleshooting

### Failed Items
If some items fail during creation:
1. Check the Creation Log for error messages
2. Click **Actions > Retry Failed Items**
3. Review and fix any issues
4. Retry again if needed

### Duplicate ISBN Error
The system prevents duplicate ISBNs:
- Check existing items for the ISBN
- Use a different ISBN
- Or delete the existing item first

### Price List Not Found
Ensure price lists exist:
- Standard Selling (for selling prices)
- Standard Buying (for buying prices)

## Technical Details

### Doctypes

| Doctype | Type | Purpose |
|---------|------|---------|
| Publication | Master | Book publishers |
| Subject | Master | Academic subjects |
| Class Master | Master | School classes |
| Book Item Creator | Transaction | Main bulk creation |
| Book Class Detail | Child Table | Class-wise details |
| Book Creation Log | Child Table | Creation log |

### Custom Fields on Item

| Field | Type | Description |
|-------|------|-------------|
| custom_publication | Link | Publisher reference |
| custom_subject | Link | Subject reference |
| custom_class | Link | Class reference |
| custom_author | Data | Author name |
| custom_edition | Data | Book edition |
| custom_publication_year | Data | Publication year |
| custom_isbn_barcode | Data | ISBN/Barcode (unique) |
| custom_sales_discount_percent | Percent | Sales discount |
| custom_purchase_discount_percent | Percent | Purchase discount |
| custom_book_item_creator | Link | Source document |

### Permissions

| Role | Permissions |
|------|-------------|
| System Manager | Full access |
| Stock Manager | Full access |
| Stock User | Create, Read, Write, Submit |

## Changelog

### Version 1.0.0
- Initial release
- Bulk item creation
- Quick Add Classes feature
- Progress bar with real-time updates
- Duplicate ISBN detection
- Price list integration
- Opening stock entry
- Edition/Year tracking

## Support

For issues and feature requests, please contact:
- Email: support@trustbit.com
- GitHub Issues: [Repository Issues Page]

## License

MIT License - See LICENSE file for details.
