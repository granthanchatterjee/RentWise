"""Phase 2: creating and managing flat listings."""
import json

from .foundation import NotFound, ValidationError, db, validate_listing

DEFAULTS = {"deposit": 0, "bathrooms": 1, "amenities": [], "description": "",
            "area_sqft": None, "available_from": None, "rental_type": "long_term"}


def _row(r):
    d = dict(r)
    d["amenities"] = json.loads(d["amenities"])
    return d


def get_listing(listing_id):
    with db() as c:
        r = c.execute("SELECT * FROM listings WHERE id=? AND status='active'",
                      (listing_id,)).fetchone()
    if not r:
        raise NotFound(f"Listing {listing_id} not found")
    return _row(r)


def create_listing(data):
    clean, errs = validate_listing(data)
    if errs:
        raise ValidationError(errs)
    row = {**DEFAULTS, **clean}
    row["amenities"] = json.dumps(row["amenities"])
    cols = ", ".join(row)
    marks = ", ".join(":" + k for k in row)
    with db() as c:
        new_id = c.execute(f"INSERT INTO listings ({cols}) VALUES ({marks})", row).lastrowid
    return get_listing(new_id)


def update_listing(listing_id, data):
    get_listing(listing_id)  # 404 if missing
    clean, errs = validate_listing(data, partial=True)
    if not errs and not clean:
        errs = ["No valid fields to update"]
    if errs:
        raise ValidationError(errs)
    if "amenities" in clean:
        clean["amenities"] = json.dumps(clean["amenities"])
    sets = ", ".join(f"{k}=:{k}" for k in clean)
    with db() as c:
        c.execute(f"UPDATE listings SET {sets} WHERE id=:_id", {**clean, "_id": listing_id})
    return get_listing(listing_id)


def delete_listing(listing_id):
    """Soft delete: the row stays in the database but stops appearing."""
    with db() as c:
        n = c.execute("UPDATE listings SET status='removed' WHERE id=? AND status='active'",
                      (listing_id,)).rowcount
    if not n:
        raise NotFound(f"Listing {listing_id} not found")
