# Test report

Generated: 2026-10-26 14:12

**Result:** 32 passed in 90.63s (0:01:30)

Tests use a separate temporary SQLite database, never `greenleaf.db`.

| Test | Result |
|---|---|
| `test_login_success_and_wrong_password` | PASSED |
| `test_password_is_hashed` | PASSED |
| `test_cashier_cannot_open_admin_pages` | PASSED |
| `test_anonymous_redirected_to_login` | PASSED |
| `test_add_product_valid` | PASSED |
| `test_product_validation_rejects_bad_input[unit_price--5]` | PASSED |
| `test_product_validation_rejects_bad_input[stock_qty--1]` | PASSED |
| `test_product_validation_rejects_bad_input[stock_qty-abc]` | PASSED |
| `test_product_validation_rejects_bad_input[name-` | PASSED |
| `test_product_validation_rejects_bad_input[expiry_date-2026-13-45]` | PASSED |
| `test_product_validation_rejects_bad_input[reorder_level--2]` | PASSED |
| `test_duplicate_product_name_rejected` | PASSED |
| `test_search_products` | PASSED |
| `test_bill_deducts_stock_and_applies_discount` | PASSED |
| `test_cannot_sell_more_than_stock` | PASSED |
| `test_bad_quantities_rejected[-1]` | PASSED |
| `test_bad_quantities_rejected[0]` | PASSED |
| `test_bad_quantities_rejected[abc]` | PASSED |
| `test_bad_quantities_rejected[1.5]` | PASSED |
| `test_empty_bill_and_bad_discount_rejected` | PASSED |
| `test_failed_bill_changes_nothing` | PASSED |
| `test_expired_product_cannot_be_sold` | PASSED |
| `test_duplicate_lines_are_merged` | PASSED |
| `test_product_with_sales_cannot_be_deleted` | PASSED |
| `test_csv_import_reports_bad_rows` | PASSED |
| `test_reports_and_kpis` | PASSED |
| `test_end_to_end_billing_and_pages` | PASSED |
| `test_supplier_validation_and_add` | PASSED |
| `test_create_user_rules` | PASSED |
| `test_admin_pages_for_suppliers_users_and_import` | PASSED |
| `test_cashier_sees_only_own_bills` | PASSED |
| `test_password_hash_method_is_portable` | PASSED |
