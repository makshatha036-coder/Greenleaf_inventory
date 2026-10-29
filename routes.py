"""All web routes (one Blueprint)."""
import csv
import io
from datetime import date, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, session, url_for)

import models
import reports
from database import get_db
from utils import (ValidationError, csv_response, login_required, parse_date,
                   role_required)

bp = Blueprint("main", __name__)


def _flash_errors(exc):
    for msg in exc.errors:
        flash(msg, "error")


# ---------- auth ----------
@bp.route("/")
def index():
    return redirect(url_for("main.dashboard" if "user_id" in session else "main.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = models.authenticate(request.form.get("username"), request.form.get("password"))
        if user:
            session.clear()
            session.update(user_id=user["user_id"], username=user["username"], role=user["role"])
            return redirect(url_for("main.dashboard"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "ok")
    return redirect(url_for("main.login"))


# ---------- dashboard ----------
@bp.route("/dashboard")
@login_required
def dashboard():
    if session["role"] != "admin":
        return render_template("dashboard.html", kpis=None, low=[], expiry=[])
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=30)).isoformat()
    days = current_app.config["NEAR_EXPIRY_DAYS"]
    return render_template(
        "dashboard.html", kpis=reports.kpis(start, end), start=start, end=end,
        low=reports.low_stock().to_dict("records"),
        expiry=reports.expiring(days).to_dict("records"), days=days)


# ---------- products ----------
@bp.route("/products")
@role_required("admin")
def products():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "")
    today = date.today()
    soon = today + timedelta(days=current_app.config["NEAR_EXPIRY_DAYS"])
    return render_template(
        "products.html", products=models.list_products(q, cat), categories=models.categories(),
        q=q, category=cat, today=today.isoformat(), soon=soon.isoformat())


def _product_form(product_id=None):
    product = models.get_product(product_id) if product_id else None
    if product_id and product is None:
        flash("Product not found.", "error")
        return redirect(url_for("main.products"))
    values = dict(product) if product else {}
    if request.method == "POST":
        values = request.form.to_dict()
        try:
            if product_id:
                models.update_product(product_id, values)
                flash("Product updated.", "ok")
            else:
                models.add_product(values)
                flash("Product added.", "ok")
            return redirect(url_for("main.products"))
        except ValidationError as e:
            _flash_errors(e)
    return render_template("product_form.html", p=values, editing=bool(product_id),
                           suppliers=models.suppliers(), categories=models.categories())


@bp.route("/products/add", methods=["GET", "POST"])
@role_required("admin")
def product_add():
    return _product_form()


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def product_edit(product_id):
    return _product_form(product_id)


@bp.route("/products/<int:product_id>/delete", methods=["POST"])
@role_required("admin")
def product_delete(product_id):
    try:
        models.delete_product(product_id)
        flash("Product deleted.", "ok")
    except ValidationError as e:
        _flash_errors(e)
    return redirect(url_for("main.products"))


@bp.route("/products/import", methods=["POST"])
@role_required("admin")
def products_import():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a CSV file to import.", "error")
        return redirect(url_for("main.products"))
    try:
        text = f.read(current_app.config["MAX_UPLOAD_BYTES"] + 1)
        if len(text) > current_app.config["MAX_UPLOAD_BYTES"]:
            raise ValidationError("File is too large (max 2 MB).")
        added, errors = models.import_products_csv(text.decode("utf-8-sig"))
        flash(f"Imported {added} product(s).", "ok")
        for msg in errors[:10]:
            flash(msg, "error")
        if len(errors) > 10:
            flash(f"...and {len(errors) - 10} more rows had errors.", "error")
    except UnicodeDecodeError:
        flash("The file must be a UTF-8 CSV.", "error")
    except ValidationError as e:
        _flash_errors(e)
    return redirect(url_for("main.products"))


@bp.route("/products/export")
@role_required("admin")
def products_export():
    import pandas as pd
    rows = [dict(r) for r in models.list_products()]
    cols = ["product_id", "name", "category", "unit_price", "stock_qty",
            "reorder_level", "expiry_date", "supplier_id"]
    df = pd.DataFrame(rows, columns=cols + ["supplier_name"])[cols]
    return csv_response(df, "products.csv")


# ---------- billing ----------
def _billable_products():
    today = date.today().isoformat()
    rows = get_db().execute(
        "SELECT product_id, name, unit_price, stock_qty FROM products WHERE stock_qty > 0 "
        "AND (expiry_date IS NULL OR expiry_date >= ?) ORDER BY name", (today,)).fetchall()
    return [dict(r) for r in rows]


@bp.route("/billing", methods=["GET", "POST"])
@login_required
def billing():
    if request.method == "POST":
        items = list(zip(request.form.getlist("product_id"), request.form.getlist("quantity")))
        try:
            sale_id = models.create_bill(session["user_id"], items, request.form.get("discount", 0))
            flash("Bill created and stock updated.", "ok")
            return redirect(url_for("main.bill_view", sale_id=sale_id))
        except ValidationError as e:
            _flash_errors(e)
    return render_template("billing.html", products=_billable_products())


