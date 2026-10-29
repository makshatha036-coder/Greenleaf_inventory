from datetime import date, timedelta

import pytest

import models
import reports
from conftest import login
from database import get_db
from utils import ValidationError

GOOD = {"name": "Milk 1L", "category": "Dairy", "unit_price": "50", "stock_qty": "20", "reorder_level": "5"}


def add(app_ctx_data=None, **over):
    data = {**GOOD, **over}
    return models.add_product(data)


# ---------- login ----------
def test_login_success_and_wrong_password(client):
    assert b"Welcome, admin" in login(client).data
    client.get("/logout")
    assert b"Wrong username or password" in login(client, password="nope").data


def test_password_is_hashed(app):
    with app.app_context():
        row = get_db().execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()
        assert row["password_hash"] != "admin123" and len(row["password_hash"]) > 30


def test_cashier_cannot_open_admin_pages(client):
    login(client, "cashier", "cashier123")
    for url in ("/products", "/reports"):
        r = client.get(url)
        assert r.status_code == 302 and "/dashboard" in r.headers["Location"]
    assert client.get("/billing").status_code == 200


def test_anonymous_redirected_to_login(client):
    r = client.get("/products")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


# ---------- product validation ----------
def test_add_product_valid(app):
    with app.app_context():
        pid = add()
        assert models.get_product(pid)["name"] == "Milk 1L"


@pytest.mark.parametrize("field,value", [("unit_price", "-5"), ("stock_qty", "-1"), ("stock_qty", "abc"),
                                         ("name", "   "), ("expiry_date", "2026-13-45"), ("reorder_level", "-2")])
def test_product_validation_rejects_bad_input(app, field, value):
    with app.app_context(), pytest.raises(ValidationError):
        add(**{field: value})


def test_duplicate_product_name_rejected(app):
    with app.app_context():
        add()
        with pytest.raises(ValidationError):
            add(name="milk 1l")


def test_search_products(app):
    with app.app_context():
        add(); add(name="Bread", category="Bakery")
        assert [p["name"] for p in models.list_products("bre")] == ["Bread"]
        assert len(models.list_products(category="Dairy")) == 1


# ---------- billing ----------
def test_bill_deducts_stock_and_applies_discount(app):
    with app.app_context():
        pid = add()
        sid = models.create_bill(1, [(pid, "4")], discount_percent=10)
        sale, items = models.get_sale(sid)
        assert sale["subtotal"] == 200 and sale["total_amount"] == 180
        assert models.get_product(pid)["stock_qty"] == 16 and len(items) == 1


def test_cannot_sell_more_than_stock(app):
    with app.app_context():
        pid = add(stock_qty="3")
        with pytest.raises(ValidationError, match="Not enough stock"):
            models.create_bill(1, [(pid, "4")])
        assert models.get_product(pid)["stock_qty"] == 3


@pytest.mark.parametrize("qty", ["-1", "0", "abc", "1.5"])
def test_bad_quantities_rejected(app, qty):
    with app.app_context():
        pid = add()
        with pytest.raises(ValidationError):
            models.create_bill(1, [(pid, qty)])


def test_empty_bill_and_bad_discount_rejected(app):
    with app.app_context():
        pid = add()
        with pytest.raises(ValidationError):
            models.create_bill(1, [])
        with pytest.raises(ValidationError):
            models.create_bill(1, [(pid, "1")], discount_percent=150)


def test_failed_bill_changes_nothing(app):
    with app.app_context():
        a, b = add(), add(name="Curd", stock_qty="1")
        with pytest.raises(ValidationError):
            models.create_bill(1, [(a, "2"), (b, "5")])
        assert models.get_product(a)["stock_qty"] == 20
        assert get_db().execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0


def test_expired_product_cannot_be_sold(app):
    with app.app_context():
        pid = add(expiry_date=(date.today() - timedelta(days=1)).isoformat())
        with pytest.raises(ValidationError, match="expired"):
            models.create_bill(1, [(pid, "1")])


def test_duplicate_lines_are_merged(app):
    with app.app_context():
        pid = add()
        sid = models.create_bill(1, [(pid, "2"), (pid, "3")])
        assert models.get_sale(sid)[0]["subtotal"] == 250
        assert models.get_product(pid)["stock_qty"] == 15


