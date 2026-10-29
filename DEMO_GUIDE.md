# Demo guide (about 10 minutes)

## A. One-time setup
1. Open a terminal in the project folder.
2. `python -m venv venv`, then activate it:
   Windows `venv\Scripts\activate` | Mac/Linux `source venv/bin/activate`
3. `pip install -r requirements.txt`
4. `python check_setup.py`  (every line should say OK)
5. `python seed_data.py`  (prints: Seeded 53 products, 6 suppliers and 620 sales)
6. `python run_tests.py`  (expect 32 passed; creates TEST_REPORT.md)
7. `python app.py`  then open http://127.0.0.1:5001

Start over any time: stop the server (Ctrl+C), then `python seed_data.py --reset`.

## B. Demo script
1. **Login as admin** (admin / admin123). The dashboard shows revenue, average bill, low-stock and expiry alerts.
2. **Wrong password**: log out, try a wrong password, show the friendly error. Log back in.
3. **Add a product by hand**: Products > Add product. Name `Demo Brown Sugar 1kg`, category Staples, price 60, stock 25, reorder level 10, expiry 2027-05-01 > Save.
4. **Show validation**: Add product with price -5 (blocked), or an impossible expiry date. Duplicate name also rejected.
5. **Edit and search**: edit that product's stock, then search "sugar" and filter by category.
6. **Import CSV**: on Products, choose `sample_data/demo_products.csv` > Import. Eight demo products appear.
   Point out the orange *Low stock* tags (Greek Yogurt, Whole Wheat Bread) and red *Expiring soon* tags.
   Tip: the expiry dates in that CSV are near late October/early November 2026. If today is later, edit one demo
   product's expiry to a date within the next 10 days so the near-expiry alert shows.
7. **Export CSV**: click Export CSV on Products, open the file.
8. **Suppliers and Users**: add a supplier; create a cashier named `ravi`.
9. **Billing** (New bill): add Demo Basmati Rice x3 and Demo Olive Oil x2, discount 10%.
   The live total shows 1233.00. Create bill. The bill page shows cashier and time. Click Print and Download CSV.
10. **Stock deducted**: Products > search "Demo". Rice went 60 > 57, Olive Oil 25 > 23.
11. **Error handling**: New bill, Greek Yogurt quantity 50 > blocked (only 6 in stock). Quantity -1 > blocked.
12. **Cashier role**: log out, log in as cashier / cashier123. Only billing and own bills are available;
    typing /products or /reports in the address bar sends you back to the dashboard.
13. **Reports** (admin): set From/To dates, switch Charts show to Quantity, view the daily trend, monthly trend,
    top 10, category pie. Show the Low stock, Expiry and Slow-moving tables, and Export CSV on a report.
14. **Tests**: show TEST_REPORT.md (32 passed).

## C. Fixes for common problems
| Problem | Fix |
|---|---|
| `python` not found | Use `python3` (Mac/Linux) or `py` (Windows) |
| `No module named flask` | Activate the venv, then `pip install -r requirements.txt` |
| Port busy | `set PORT=8000` (Windows) or `export PORT=8000`, then `python app.py` |
| Empty reports | Run `python seed_data.py` |
| Want a clean database | Stop the server, `python seed_data.py --reset` |
