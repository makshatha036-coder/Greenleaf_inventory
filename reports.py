"""pandas analytics, KPIs and matplotlib charts."""
import base64
import io
from datetime import date, timedelta

import pandas as pd
from matplotlib.figure import Figure  # Figure (not pyplot) is thread-safe in Flask

from database import get_db

GREEN, LEAF, GREY = "#2f7d4f", "#8cc28c", "#6b7a6f"


def _read(sql, params=()):
    return pd.read_sql_query(sql, get_db(), params=params)


def default_range(days=90):
    end = date.today()
    return (end - timedelta(days=days)).isoformat(), end.isoformat()


# ---------- data frames ----------
def sales_df(start, end):
    return _read("SELECT sale_id, sale_date, total_amount FROM sales WHERE sale_date BETWEEN ? AND ?",
                 (start, end))


def items_df(start, end):
    return _read(
        "SELECT s.sale_id, s.sale_date, p.product_id, p.name, p.category, si.quantity, si.price, "
        "si.quantity * si.price AS line_total FROM sale_items si "
        "JOIN sales s ON s.sale_id = si.sale_id JOIN products p ON p.product_id = si.product_id "
        "WHERE s.sale_date BETWEEN ? AND ?", (start, end))


def _period_report(start, end, key_fn, label):
    sales, items = sales_df(start, end), items_df(start, end)
    cols = [label, "revenue", "bills", "quantity"]
    if sales.empty:
        return pd.DataFrame(columns=cols)
    sales[label] = sales["sale_date"].map(key_fn)
    items[label] = items["sale_date"].map(key_fn)
    a = sales.groupby(label).agg(revenue=("total_amount", "sum"), bills=("sale_id", "count"))
    b = items.groupby(label).agg(quantity=("quantity", "sum"))
    out = a.join(b).fillna(0).reset_index()
    out["revenue"] = out["revenue"].round(2)
    out["quantity"] = out["quantity"].astype(int)
    return out[cols]


def daily_revenue(start, end):
    return _period_report(start, end, lambda d: d, "date")


def monthly_revenue(start, end):
    return _period_report(start, end, lambda d: d[:7], "month")


def top_products(start, end, n=10, by="revenue"):
    items = items_df(start, end)
    if items.empty:
        return pd.DataFrame(columns=["name", "category", "quantity", "revenue"])
    g = (items.groupby(["name", "category"])
         .agg(quantity=("quantity", "sum"), revenue=("line_total", "sum")).reset_index())
    g["revenue"] = g["revenue"].round(2)
    by = by if by in ("revenue", "quantity") else "revenue"
    return g.sort_values(by, ascending=False).head(n).reset_index(drop=True)


def category_share(start, end, by="revenue"):
    items = items_df(start, end)
    if items.empty:
        return pd.DataFrame(columns=["category", "quantity", "revenue", "share_pct"])
    g = (items.groupby("category")
         .agg(quantity=("quantity", "sum"), revenue=("line_total", "sum")).reset_index())
    by = by if by in ("revenue", "quantity") else "revenue"
    g["share_pct"] = (g[by] / g[by].sum() * 100).round(1)
    g["revenue"] = g["revenue"].round(2)
    return g.sort_values("share_pct", ascending=False).reset_index(drop=True)


def slow_moving(days=30, max_units=2):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _read(
        "SELECT p.product_id, p.name, p.category, p.stock_qty, "
        "COALESCE(SUM(CASE WHEN s.sale_date >= ? THEN si.quantity END), 0) AS units_sold, "
        "MAX(s.sale_date) AS last_sold "
        "FROM products p LEFT JOIN sale_items si ON si.product_id = p.product_id "
        "LEFT JOIN sales s ON s.sale_id = si.sale_id "
        "WHERE p.stock_qty > 0 GROUP BY p.product_id HAVING units_sold <= ? "
        "ORDER BY units_sold, p.stock_qty DESC", (cutoff, max_units))


def low_stock(*_):
    return _read("SELECT product_id, name, category, stock_qty, reorder_level FROM products "
                 "WHERE stock_qty <= reorder_level ORDER BY stock_qty - reorder_level, name")


def expiring(days=15):
    today = date.today()
    return _read(
        "SELECT product_id, name, category, stock_qty, expiry_date, "
        "CASE WHEN expiry_date < ? THEN 'Expired' ELSE 'Expiring soon' END AS status "
        "FROM products WHERE expiry_date IS NOT NULL AND expiry_date <= ? AND stock_qty > 0 "
        "ORDER BY expiry_date", (today.isoformat(), (today + timedelta(days=days)).isoformat()))


# ---------- KPIs ----------
def kpis(start, end):
    sales = sales_df(start, end)
    items = items_df(start, end)
    revenue = float(sales["total_amount"].sum()) if not sales.empty else 0.0
    bills = len(sales)
    units = int(items["quantity"].sum()) if not items.empty else 0
    stock_units = get_db().execute("SELECT COALESCE(SUM(stock_qty), 0) FROM products").fetchone()[0]
    cats = category_share(start, end)
    return {
        "total_revenue": round(revenue, 2),
        "bills": bills,
        "avg_bill": round(revenue / bills, 2) if bills else 0.0,
        "units_sold": units,
        # units sold in the period / units currently in stock
        "stock_turnover": round(units / stock_units, 2) if stock_units else 0.0,
        "low_stock_count": len(low_stock()),
        "top_category": cats.iloc[0]["category"] if not cats.empty else "-",
        "top_category_share": float(cats.iloc[0]["share_pct"]) if not cats.empty else 0.0,
    }


# ---------- charts (return base64 PNG or None) ----------
def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    return base64.b64encode(buf.getvalue()).decode()


def _label(metric):
    return ("Revenue (₹)", "revenue") if metric == "revenue" else ("Quantity sold", "quantity")


def line_chart(df, xcol, metric, title):
    if df.empty:
        return None
    ylabel, col = _label(metric)
    fig = Figure(figsize=(8, 3.4))
    ax = fig.subplots()
    ax.plot(pd.to_datetime(df[xcol]), df[col], color=GREEN, linewidth=1.8)
    ax.set_title(title); ax.set_ylabel(ylabel); ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    return _png(fig)


def bar_chart(df, xcol, metric, title, horizontal=False):
    if df.empty:
        return None
    ylabel, col = _label(metric)
    fig = Figure(figsize=(8, 3.8))
    ax = fig.subplots()
    if horizontal:
        ax.barh(df[xcol][::-1], df[col][::-1], color=GREEN)
        ax.set_xlabel(ylabel)
    else:
        ax.bar(df[xcol], df[col], color=GREEN)
        ax.set_ylabel(ylabel)
        fig.autofmt_xdate()
    ax.set_title(title); ax.grid(alpha=0.25)
    return _png(fig)


def pie_chart(df, metric, title):
    if df.empty:
        return None
    _, col = _label(metric)
    fig = Figure(figsize=(5.5, 4))
    ax = fig.subplots()
    ax.pie(df[col], labels=df["category"], autopct="%1.0f%%", textprops={"fontsize": 8})
    ax.set_title(title)
    return _png(fig)


REPORTS = {
    "daily": daily_revenue,
    "monthly": monthly_revenue,
    "top_products": lambda s, e: top_products(s, e),
    "category_share": category_share,
    "low_stock": low_stock,
    "expiry": lambda s, e: expiring(),
    "slow_moving": lambda s, e: slow_moving(),
}
