"""Foundation layer (data, validation, database).

Stand-in for Phase 1 so this package runs on its own. If your own Phase 1 code
differs, keep these names and swap the internals: db(), init_db(),
validate_listing(), ValidationError, NotFound.
"""
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ROOT
RES_DIR = getattr(sys, "_MEIPASS", ROOT)

PROPERTY_TYPES = ["apartment", "independent_house", "villa", "studio", "pg_room"]
FURNISHING = ["unfurnished", "semi_furnished", "furnished"]
AMENITIES = ["parking", "wifi", "lift", "power_backup", "gym", "security",
             "balcony", "ac", "water_24x7", "pet_friendly"]


class ValidationError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


class NotFound(Exception):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, city TEXT NOT NULL, locality TEXT NOT NULL,
    rent INTEGER NOT NULL, deposit INTEGER NOT NULL DEFAULT 0,
    bedrooms INTEGER NOT NULL, bathrooms INTEGER NOT NULL DEFAULT 1,
    area_sqft INTEGER, property_type TEXT NOT NULL, furnishing TEXT NOT NULL,
    available_from TEXT, amenities TEXT NOT NULL DEFAULT '[]',
    description TEXT NOT NULL DEFAULT '',
    owner_name TEXT NOT NULL, owner_phone TEXT NOT NULL,
    rental_type TEXT NOT NULL DEFAULT 'long_term',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_listings_city_rent ON listings (city, rent);
"""


def db_path():
    return os.environ.get("RENTWISE_DB") or os.path.join(APP_DIR, "rentwise.db")


@contextmanager
def db():
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript(SCHEMA)


# field: (min length, max length, required)
TEXT = {"title": (5, 120, True), "city": (2, 60, True), "locality": (2, 80, True),
        "owner_name": (2, 80, True), "description": (0, 1000, False)}
# field: (min, max, required)
NUMS = {"rent": (500, 1_000_000, True), "deposit": (0, 10_000_000, False),
        "bedrooms": (0, 10, True), "bathrooms": (1, 10, False),
        "area_sqft": (50, 20_000, False)}
# field: (allowed values, required)
CHOICES = {"property_type": (PROPERTY_TYPES, True), "furnishing": (FURNISHING, True),
           "rental_type": (["long_term"], False)}


def validate_listing(d, partial=False):
    """Return (clean, errors). With partial=True, missing fields are fine."""
    clean, errs = {}, []

    def missing(k):
        return k not in d or d[k] in (None, "")

    for k, (lo, hi, req) in TEXT.items():
        if missing(k):
            if req and not partial:
                errs.append(f"{k} is required")
            continue
        v = str(d[k]).strip()
        if lo <= len(v) <= hi:
            clean[k] = v
        else:
            errs.append(f"{k} must be {lo}-{hi} characters")

    for k, (lo, hi, req) in NUMS.items():
        if missing(k):
            if req and not partial:
                errs.append(f"{k} is required")
            continue
        try:
            v = int(d[k])
        except (TypeError, ValueError):
            errs.append(f"{k} must be a whole number")
            continue
        if lo <= v <= hi:
            clean[k] = v
        else:
            errs.append(f"{k} must be between {lo} and {hi}")

    for k, (allowed, req) in CHOICES.items():
        if missing(k):
            if req and not partial:
                errs.append(f"{k} is required")
        elif d[k] in allowed:
            clean[k] = d[k]
        else:
            errs.append(f"{k} must be one of: {', '.join(allowed)}")

    if missing("owner_phone"):
        if not partial:
            errs.append("owner_phone is required")
    else:
        ph = re.sub(r"[\s-]", "", str(d["owner_phone"]))
        ph = re.sub(r"^(\+91|91|0)(?=\d{10}$)", "", ph)
        if re.fullmatch(r"[6-9]\d{9}", ph):
            clean["owner_phone"] = ph
        else:
            errs.append("owner_phone must be a valid 10-digit Indian mobile number")

    if not missing("available_from"):
        try:
            clean["available_from"] = date.fromisoformat(str(d["available_from"])).isoformat()
        except ValueError:
            errs.append("available_from must be a date like 2026-11-01")

    if "amenities" in d:
        am = d["amenities"]
        if isinstance(am, list) and all(a in AMENITIES for a in am):
            clean["amenities"] = sorted(set(am))
        else:
            errs.append("amenities must be a list of: " + ", ".join(AMENITIES))

    return clean, errs