def _own_sale_or_404(sale_id):
    sale, items = models.get_sale(sale_id)
    if sale is None or (session["role"] != "admin" and sale["user_id"] != session["user_id"]):
        abort(404)
    return sale, items


@bp.route("/bills")
@login_required
def bills():
    uid = None if session["role"] == "admin" else session["user_id"]
    return render_template("bills.html", sales=models.recent_sales(uid))


@bp.route("/bills/<int:sale_id>")
@login_required
def bill_view(sale_id):
    sale, items = _own_sale_or_404(sale_id)
    return render_template("bill.html", sale=sale, items=items)


@bp.route("/bills/<int:sale_id>/csv")
@login_required
def bill_csv(sale_id):
    sale, items = _own_sale_or_404(sale_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["GreenLeaf Grocers", f"Bill #{sale['sale_id']}", sale["sale_date"], sale["sale_time"],
                f"Cashier: {sale['username']}"])
    w.writerow(["Item", "Quantity", "Unit price", "Line total"])
    for i in items:
        w.writerow([i["name"], i["quantity"], f"{i['price']:.2f}", f"{i['line_total']:.2f}"])
    w.writerow(["Subtotal", "", "", f"{sale['subtotal']:.2f}"])
    w.writerow([f"Discount {sale['discount_percent']:g}%", "", "",
                f"-{sale['subtotal'] - sale['total_amount']:.2f}"])
    w.writerow(["Total", "", "", f"{sale['total_amount']:.2f}"])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=bill_{sale_id}.csv"})


# ---------- suppliers & users (admin) ----------
@bp.route("/suppliers", methods=["GET", "POST"])
@role_required("admin")
def suppliers_page():
    if request.method == "POST":
        try:
            models.add_supplier(request.form.get("name"), request.form.get("phone"), request.form.get("email"))
            flash("Supplier added.", "ok")
            return redirect(url_for("main.suppliers_page"))
        except ValidationError as e:
            _flash_errors(e)
    return render_template("suppliers.html", suppliers=models.suppliers(), f=request.form)


@bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@role_required("admin")
def supplier_delete(supplier_id):
    models.delete_supplier(supplier_id)
    flash("Supplier removed.", "ok")
    return redirect(url_for("main.suppliers_page"))


@bp.route("/users", methods=["GET", "POST"])
@role_required("admin")
def users_page():
    if request.method == "POST":
        try:
            models.create_user(request.form.get("username"), request.form.get("password"),
                               request.form.get("role", "cashier"))
            flash("User created.", "ok")
            return redirect(url_for("main.users_page"))
        except ValidationError as e:
            _flash_errors(e)
    return render_template("users.html", users=models.list_users())


# ---------- reports ----------
def _date_range():
    d_start, d_end = reports.default_range()
    try:
        start = parse_date(request.args.get("start"), "Start date") or d_start
        end = parse_date(request.args.get("end"), "End date") or d_end
    except ValidationError as e:
        _flash_errors(e)
        return d_start, d_end
    if start > end:
        flash("Start date must not be after end date. Showing the default range.", "error")
        return d_start, d_end
    return start, end


@bp.route("/reports")
@role_required("admin")
def reports_page():
    start, end = _date_range()
    metric = request.args.get("metric", "revenue")
    if metric not in ("revenue", "quantity"):
        metric = "revenue"
    days = current_app.config["NEAR_EXPIRY_DAYS"]
    daily, monthly = reports.daily_revenue(start, end), reports.monthly_revenue(start, end)
    top = reports.top_products(start, end, by=metric)
    cats = reports.category_share(start, end, by=metric)
    charts = {
        "daily": reports.line_chart(daily, "date", metric, "Daily trend"),
        "monthly": reports.bar_chart(monthly, "month", metric, "Monthly trend"),
        "top": reports.bar_chart(top, "name", metric, "Top 10 products", horizontal=True),
        "category": reports.pie_chart(cats, metric, "Category share"),
    }
    return render_template(
        "reports.html", start=start, end=end, metric=metric, kpis=reports.kpis(start, end),
        charts=charts, daily=daily.tail(31).to_dict("records"), monthly=monthly.to_dict("records"),
        top=top.to_dict("records"), cats=cats.to_dict("records"),
        low=reports.low_stock().to_dict("records"), expiry=reports.expiring(days).to_dict("records"),
        slow=reports.slow_moving(current_app.config["SLOW_MOVING_DAYS"]).to_dict("records"), days=days)


@bp.route("/reports/export/<name>")
@role_required("admin")
def export_report(name):
    fn = reports.REPORTS.get(name)
    if fn is None:
        abort(404)
    start, end = _date_range()
    return csv_response(fn(start, end), f"{name}_{start}_to_{end}.csv")
