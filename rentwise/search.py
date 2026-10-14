"""Phase 3: finding and retrieving flats."""
from .foundation import (AMENITIES, FURNISHING, PROPERTY_TYPES, ValidationError, db)
from .listings import _row

SORTS = {"newest": "created_at DESC, id DESC", "rent_asc": "rent ASC, id ASC",
         "rent_desc": "rent DESC, id ASC"}


def _int(p, key, default=None, lo=0, hi=10**9):
    v = p.get(key)
    if v in (None, ""):
        return default
    try:
        n = int(v)
    except ValueError:
        raise ValidationError([f"{key} must be a whole number"])
    return min(max(n, lo), hi)


def search_listings(p):
    """p is a dict of query-string values. Returns {total, page, limit, items}."""
    where, args = ["status='active'"], []

    if p.get("city"):
        where.append("LOWER(city)=LOWER(?)")
        args.append(p["city"].strip())
    if p.get("locality"):
        where.append("LOWER(locality) LIKE ?")
        args.append(f"%{p['locality'].strip().lower()}%")
    lo, hi = _int(p, "min_rent"), _int(p, "max_rent")
    if lo is not None:
        where.append("rent >= ?")
        args.append(lo)
    if hi is not None:
        where.append("rent <= ?")
        args.append(hi)
    beds = _int(p, "bedrooms", hi=10)
    if beds is not None:  # 4 means "4 or more"
        where.append("bedrooms >= ?" if beds >= 4 else "bedrooms = ?")
        args.append(beds)
    for key, allowed in (("furnishing", FURNISHING), ("property_type", PROPERTY_TYPES)):
        if p.get(key):
            if p[key] not in allowed:
                raise ValidationError([f"{key} must be one of: {', '.join(allowed)}"])
            where.append(f"{key} = ?")
            args.append(p[key])
    if p.get("amenities"):
        for a in p["amenities"].split(","):
            if a not in AMENITIES:
                raise ValidationError([f"unknown amenity: {a}"])
            where.append("amenities LIKE ?")
            args.append(f'%"{a}"%')
    if p.get("q"):
        where.append("(LOWER(title) LIKE ? OR LOWER(locality) LIKE ? OR LOWER(description) LIKE ?)")
        args += [f"%{p['q'].strip().lower()}%"] * 3

    order = SORTS.get(p.get("sort"), SORTS["newest"])
    page = _int(p, "page", 1, lo=1)
    limit = _int(p, "limit", 10, lo=1, hi=50)
    clause = " AND ".join(where)

    with db() as c:
        total = c.execute(f"SELECT COUNT(*) FROM listings WHERE {clause}", args).fetchone()[0]
        rows = c.execute(f"SELECT * FROM listings WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                         args + [limit, (page - 1) * limit]).fetchall()
    return {"total": total, "page": page, "limit": limit, "items": [_row(r) for r in rows]}


def filter_options():
    """Values the web page needs to build its filters."""
    with db() as c:
        cities = [r[0] for r in c.execute(
            "SELECT DISTINCT city FROM listings WHERE status='active' ORDER BY city")]
    return {"cities": cities, "property_types": PROPERTY_TYPES,
            "furnishing": FURNISHING, "amenities": AMENITIES}
