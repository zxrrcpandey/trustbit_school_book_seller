# Trustbit School Book Seller

A custom ERPNext application for school book sellers to manage bulk book item creation with class-wise pricing, ISBN tracking, and stock management.

## Features

### Core Features
- **Bulk Item Creation**: Create multiple book items for different classes in one go
- **Auto-naming**: Items named as `{Publication} {Book Name} {Class}`
- **Price List Integration**: Auto-creates selling and buying price entries
- **Stock Management**: Creates opening stock entries automatically
- **Barcode Support**: ISBN/Barcode tracking for each book variant

### Quick Add Classes
- All Classes (15 classes at once)
- Primary (Nursery to Class 5)
- Middle (Class 6 to 10)
- Senior (Class 11-12)

### Real-Time Progress
- Beautiful progress dialog during item creation
- Live updates with success/failure counts
- Color-coded progress bar

### Import/Export
- Export created items to Excel/CSV
- Import class details from CSV
- Download CSV template

### Reports
- **Book Items Report**: All created book items with stock details
- **Book Creation Summary**: Entry-wise summary with success rates

### Workspace
- Dedicated "School Book Seller" workspace
- Quick shortcuts to all features

## Installation

### Prerequisites
- ERPNext v14 or v15
- Frappe Bench

### Install Steps

```bash
# Get the app
bench get-app https://github.com/zxrrcpandey/trustbit_school_book_seller.git

# Install on your site
bench --site [your-site] install-app trustbit_school_book_seller

# Run migrations
bench --site [your-site] migrate

# Build assets
bench build --app trustbit_school_book_seller

# Restart
sudo supervisorctl restart all
```

## Pre-loaded Data

### Classes (15)
Nursery, LKG, UKG, Class 1, Class 2, Class 3, Class 4, Class 5, Class 6, Class 7, Class 8, Class 9, Class 10, Class 11, Class 12

### Subjects (20)
Mathematics, English, Hindi, Science, Social Science, Physics, Chemistry, Biology, Computer Science, Economics, Accountancy, Business Studies, Geography, History, Political Science, Sanskrit, Physical Education, Art & Craft, Music, General Knowledge

## Usage

1. **Create Publication** (if new): Search "Publication" → New → Save
2. **Create Book Item Creator**: Search "Book Item Creator" → New
3. **Fill Details**: Publication, Subject, Book Name, Author, etc.
4. **Add Classes**: Use "Quick Add Classes" or add manually
5. **Enter Rates & ISBN**: For each class row
6. **Submit**: Click "Submit & Create Items" and watch progress

## DocTypes

| DocType | Type | Purpose |
|---------|------|---------|
| Publication | Master | Publisher information |
| Subject | Master | Subject names |
| Class Master | Master | Class/Grade names |
| Book Item Creator | Transaction | Bulk item creation form |
| Book Class Detail | Child Table | Class-wise details |
| Book Creation Log | Child Table | Audit trail |

## Custom Fields on Item

- Publication, Subject, Class
- Author, Edition, Publication Year
- ISBN/Barcode
- Sales/Purchase Discount %
- Book Item Creator reference

## License

MIT License

## Author

Trustbit - info@trustbit.in
