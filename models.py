"""Data-access and business logic: users, products, billing."""
import csv
import io
import sqlite3
from datetime import date, datetime

from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db
from utils import ValidationError, validate_product


# ---------- users ----------
def create_user(username, password, role="cashier"):
    username = (username or "").strip()
    if not username:
        raise ValidationError("Username is required.")
    if len(password or "") < 4:
        raise ValidationError("Password must be at least 4 characters.")
    if role not in ("admin", "cashier"):
        raise ValidationError("Role must be admin or cashier.")
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password, method="pbkdf2:sha256"), role),
        )
        db.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValidationError("That username already exists.")


def authenticate(username, password):
    row = get_db().execute(
        "SELECT * FROM users WHERE username = ?", ((username or "").strip(),)
    ).fetchone()
    if row and check_password_hash(row["password_hash"], password or ""):
        return row
    return None


def ensure_default_users():
    """Create demo accounts on first run."""
    if get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        create_user("admin", "admin123", "admin")
        create_user("cashier", "cashier123", "cashier")


# ---------- products ----------
def list_products(search="", category=""):
    sql = ("SELECT p.*, s.name AS supplier_name FROM products p "
           "LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id WHERE 1=1")
    params = []
    if search:
        sql += " AND (p.name LIKE ? OR p.category LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if category:
        sql += " AND p.category = ?"
        params.append(category)
    return get_db().execute(sql + " ORDER BY p.name", params).fetchall()


def get_product(product_id):
    return get_db().execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()


def categories():
    rows = get_db().execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    return [r["category"] for r in rows]


def suppliers():
    return get_db().execute("SELECT * FROM suppliers ORDER BY name").fetchall()


def _name_taken(name, exclude_id=None):
    row = get_db().execute(
        "SELECT product_id FROM products WHERE LOWER(name) = LOWER(?) AND product_id != ?",
        (name, exclude_id or -1),
    ).fetchone()
    return row is not None


def add_product(data):
    c = validate_product(data)
    if _name_taken(c["name"]):
        raise ValidationError(f"A product named '{c['name']}' already exists.")
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO products (name, category, unit_price, stock_qty, reorder_level, expiry_date, supplier_id) "
            "VALUES (:name, :category, :unit_price, :stock_qty, :reorder_level, :expiry_date, :supplier_id)", c)
        db.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        db.rollback()
        raise ValidationError("Could not save the product. Check the supplier and values.")


def update_product(product_id, data):
    if get_product(product_id) is None:
        raise ValidationError("Product not found.")
    c = validate_product(data)
    if _name_taken(c["name"], product_id):
        raise ValidationError(f"A product named '{c['name']}' already exists.")
    c["product_id"] = product_id
    db = get_db()
    try:
        db.execute(
            "UPDATE products SET name=:name, category=:category, unit_price=:unit_price, stock_qty=:stock_qty, "
            "reorder_level=:reorder_level, expiry_date=:expiry_date, supplier_id=:supplier_id "
            "WHERE product_id=:product_id", c)
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise ValidationError("Could not update the product. Check the supplier and values.")


def delete_product(product_id):
    if get_product(product_id) is None:
        raise ValidationError("Product not found.")
    db = get_db()
    used = db.execute("SELECT COUNT(*) FROM sale_items WHERE product_id = ?", (product_id,)).fetchone()[0]
    if used:
        raise ValidationError(
            "This product has sales history and cannot be deleted. Set its stock to 0 instead.")
    db.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
    db.commit()


def import_products_csv(text):
    """Import products from CSV text. Returns (added_count, error_messages)."""
    reader = csv.DictReader(io.StringIO(text))
    required = {"name", "category", "unit_price", "stock_qty"}
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if not required <= headers:
        raise ValidationError("CSV must have columns: name, category, unit_price, stock_qty "
                              "(optional: reorder_level, expiry_date, supplier_id).")
    added, errors = 0, []
    for line_no, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            add_product(row)
            added += 1
        except ValidationError as e:
            errors.append(f"Row {line_no}: " + " ".join(e.errors))
    return added, errors