def test_product_with_sales_cannot_be_deleted(app):
    with app.app_context():
        pid = add()
        models.create_bill(1, [(pid, "1")])
        with pytest.raises(ValidationError):
            models.delete_product(pid)
        other = add(name="Unsold")
        models.delete_product(other)
        assert models.get_product(other) is None


# ---------- CSV ----------
def test_csv_import_reports_bad_rows(app):
    csv_text = ("name,category,unit_price,stock_qty\nTea,Beverages,120,10\n"
                "Bad,Beverages,-3,10\nCoffee,Beverages,200,abc\n")
    with app.app_context():
        added, errors = models.import_products_csv(csv_text)
        assert added == 1 and len(errors) == 2 and "Row 3" in errors[0]
        with pytest.raises(ValidationError):
            models.import_products_csv("foo,bar\n1,2\n")


# ---------- reports & routes ----------
def test_reports_and_kpis(app):
    with app.app_context():
        pid = add(stock_qty="10", reorder_level="10")
        models.create_bill(1, [(pid, "2")])
        today = date.today().isoformat()
        k = reports.kpis(today, today)
        assert k["total_revenue"] == 100 and k["bills"] == 1 and k["avg_bill"] == 100
        assert k["low_stock_count"] == 1 and k["top_category"] == "Dairy"
        assert reports.top_products(today, today).iloc[0]["name"] == "Milk 1L"


def test_end_to_end_billing_and_pages(client, app):
    with app.app_context():
        pid = add()
    login(client)
    r = client.post("/billing", data={"product_id": [str(pid)], "quantity": ["2"], "discount": "0"},
                    follow_redirects=True)
    assert b"Bill created" in r.data
    r = client.post("/billing", data={"product_id": [str(pid)], "quantity": ["999"]})
    assert b"Not enough stock" in r.data
    for url in ("/dashboard", "/products", "/reports", "/bills", "/bills/1/csv", "/products/export",
                "/reports/export/daily", "/reports?start=bad-date"):
        assert client.get(url).status_code == 200, url
    assert client.get("/bills/999").status_code == 404
    assert client.get("/reports/export/nope").status_code == 404


# ---------- extra: suppliers, users, permissions, hashing ----------
def test_supplier_validation_and_add(app):
    with app.app_context():
        models.add_supplier("Fresh Farms", "98765 43210", "a@b.com")
        assert len(models.suppliers()) == 1
        for bad in [("", "", ""), ("X", "abc", ""), ("X", "", "not-an-email")]:
            with pytest.raises(ValidationError):
                models.add_supplier(*bad)


def test_create_user_rules(app):
    with app.app_context():
        models.create_user("sam", "pass1234", "cashier")
        assert models.authenticate("sam", "pass1234") is not None
        assert models.authenticate("sam", "wrong") is None
        for bad in [("sam", "pass1234", "cashier"), ("x", "1", "cashier"), ("y", "pass1234", "boss")]:
            with pytest.raises(ValidationError):
                models.create_user(*bad)


def test_admin_pages_for_suppliers_users_and_import(client, app):
    login(client)
    assert b"Supplier added" in client.post("/suppliers", data={"name": "Metro"}, follow_redirects=True).data
    assert b"User created" in client.post("/users", data={"username": "ravi", "password": "abcd", "role": "cashier"},
                                          follow_redirects=True).data
    import io
    csv_bytes = b"name,category,unit_price,stock_qty\nTea,Beverages,10,5\nBad,Beverages,-1,5\n"
    r = client.post("/products/import", data={"file": (io.BytesIO(csv_bytes), "p.csv")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Imported 1 product" in r.data and b"Row 3" in r.data


def test_cashier_sees_only_own_bills(client, app):
    with app.app_context():
        pid = add()
        admin_sale = models.create_bill(1, [(pid, "1")])      # user 1 = admin
    login(client, "cashier", "cashier123")
    assert client.get(f"/bills/{admin_sale}").status_code == 404
    assert client.get("/suppliers").status_code == 302


def test_password_hash_method_is_portable(app):
    with app.app_context():
        h = get_db().execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
        assert h.startswith("pbkdf2:sha256")
