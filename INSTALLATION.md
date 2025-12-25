# Installation Guide - Trustbit School Book Seller App

## ⚠️ CRITICAL: Read Before Installing

This guide ensures a **bug-free installation**. Follow each step exactly.

---

## Prerequisites

- ERPNext v14 or v15 installed
- Frappe Bench configured
- Git installed
- sudo access

---

## Installation Steps

### Step 1: Navigate to Bench Directory

```bash
cd ~/frappe-bench
```

### Step 2: Get the App from GitHub

```bash
bench get-app https://github.com/zxrrcpandey/trustbit_school_book_seller.git
```

**OR** if you have the local folder:
```bash
# Copy the app folder to apps directory
cp -r /path/to/trustbit_school_book_seller ~/frappe-bench/apps/
```

### Step 3: Install App on Site

```bash
bench --site [your-site-name] install-app trustbit_school_book_seller
```

**Example:**
```bash
bench --site demo.trustbit.cloud install-app trustbit_school_book_seller
```

### Step 4: Run Migration

```bash
bench --site [your-site-name] migrate
```

### Step 5: Build Assets

```bash
bench build --app trustbit_school_book_seller
```

### Step 6: Restart Services

```bash
sudo supervisorctl restart all
```

---

## Verification

After installation, verify:

1. **Check DocTypes exist:**
   - Search "Publication" - should open
   - Search "Subject" - should show 20 pre-loaded subjects
   - Search "Class Master" - should show 15 pre-loaded classes
   - Search "Book Item Creator" - should open

2. **Check Workspace:**
   - Search "School Book Seller" in sidebar
   - Should show workspace with shortcuts

3. **Check Reports:**
   - Search "Book Items Report"
   - Search "Book Creation Summary"

---

## Troubleshooting Common Issues

### Issue 1: "App not found in apps.txt"

**Solution:**
```bash
# Check the CORRECT apps.txt file
cat ~/frappe-bench/sites/apps.txt

# If app not listed, add it:
echo "trustbit_school_book_seller" >> ~/frappe-bench/sites/apps.txt

# Then install
bench --site [your-site] install-app trustbit_school_book_seller
```

### Issue 2: "Module not found"

**Solution:**
```bash
# Run migrate
bench --site [your-site] migrate

# Clear cache
bench --site [your-site] clear-cache

# Restart
sudo supervisorctl restart all
```

### Issue 3: Custom fields not appearing on Item

**Solution:**
```bash
# Run the after_install function manually
bench --site [your-site] console
```

Then in console:
```python
from trustbit_school_book_seller.install import after_install
after_install()
```

### Issue 4: JavaScript not loading

**Solution:**
```bash
# Rebuild assets
bench build --app trustbit_school_book_seller --force

# Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)

# Restart
sudo supervisorctl restart all
```

---

## Uninstallation

If you need to remove the app:

```bash
bench --site [your-site] uninstall-app trustbit_school_book_seller
bench remove-app trustbit_school_book_seller
```

---

## Support

For issues, contact: info@trustbit.in

---

## Version History

- **v1.0.0** - Initial release with all features
  - Bulk item creation
  - Progress dialog
  - Import/Export
  - Reports
  - Workspace
