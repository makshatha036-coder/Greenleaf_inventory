"""Run this first: python check_setup.py  -> tells you exactly what is missing."""
import hashlib
import importlib
from importlib import metadata
import socket
import sys

ok = True
print(f"Python {sys.version.split()[0]}")
if sys.version_info < (3, 9):
    print("  PROBLEM: Python 3.9 or newer is required"); ok = False
for pkg in ("flask", "pandas", "matplotlib", "pytest"):
    try:
        importlib.import_module(pkg)
        print(f"  OK       {pkg} {metadata.version(pkg)}")
    except ImportError:
        print(f"  MISSING  {pkg}  ->  pip install -r requirements.txt"); ok = False
print("  OK       password hashing (pbkdf2)" if hasattr(hashlib, "pbkdf2_hmac") else "  PROBLEM  pbkdf2 missing")
s = socket.socket()
try:
    s.bind(("127.0.0.1", 5001)); print("  OK       port 5001 is free")
except OSError:
    print("  NOTE     port 5001 is busy. Use another: set PORT=8000 (Windows) / export PORT=8000 (Mac/Linux)")
finally:
    s.close()
print("\nAll good. Next: python seed_data.py, then python app.py" if ok else "\nFix the items above, then run this again.")
