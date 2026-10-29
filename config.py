import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
    DATABASE = os.path.join(BASE_DIR, "greenleaf.db")
    NEAR_EXPIRY_DAYS = 15
    SLOW_MOVING_DAYS = 30
    MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB CSV limit
