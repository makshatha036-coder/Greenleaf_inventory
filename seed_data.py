"""Generate sample data: 50+ products, 6 suppliers, 600 sales over ~6 months.

Usage:  python seed_data.py            (only seeds an empty database)
        python seed_data.py --reset    (wipes products/sales first)
"""
import random
import sys
from datetime import date, datetime, timedelta

from app import create_app
from database import get_db

random.seed(42)

CATALOG = {  # category: (price range, perishable?, [products])
    "Fruits & Vegetables": ((20, 120), True, ["Bananas 1kg", "Apples 1kg", "Tomatoes 1kg", "Onions 1kg", "Potatoes 1kg", "Carrots 500g", "Spinach Bunch", "Mangoes 1kg"]),
    "Dairy & Eggs": ((25, 140), True, ["Milk 1L", "Curd 500g", "Butter 100g", "Paneer 200g", "Cheese Slices", "Eggs Tray 12", "Buttermilk 200ml"]),
    "Bakery": ((20, 90), True, ["Bread Loaf", "Brown Bread", "Burger Buns", "Cookies Pack", "Cake Rusk", "Croissant"]),
    "Beverages": ((20, 250), False, ["Orange Juice 1L", "Green Tea 25 Bags", "Instant Coffee 100g", "Cola 2L", "Mineral Water 1L", "Energy Drink", "Coconut Water"]),
    "Snacks": ((10, 120), False, ["Potato Chips", "Salted Peanuts", "Chocolate Bar", "Biscuits Pack", "Popcorn", "Namkeen Mix", "Granola Bar"]),
    "Staples": ((40, 600), False, ["Basmati Rice 5kg", "Wheat Flour 5kg", "Toor Dal 1kg", "Sugar 1kg", "Salt 1kg", "Sunflower Oil 1L", "Tea Powder 250g"]),
    "Household": ((30, 350), None, ["Dish Wash Liquid", "Laundry Detergent 1kg", "Toilet Cleaner", "Hand Wash", "Tissue Pack", "Garbage Bags"]),
    "Personal Care": ((30, 300), None, ["Shampoo 200ml", "Toothpaste 150g", "Bath Soap", "Face Wash", "Deodorant"]),
}
SUPPLIERS = [("Fresh Farms Co.", "9876500001", "sales@freshfarms.example"),
             ("DairyBest Ltd.", "9876500002", "orders@dairybest.example"),
             ("Daily Bakers", "9876500003", "hello@dailybakers.example"),
             ("Metro Wholesale", "9876500004", "supply@metro.example"),
             ("PureHome Traders", "9876500005", "care@purehome.example"),
             ("Snack Hub", "9876500006", "bulk@snackhub.example")]


def seed(reset=False):
    app = create_app()
    with app.app_context():
        db = get_db()
        if db.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
            if not reset:
                print("Database already has products. Use --reset to replace the sample data.")
                return
            for t in ("sale_items", "sales", "products", "suppliers"):
                db.execute(f"DELETE FROM {t}")
            db.execute("DELETE FROM sqlite_sequence WHERE name IN ('sale_items','sales','products','suppliers')")
        today = date.today()

        sup_ids = [db.execute("INSERT INTO suppliers (name, phone, email) VALUES (?,?,?)", s).lastrowid
                   for s in SUPPLIERS]

        products = []  # (id, price)
        for cat, ((lo, hi), perishable, names) in CATALOG.items():
            for name in names:
                price = round(random.uniform(lo, hi), 2)
                if perishable is True:
                    expiry = today + timedelta(days=random.randint(2, 25))
                elif perishable is False:
                    expiry = today + timedelta(days=random.randint(120, 540))
                else:
                    expiry = None
                reorder = random.randint(8, 25)
                stock = random.randint(reorder + 5, 150)
                products.append([name, cat, price, stock, reorder, expiry.isoformat() if expiry else None,
                                 random.choice(sup_ids)])
        for p in random.sample(products, 9):          # force some low-stock items
            p[3] = random.randint(0, p[4])
        ids = []
        for p in products:
            ids.append(db.execute(
                "INSERT INTO products (name, category, unit_price, stock_qty, reorder_level, expiry_date, supplier_id) "
                "VALUES (?,?,?,?,?,?,?)", p).lastrowid)
        prices = {pid: p[2] for pid, p in zip(ids, products)}
        weights = {pid: random.uniform(1, 4) for pid in ids}
        for pid in random.sample(ids, 8):                               # a few best sellers
            weights[pid] *= 3
        slow = set(random.sample(ids, 6))                               # no sales in last 30 days

        user_ids = [r[0] for r in db.execute("SELECT user_id FROM users")]
        n_sales = 0
        for _ in range(620):
            d = today - timedelta(days=random.randint(0, 180))
            pool = [i for i in ids if not (i in slow and (today - d).days < 30)]
            chosen = set(random.choices(pool, weights=[weights[i] for i in pool], k=random.randint(1, 5)))
            lines = [(pid, random.randint(1, 5), prices[pid]) for pid in chosen]
            subtotal = round(sum(q * pr for _, q, pr in lines), 2)
            disc = random.choice([0, 0, 0, 0, 5, 10])
            total = round(subtotal * (1 - disc / 100), 2)
            t = datetime(2000, 1, 1, random.randint(8, 21), random.randint(0, 59), random.randint(0, 59))
            sid = db.execute(
                "INSERT INTO sales (sale_date, sale_time, user_id, subtotal, discount_percent, total_amount) "
                "VALUES (?,?,?,?,?,?)",
                (d.isoformat(), t.strftime("%H:%M:%S"), random.choice(user_ids), subtotal, disc, total)).lastrowid
            db.executemany("INSERT INTO sale_items (sale_id, product_id, quantity, price) VALUES (?,?,?,?)",
                           [(sid, pid, q, pr) for pid, q, pr in lines])
            n_sales += 1
        db.commit()
        print(f"Seeded {len(ids)} products, {len(sup_ids)} suppliers and {n_sales} sales.")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
