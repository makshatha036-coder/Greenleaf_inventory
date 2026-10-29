"""Validation helpers, decorators and CSV helpers."""
import io
from datetime import datetime
from functools import wraps

from flask import Response, flash, redirect, session, url_for


class ValidationError(Exception):
    """Raised for any bad user input. `errors` is a list of friendly messages."""

    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# ---------- validation ----------
def parse_date(value, label="Date", required=False):
    value = (value or "").strip()
    if not value:
        if required:
            raise ValidationError(f"{label} is required.")
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValidationError(f"{label} must be a valid date in YYYY-MM-DD format.")


def _number(raw, cast, label, errors, minimum=0):
    try:
        value = cast(str(raw).strip())
    except (ValueError, TypeError):
        errors.append(f"{label} must be a valid number.")
        return None
    if value != value or value in (float("inf"), float("-inf")):
        errors.append(f"{label} must be a valid number.")
        return None
    if value < minimum:
        errors.append(f"{label} cannot be negative." if minimum == 0 else f"{label} must be at least {minimum}.")
        return None
    return value


def validate_product(data):
    """Return a cleaned dict or raise ValidationError."""
    errors = []
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()
    if not name:
        errors.append("Product name is required.")
    elif len(name) > 100:
        errors.append("Product name is too long (max 100 characters).")
    if not category:
        errors.append("Category is required.")

    price = _number(data.get("unit_price"), float, "Unit price", errors)
    stock = _number(data.get("stock_qty"), int, "Stock quantity", errors)
    reorder = _number(data.get("reorder_level", 10) or 10, int, "Reorder level", errors)

    expiry = None
    try:
        expiry = parse_date(data.get("expiry_date"), "Expiry date")
    except ValidationError as e:
        errors.extend(e.errors)

    supplier_id = None
    raw_sup = str(data.get("supplier_id") or "").strip()
    if raw_sup:
        supplier_id = _number(raw_sup, int, "Supplier", errors, minimum=1)

    if errors:
        raise ValidationError(errors)
    return {
        "name": name, "category": category, "unit_price": round(price, 2),
        "stock_qty": stock, "reorder_level": reorder,
        "expiry_date": expiry, "supplier_id": supplier_id,
    }


# ---------- access control ----------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") != role:
                flash("You do not have permission to open that page.", "error")
                return redirect(url_for("main.dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------- CSV ----------
def csv_response(df, filename):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