# ---------- billing ----------
def create_bill(user_id, items, discount_percent=0, now=None):
    """Create a sale and deduct stock atomically.

    items: iterable of (product_id, quantity) raw values (strings are fine).
    Returns the new sale_id or raises ValidationError.
    """
    errors, wanted = [], {}
    for pid, qty in items:
        if str(pid).strip() == "" and str(qty).strip() == "":
            continue  # empty row
        try:
            pid, qty = int(pid), int(str(qty).strip())
        except (ValueError, TypeError):
            errors.append("Every bill line needs a product and a whole-number quantity.")
            continue
        if qty <= 0:
            errors.append("Quantity must be greater than zero.")
            continue
        wanted[pid] = wanted.get(pid, 0) + qty

    try:
        disc = float(str(discount_percent).strip() or 0)
        if not 0 <= disc <= 100 or disc != disc:
            raise ValueError
    except ValueError:
        errors.append("Discount must be a number between 0 and 100.")
        disc = 0
    if not wanted and not errors:
        errors.append("Add at least one item to the bill.")
    if errors:
        raise ValidationError(sorted(set(errors)))

    db = get_db()
    now = now or datetime.now()
    today = now.date().isoformat()
    lines, subtotal = [], 0.0
    for pid, qty in wanted.items():
        p = get_product(pid)
        if p is None:
            errors.append(f"Product #{pid} does not exist.")
        elif p["expiry_date"] and p["expiry_date"] < today:
            errors.append(f"{p['name']} is expired and cannot be sold.")
        elif qty > p["stock_qty"]:
            errors.append(f"Not enough stock for {p['name']}: requested {qty}, available {p['stock_qty']}.")
        else:
            lines.append((p["product_id"], qty, p["unit_price"]))
            subtotal += qty * p["unit_price"]
    if errors:
        raise ValidationError(errors)

    subtotal = round(subtotal, 2)
    total = round(subtotal * (1 - disc / 100), 2)
    try:
        cur = db.execute(
            "INSERT INTO sales (sale_date, sale_time, user_id, subtotal, discount_percent, total_amount) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (today, now.strftime("%H:%M:%S"), user_id, subtotal, disc, total))
        sale_id = cur.lastrowid
        for pid, qty, price in lines:
            db.execute("INSERT INTO sale_items (sale_id, product_id, quantity, price) VALUES (?, ?, ?, ?)",
                       (sale_id, pid, qty, price))
            res = db.execute(
                "UPDATE products SET stock_qty = stock_qty - ? WHERE product_id = ? AND stock_qty >= ?",
                (qty, pid, qty))
            if res.rowcount != 1:  # someone else bought it meanwhile
                raise ValidationError("Stock changed while billing. Please try again.")
        db.commit()
        return sale_id
    except ValidationError:
        db.rollback()
        raise
    except sqlite3.Error:
        db.rollback()
        raise ValidationError("Could not save the bill. Nothing was changed.")


def get_sale(sale_id):
    db = get_db()
    sale = db.execute(
        "SELECT s.*, u.username FROM sales s JOIN users u ON u.user_id = s.user_id WHERE s.sale_id = ?",
        (sale_id,)).fetchone()
    if sale is None:
        return None, []
    items = db.execute(
        "SELECT si.*, p.name, si.quantity * si.price AS line_total FROM sale_items si "
        "JOIN products p ON p.product_id = si.product_id WHERE si.sale_id = ?", (sale_id,)).fetchall()
    return sale, items


def recent_sales(user_id=None, limit=50):
    sql = ("SELECT s.*, u.username FROM sales s JOIN users u ON u.user_id = s.user_id")
    params = []
    if user_id:
        sql += " WHERE s.user_id = ?"
        params.append(user_id)
    sql += " ORDER BY s.sale_date DESC, s.sale_time DESC, s.sale_id DESC LIMIT ?"
    params.append(limit)
    return get_db().execute(sql, params).fetchall()


# ---------- users (admin screen) ----------
def list_users():
    return get_db().execute("SELECT user_id, username, role FROM users ORDER BY username").fetchall()


# ---------- suppliers ----------
def add_supplier(name, phone="", email=""):
    name, phone, email = (name or "").strip(), (phone or "").strip(), (email or "").strip()
    errors = []
    if not name:
        errors.append("Supplier name is required.")
    if phone and not phone.replace("+", "").replace("-", "").replace(" ", "").isdigit():
        errors.append("Phone may contain only digits, spaces, + and -.")
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        errors.append("Enter a valid email address.")
    if errors:
        raise ValidationError(errors)
    db = get_db()
    cur = db.execute("INSERT INTO suppliers (name, phone, email) VALUES (?, ?, ?)", (name, phone or None, email or None))
    db.commit()
    return cur.lastrowid


def delete_supplier(supplier_id):
    db = get_db()
    db.execute("DELETE FROM suppliers WHERE supplier_id = ?", (supplier_id,))  # products keep existing (SET NULL)
    db.commit()
