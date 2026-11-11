import base64, difflib, hashlib, json, os, re, secrets, sqlite3
from datetime import date, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "rentwise_p45.db")
UPLOADS = os.path.join(BASE, "uploads")
PORT = int(os.environ.get("PORT", "8000"))
os.makedirs(UPLOADS, exist_ok=True)
SESSIONS = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, role TEXT, name TEXT, email TEXT UNIQUE, phone TEXT,
  salt TEXT, pw TEXT, id_type TEXT, id_name TEXT, id_file TEXT, id_status TEXT DEFAULT 'none');
CREATE TABLE IF NOT EXISTS flats(id INTEGER PRIMARY KEY, owner_id INTEGER, title TEXT, city TEXT, area TEXT,
  bedrooms INTEGER, rent INTEGER, kind TEXT, descr TEXT, bill_name TEXT, bill_file TEXT, bill_status TEXT DEFAULT 'pending',
  active INTEGER DEFAULT 1, photos TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY, flat_id INTEGER, tenant_id INTEGER, start_day TEXT,
  end_day TEXT, note TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS blocked(flat_id INTEGER, day TEXT, PRIMARY KEY(flat_id, day));
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, author_id INTEGER, target_id INTEGER, booking_id INTEGER,
  rating INTEGER, body TEXT, created TEXT, UNIQUE(author_id, booking_id));
CREATE TABLE IF NOT EXISTS prefs(user_id INTEGER PRIMARY KEY, city TEXT, budget INTEGER, smoking TEXT, pets TEXT,
  diet TEXT, sleep TEXT, guests TEXT);
CREATE TABLE IF NOT EXISTS squads(id INTEGER PRIMARY KEY, name TEXT, city TEXT, created_by INTEGER);
CREATE TABLE IF NOT EXISTS squad_members(squad_id INTEGER, user_id INTEGER, status TEXT, PRIMARY KEY(squad_id, user_id));
"""


def q(sql, args=(), one=False, commit=False):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        cur = c.execute(sql, args)
        if commit:
            c.commit()
            return cur.lastrowid
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        c.close()
    if one:
        return rows[0] if rows else None
    return rows


class Err(Exception):
    def __init__(self, msg, code=400):
        self.msg = msg
        self.code = code


def need(u):
    if not u:
        raise Err("Please log in first", 401)


def need_role(u, role):
    need(u)
    if u["role"] != role:
        raise Err("Only %ss can do this" % role, 403)


def pdate(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        raise Err("Enter a valid date")


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000).hex()


def pub(u):
    keys = ("id", "role", "name", "email", "phone", "id_type", "id_name", "id_status")
    return {k: u[k] for k in keys}


def rating(uid):
    r = q("SELECT COUNT(*) n, AVG(rating) a FROM reviews WHERE target_id=?", (uid,), one=True)
    return {"n": r["n"], "a": r["a"]}


def reviews_about(uid):
    return q("SELECT r.rating, r.body, r.created, a.name author FROM reviews r JOIN users a ON a.id=r.author_id "
             "WHERE r.target_id=? ORDER BY r.id DESC", (uid,))


def names_match(a, b):
    ta = set(re.sub(r"[^a-z ]", "", a.lower()).split())
    tb = set(re.sub(r"[^a-z ]", "", b.lower()).split())
    if not ta or not tb:
        return False
    common = len(ta & tb)
    if common >= 2 or (common == 1 and len(ta) == 1 and len(tb) == 1):
        return True
    return difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio() >= 0.85


def is_free(fid, s, e):
    if q("SELECT 1 FROM bookings WHERE flat_id=? AND status='approved' AND start_day < ? AND end_day > ?",
         (fid, str(e), str(s)), one=True):
        return False
    if q("SELECT 1 FROM blocked WHERE flat_id=? AND day >= ? AND day < ?", (fid, str(s), str(e)), one=True):
        return False
    return True



def store_file(uid, d):
    ext = (d.get("filename") or "").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "pdf"):
        raise Err("Upload a JPG, PNG or PDF file")
    try:
        raw = base64.b64decode(d.get("data") or "")
    except ValueError:
        raise Err("Could not read the file")
    if not raw or len(raw) > 3 * 1024 * 1024:
        raise Err("The file is empty or bigger than 3 MB")
    fname = "%d_%s.%s" % (uid, secrets.token_hex(6), ext)
    with open(os.path.join(UPLOADS, fname), "wb") as f:
        f.write(raw)
    return fname


def send_file(h, fname):
    path = os.path.join(UPLOADS, os.path.basename(fname))
    if not os.path.exists(path):
        raise Err("File not found", 404)
    ctype = {"pdf": "application/pdf", "png": "image/png"}.get(path.rsplit(".", 1)[-1], "image/jpeg")
    with open(path, "rb") as f:
        data = f.read()
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    h.wfile.write(data)
    return None


MAX_PHOTOS = 3


def store_photo(uid, d):
    ext = (d.get("filename") or "").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png"):
        raise Err("Photos must be JPG or PNG images")
    try:
        raw = base64.b64decode(d.get("data") or "")
    except ValueError:
        raise Err("Could not read the photo")
    if not raw or len(raw) > 2 * 1024 * 1024:
        raise Err("Each photo must be smaller than 2 MB")
    if not (raw.startswith(b"\xff\xd8") or raw.startswith(b"\x89PNG")):
        raise Err("That file is not a valid JPG or PNG image")
    fname = "photo_%d_%s.%s" % (uid, secrets.token_hex(6), "png" if raw.startswith(b"\x89PNG") else "jpg")
    with open(os.path.join(UPLOADS, fname), "wb") as f:
        f.write(raw)
    return fname


def photo_list(raw):
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def fix_photos(r):
    r["photos"] = ["/api/photo/" + p for p in photo_list(r.get("photos"))]


def hide_private(r):
    for k in ("consumer_no", "reg_name", "board", "bill_file", "bill_name"):
        r.pop(k, None)
    fix_photos(r)


ROUTES = []


def route(method, pattern):
    def deco(f):
        ROUTES.append((method, re.compile("^" + pattern + "$"), f))
        return f
    return deco


def login_as(uid):
    tok = secrets.token_hex(16)
    SESSIONS[tok] = uid
    return 200, {"ok": True}, {"Set-Cookie": "tok=%s; Path=/; HttpOnly; SameSite=Lax" % tok}


# ---------------- accounts ----------------
@route("POST", "/api/signup")
def signup(h, u, d):
    role = d.get("role")
    if role not in ("owner", "tenant"):
        raise Err("Choose owner or tenant")
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if len(name) < 3 or "@" not in email or len(pw) < 6:
        raise Err("Enter your full name, a valid email and a password of 6 or more characters")
    if q("SELECT 1 FROM users WHERE email=?", (email,), one=True):
        raise Err("This email is already registered")
    salt = secrets.token_hex(8)
    uid = q("INSERT INTO users(role,name,email,phone,salt,pw) VALUES(?,?,?,?,?,?)",
            (role, name, email, d.get("phone") or "", salt, hash_pw(pw, salt)), commit=True)
    return login_as(uid)


@route("POST", "/api/login")
def login(h, u, d):
    row = q("SELECT * FROM users WHERE email=?", ((d.get("email") or "").strip().lower(),), one=True)
    if not row or hash_pw(d.get("password") or "", row["salt"]) != row["pw"]:
        raise Err("Wrong email or password", 401)
    return login_as(row["id"])


@route("POST", "/api/logout")
def logout(h, u, d):
    c = SimpleCookie(h.headers.get("Cookie", ""))
    if "tok" in c:
        SESSIONS.pop(c["tok"].value, None)
    return 200, {"ok": True}, {"Set-Cookie": "tok=; Path=/; Max-Age=0"}


@route("GET", "/api/me")
def me(h, u, d):
    if not u:
        return {"user": None}
    out = pub(u)
    out["rating"] = rating(u["id"])
    return {"user": out}


@route("POST", "/api/me/id")
def upload_id(h, u, d):
    need(u)
    id_type = (d.get("id_type") or "").strip()
    id_name = (d.get("id_name") or "").strip()
    ext = (d.get("filename") or "").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "pdf"):
        raise Err("Upload a JPG, PNG or PDF file")
    if not id_type or not id_name:
        raise Err("Choose the ID type and type the name printed on it")
    if not names_match(id_name, u["name"]):
        raise Err("The name on the ID does not match your account name")
    try:
        raw = base64.b64decode(d.get("data") or "")
    except ValueError:
        raise Err("Could not read the file")
    if not raw or len(raw) > 3 * 1024 * 1024:
        raise Err("The file is empty or bigger than 3 MB")
    fname = "%d_%s.%s" % (u["id"], secrets.token_hex(6), ext)
    with open(os.path.join(UPLOADS, fname), "wb") as f:
        f.write(raw)
    q("UPDATE users SET id_type=?, id_name=?, id_file=?, id_status='pending' WHERE id=?",
      (id_type, id_name, fname, u["id"]), commit=True)
    return {"ok": True}


@route("GET", "/api/admin/pending")
def pending(h, u, d):
    need_role(u, "admin")
    return q("SELECT id, name, email, role, id_type, id_name FROM users WHERE id_status='pending'")


@route("POST", "/api/admin/verify")
def admin_verify(h, u, d):
    need_role(u, "admin")
    status = "verified" if d.get("approve") else "rejected"
    q("UPDATE users SET id_status=? WHERE id=? AND id_status='pending'", (status, d.get("user_id")), commit=True)
    return {"ok": True}


@route("GET", r"/api/admin/idfile/(\d+)")
def idfile(h, u, d, uid):
    need_role(u, "admin")
    row = q("SELECT id_file FROM users WHERE id=?", (uid,), one=True)
    if not row or not row["id_file"]:
        raise Err("No file uploaded", 404)
    return send_file(h, row["id_file"])


@route("GET", "/api/admin/bills")
def pending_bills(h, u, d):
    need_role(u, "admin")
    return q("SELECT f.id, f.title, f.city, f.bill_name, o.name owner_name, o.email owner_email, "
             "(SELECT COUNT(*) FROM flats g WHERE lower(g.bill_name)=lower(f.bill_name) AND g.owner_id != f.owner_id "
             "AND g.bill_status != 'rejected') other_owners "
             "FROM flats f JOIN users o ON o.id=f.owner_id WHERE f.bill_status='pending' ORDER BY f.id")


@route("POST", "/api/admin/bill-verify")
def admin_bill_verify(h, u, d):
    need_role(u, "admin")
    status = "verified" if d.get("approve") else "rejected"
    q("UPDATE flats SET bill_status=? WHERE id=? AND bill_status='pending'", (status, d.get("flat_id")), commit=True)
    return {"ok": True}


@route("GET", r"/api/admin/billfile/(\d+)")
def billfile(h, u, d, fid):
    need_role(u, "admin")
    row = q("SELECT bill_file FROM flats WHERE id=?", (fid,), one=True)
    if not row or not row["bill_file"]:
        raise Err("No bill uploaded", 404)
    return send_file(h, row["bill_file"])


# ---------------- flats ----------------
@route("GET", r"/api/photo/([A-Za-z0-9_.]+)")
def flat_photo(h, u, d, fname):
    if not fname.startswith("photo_") or not q("SELECT 1 FROM flats WHERE photos LIKE ?", ('%"' + fname + '"%',), one=True):
        raise Err("Photo not found", 404)
    return send_file(h, fname)


@route("GET", "/api/flats")
def flats(h, u, d):
    sql = ("SELECT f.*, o.name owner_name FROM flats f JOIN users o ON o.id=f.owner_id "
           "WHERE f.active=1 AND f.bill_status='verified' AND o.id_status='verified'")
    args = []
    if d.get("city"):
        sql += " AND lower(f.city)=lower(?)"
        args.append(d["city"].strip())
    if d.get("kind") in ("long", "short"):
        sql += " AND f.kind=?"
        args.append(d["kind"])
    if d.get("max_rent"):
        sql += " AND f.rent<=?"
        args.append(int(d["max_rent"]))
    if d.get("bedrooms"):
        sql += " AND f.bedrooms>=?"
        args.append(int(d["bedrooms"]))
    rows = q(sql + " ORDER BY f.id DESC", args)
    for r in rows:
        hide_private(r)
        r["owner_rating"] = rating(r["owner_id"])
    return rows


@route("GET", "/api/flats/mine")
def my_flats(h, u, d):
    need_role(u, "owner")
    rows = q("SELECT * FROM flats WHERE owner_id=? ORDER BY id DESC", (u["id"],))
    for r in rows:
        r.pop("bill_file", None)
        r.pop("consumer_no", None)
        r.pop("reg_name", None)
        r.pop("board", None)
        fix_photos(r)
    return rows


@route("POST", "/api/flats")
def add_flat(h, u, d):
    need_role(u, "owner")
    if u["id_status"] != "verified":
        raise Err("Your ID proof must be verified before you can list a flat", 403)
    if q("SELECT COUNT(*) n FROM flats WHERE owner_id=?", (u["id"],), one=True)["n"] >= 5:
        raise Err("Limit of 5 flats per owner. RentWise is for owners, not agents", 403)
    title = (d.get("title") or "").strip()
    city = (d.get("city") or "").strip()
    kind = d.get("kind")
    try:
        rent = int(d.get("rent"))
        beds = int(d.get("bedrooms"))
    except (TypeError, ValueError):
        raise Err("Enter the rent and number of bedrooms as numbers")
    if not title or not city or kind not in ("long", "short") or rent <= 0 or beds <= 0:
        raise Err("Fill in title, city, type, rent and bedrooms")
    bill_name = (d.get("bill_name") or "").strip()
    if not bill_name:
        raise Err("Type the name printed on the electricity bill")
    if not names_match(bill_name, u["name"]):
        raise Err("The name on the electricity bill does not match your account name")
    incoming = d.get("photos") or []
    if not isinstance(incoming, list) or len(incoming) > MAX_PHOTOS:
        raise Err("You can add up to %d photos" % MAX_PHOTOS)
    fname = store_file(u["id"], d)
    photos = [store_photo(u["id"], p) for p in incoming if isinstance(p, dict)]
    q("INSERT INTO flats(owner_id,title,city,area,bedrooms,rent,kind,descr,bill_name,bill_file,bill_status,photos) "
      "VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?)",
      (u["id"], title, city, (d.get("area") or "").strip(), beds, rent, kind, (d.get("descr") or "").strip(),
       bill_name, fname, json.dumps(photos)), commit=True)
    return {"ok": True}


@route("POST", r"/api/flats/(\d+)/bill")
def reupload_bill(h, u, d, fid):
    f = own_flat(u, fid)
    bill_name = (d.get("bill_name") or "").strip()
    if not bill_name:
        raise Err("Type the name printed on the electricity bill")
    if not names_match(bill_name, u["name"]):
        raise Err("The name on the electricity bill does not match your account name")
    fname = store_file(u["id"], d)
    q("UPDATE flats SET bill_name=?, bill_file=?, bill_status='pending' WHERE id=?", (bill_name, fname, f["id"]), commit=True)
    return {"ok": True}


def own_flat(u, fid):
    need_role(u, "owner")
    f = q("SELECT * FROM flats WHERE id=? AND owner_id=?", (fid, u["id"]), one=True)
    if not f:
        raise Err("Flat not found", 404)
    return f


@route("PUT", r"/api/flats/(\d+)")
def edit_flat(h, u, d, fid):
    f = own_flat(u, fid)
    try:
        rent = int(d.get("rent", f["rent"]))
    except (TypeError, ValueError):
        raise Err("Rent must be a number")
    q("UPDATE flats SET title=?, rent=?, descr=?, active=? WHERE id=?",
      ((d.get("title") or f["title"]).strip(), rent, d.get("descr", f["descr"]),
       1 if d.get("active", f["active"]) else 0, fid), commit=True)
    return {"ok": True}


@route("POST", r"/api/flats/(\d+)/photos")
def add_photos(h, u, d, fid):
    f = own_flat(u, fid)
    cur = photo_list(f["photos"])
    incoming = [p for p in (d.get("photos") or []) if isinstance(p, dict)]
    if not incoming:
        raise Err("Choose at least one photo")
    if len(cur) + len(incoming) > MAX_PHOTOS:
        raise Err("A flat can have at most %d photos (it has %d now)" % (MAX_PHOTOS, len(cur)))
    cur += [store_photo(u["id"], p) for p in incoming]
    q("UPDATE flats SET photos=? WHERE id=?", (json.dumps(cur), fid), commit=True)
    return {"ok": True}


@route("POST", r"/api/flats/(\d+)/photos/remove")
def remove_photo(h, u, d, fid):
    f = own_flat(u, fid)
    name = os.path.basename(d.get("name") or "")
    cur = photo_list(f["photos"])
    if name not in cur:
        raise Err("Photo not found", 404)
    cur.remove(name)
    q("UPDATE flats SET photos=? WHERE id=?", (json.dumps(cur), fid), commit=True)
    try:
        os.remove(os.path.join(UPLOADS, name))
    except OSError:
        pass
    return {"ok": True}


@route("DELETE", r"/api/flats/(\d+)")
def delete_flat(h, u, d, fid):
    f = own_flat(u, fid)
    for p in photo_list(f["photos"]):
        try:
            os.remove(os.path.join(UPLOADS, os.path.basename(p)))
        except OSError:
            pass
    q("DELETE FROM flats WHERE id=?", (fid,), commit=True)
    q("DELETE FROM blocked WHERE flat_id=?", (fid,), commit=True)
    return {"ok": True}


@route("GET", r"/api/flats/(\d+)/calendar")
def calendar(h, u, d, fid):
    month = d.get("month") or date.today().strftime("%Y-%m")
    try:
        first = date.fromisoformat(month + "-01")
    except ValueError:
        raise Err("Bad month")
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    booked = set()
    for b in q("SELECT start_day, end_day FROM bookings WHERE flat_id=? AND status='approved' "
               "AND start_day < ? AND end_day > ?", (fid, str(nxt), str(first))):
        s, e = date.fromisoformat(b["start_day"]), date.fromisoformat(b["end_day"])
        while s < e:
            booked.add(str(s))
            s += timedelta(days=1)
    blocked = [r["day"] for r in q("SELECT day FROM blocked WHERE flat_id=? AND day>=? AND day<?",
                                   (fid, str(first), str(nxt)))]
    return {"month": month, "booked": sorted(booked), "blocked": blocked}


@route("POST", r"/api/flats/(\d+)/block")
def block_day(h, u, d, fid):
    own_flat(u, fid)
    day = str(pdate(d.get("day")))
    if d.get("blocked"):
        q("INSERT OR IGNORE INTO blocked VALUES(?,?)", (fid, day), commit=True)
    else:
        q("DELETE FROM blocked WHERE flat_id=? AND day=?", (fid, day), commit=True)
    return {"ok": True}


# ---------------- bookings ----------------
@route("POST", "/api/bookings")
def book(h, u, d):
    need_role(u, "tenant")
    if u["id_status"] != "verified":
        raise Err("Verify your ID proof before sending a request", 403)
    f = q("SELECT * FROM flats WHERE id=? AND active=1 AND bill_status='verified'", (d.get("flat_id"),), one=True)
    if not f:
        raise Err("This flat is not available", 404)
    s = pdate(d.get("start_day"))
    if s < date.today():
        raise Err("Start date cannot be in the past")
    if f["kind"] == "short":
        e = pdate(d.get("end_day"))
        if e <= s or (e - s).days > 30:
            raise Err("Choose an end date after the start date (maximum 30 nights)")
        if not is_free(f["id"], s, e):
            raise Err("Those dates are not available. Check the calendar", 409)
    else:
        e = s
    if q("SELECT 1 FROM bookings WHERE flat_id=? AND tenant_id=? AND status='pending'", (f["id"], u["id"]), one=True):
        raise Err("You already have a pending request for this flat", 409)
    q("INSERT INTO bookings(flat_id,tenant_id,start_day,end_day,note) VALUES(?,?,?,?,?)",
      (f["id"], u["id"], str(s), str(e), (d.get("note") or "")[:300]), commit=True)
    return {"ok": True}


@route("GET", "/api/bookings/mine")
def my_bookings(h, u, d):
    need(u)
    if u["role"] == "tenant":
        rows = q("SELECT b.*, f.title, f.city, f.kind, f.owner_id, o.name owner_name, o.phone owner_phone, o.email owner_email FROM bookings b "
                 "JOIN flats f ON f.id=b.flat_id JOIN users o ON o.id=f.owner_id WHERE b.tenant_id=? "
                 "ORDER BY b.id DESC", (u["id"],))
    elif u["role"] == "owner":
        rows = q("SELECT b.*, f.title, f.city, f.kind, t.name tenant_name, t.phone tenant_phone, t.email tenant_email FROM bookings b "
                 "JOIN flats f ON f.id=b.flat_id JOIN users t ON t.id=b.tenant_id WHERE f.owner_id=? "
                 "ORDER BY b.id DESC", (u["id"],))
        for r in rows:
            r["tenant_rating"] = rating(r["tenant_id"])
            r["tenant_reviews"] = reviews_about(r["tenant_id"])[:5]
    else:
        raise Err("Not available", 403)
    for r in rows:
        if r["status"] != "approved":  # contact details are revealed only after approval
            for k in ("owner_phone", "owner_email", "tenant_phone", "tenant_email"):
                r.pop(k, None)
        r["reviewed"] = bool(q("SELECT 1 FROM reviews WHERE author_id=? AND booking_id=?", (u["id"], r["id"]), one=True))
    return rows


@route("POST", r"/api/bookings/(\d+)/decide")
def decide(h, u, d, bid):
    need(u)
    b = q("SELECT b.*, f.owner_id, f.kind FROM bookings b JOIN flats f ON f.id=b.flat_id WHERE b.id=?", (bid,), one=True)
    if not b:
        raise Err("Request not found", 404)
    act = d.get("action")
    if act in ("approve", "decline") and u["id"] == b["owner_id"] and b["status"] == "pending":
        if act == "decline":
            q("UPDATE bookings SET status='declined' WHERE id=?", (bid,), commit=True)
        else:
            if b["kind"] == "short" and not is_free(b["flat_id"], pdate(b["start_day"]), pdate(b["end_day"])):
                raise Err("Those dates are no longer free", 409)
            q("UPDATE bookings SET status='approved' WHERE id=?", (bid,), commit=True)
            if b["kind"] == "long":
                q("UPDATE flats SET active=0 WHERE id=?", (b["flat_id"],), commit=True)
                q("UPDATE bookings SET status='declined' WHERE flat_id=? AND status='pending'", (b["flat_id"],), commit=True)
    elif act == "cancel" and u["id"] == b["tenant_id"] and b["status"] in ("pending", "approved"):
        q("UPDATE bookings SET status='cancelled' WHERE id=?", (bid,), commit=True)
    else:
        raise Err("This action is not allowed", 403)
    return {"ok": True}


# ---------------- reviews ----------------
@route("GET", "/api/reviews")
def get_reviews(h, u, d):
    t = q("SELECT id, name, role FROM users WHERE id=?", (d.get("user_id"),), one=True)
    if not t:
        raise Err("User not found", 404)
    return {"user": t, "rating": rating(t["id"]), "reviews": reviews_about(t["id"])}


@route("POST", "/api/reviews")
def add_review(h, u, d):
    need(u)
    b = q("SELECT b.*, f.owner_id FROM bookings b JOIN flats f ON f.id=b.flat_id WHERE b.id=?",
          (d.get("booking_id"),), one=True)
    if not b or b["status"] != "approved":
        raise Err("You can review only after an approved booking")
    if u["id"] == b["tenant_id"]:
        target = b["owner_id"]
    elif u["id"] == b["owner_id"]:
        target = b["tenant_id"]
    else:
        raise Err("Not your booking", 403)
    try:
        stars = int(d.get("rating"))
    except (TypeError, ValueError):
        raise Err("Choose a rating from 1 to 5")
    if not 1 <= stars <= 5:
        raise Err("Choose a rating from 1 to 5")
    try:
        q("INSERT INTO reviews(author_id,target_id,booking_id,rating,body,created) VALUES(?,?,?,?,?,?)",
          (u["id"], target, b["id"], stars, (d.get("body") or "")[:300], str(date.today())), commit=True)
    except sqlite3.IntegrityError:
        raise Err("You have already reviewed this booking", 409)
    return {"ok": True}


# ---------------- flatmate squad ----------------
RULES = ["smoking", "pets", "diet", "sleep", "guests"]


@route("GET", "/api/prefs")
def get_prefs(h, u, d):
    need_role(u, "tenant")
    return q("SELECT * FROM prefs WHERE user_id=?", (u["id"],), one=True) or {}


@route("POST", "/api/prefs")
def set_prefs(h, u, d):
    need_role(u, "tenant")
    try:
        budget = int(d.get("budget"))
    except (TypeError, ValueError):
        raise Err("Enter your monthly budget as a number")
    city = (d.get("city") or "").strip()
    if not city or budget <= 0:
        raise Err("Enter city and budget")
    q("INSERT OR REPLACE INTO prefs VALUES(?,?,?,?,?,?,?,?)",
      (u["id"], city, budget, d.get("smoking", "no"), d.get("pets", "no"), d.get("diet", "any"),
       d.get("sleep", "early"), d.get("guests", "rare")), commit=True)
    return {"ok": True}


@route("GET", "/api/squad/matches")
def matches(h, u, d):
    need_role(u, "tenant")
    mine = q("SELECT * FROM prefs WHERE user_id=?", (u["id"],), one=True)
    if not mine:
        raise Err("Save your budget and house rules first")
    out = []
    for o in q("SELECT p.*, t.name FROM prefs p JOIN users t ON t.id=p.user_id "
               "WHERE p.user_id != ? AND lower(p.city)=lower(?)", (u["id"], mine["city"])):
        lo, hi = sorted([mine["budget"], o["budget"]])
        if hi > lo * 1.25:
            continue
        score = int(100 * sum(1 for r in RULES if mine[r] == o[r]) / len(RULES))
        if score >= 60:
            out.append({"user_id": o["user_id"], "name": o["name"], "budget": o["budget"], "score": score,
                        "rules": {r: o[r] for r in RULES}})
    return sorted(out, key=lambda x: -x["score"])


@route("POST", "/api/squads")
def squad_new(h, u, d):
    need_role(u, "tenant")
    mine = q("SELECT * FROM prefs WHERE user_id=?", (u["id"],), one=True)
    if not mine:
        raise Err("Save your budget and house rules first")
    ids = [int(x) for x in (d.get("member_ids") or [])][:5]
    if not ids:
        raise Err("Pick at least one flatmate")
    sid = q("INSERT INTO squads(name,city,created_by) VALUES(?,?,?)",
            ((d.get("name") or "My squad").strip()[:40], mine["city"], u["id"]), commit=True)
    q("INSERT INTO squad_members VALUES(?,?,'joined')", (sid, u["id"]), commit=True)
    for i in ids:
        if q("SELECT 1 FROM users WHERE id=? AND role='tenant'", (i,), one=True):
            q("INSERT OR IGNORE INTO squad_members VALUES(?,?,'invited')", (sid, i), commit=True)
    return {"ok": True}


@route("GET", "/api/squads/mine")
def squads_mine(h, u, d):
    need_role(u, "tenant")
    rows = q("SELECT s.* FROM squads s JOIN squad_members m ON m.squad_id=s.id WHERE m.user_id=? ORDER BY s.id DESC", (u["id"],))
    for s in rows:
        s["members"] = q("SELECT t.id, t.name, m.status, p.budget FROM squad_members m JOIN users t ON t.id=m.user_id "
                         "LEFT JOIN prefs p ON p.user_id=t.id WHERE m.squad_id=?", (s["id"],))
        s["my_status"] = [m["status"] for m in s["members"] if m["id"] == u["id"]][0]
    return rows


@route("POST", r"/api/squads/(\d+)/respond")
def squad_respond(h, u, d, sid):
    need_role(u, "tenant")
    if d.get("accept"):
        q("UPDATE squad_members SET status='joined' WHERE squad_id=? AND user_id=?", (sid, u["id"]), commit=True)
    else:
        q("DELETE FROM squad_members WHERE squad_id=? AND user_id=?", (sid, u["id"]), commit=True)
    return {"ok": True}


@route("GET", r"/api/squads/(\d+)/flats")
def squad_flats(h, u, d, sid):
    need_role(u, "tenant")
    if not q("SELECT 1 FROM squad_members WHERE squad_id=? AND user_id=?", (sid, u["id"]), one=True):
        raise Err("You are not in this squad", 403)
    s = q("SELECT * FROM squads WHERE id=?", (sid,), one=True)
    members = q("SELECT p.budget FROM squad_members m LEFT JOIN prefs p ON p.user_id=m.user_id WHERE m.squad_id=?", (sid,))
    size = len(members)
    budgets = [m["budget"] for m in members if m["budget"]]
    if not budgets:
        raise Err("Members have not saved their budgets yet")
    lowest = min(budgets)
    rows = q("SELECT f.*, o.name owner_name FROM flats f JOIN users o ON o.id=f.owner_id WHERE f.active=1 AND f.kind='long' "
             "AND f.bill_status='verified' AND o.id_status='verified' AND lower(f.city)=lower(?) AND f.bedrooms>=? AND f.rent<=?",
             (s["city"], size, lowest * size))
    for r in rows:
        hide_private(r)
        r["per_person"] = round(r["rent"] / size)
    return {"size": size, "lowest_budget": lowest, "flats": rows}


# ---------------- seed + server ----------------
def seed():
    if q("SELECT 1 FROM users", one=True):
        return

    def mk(role, name, email, pw):
        salt = secrets.token_hex(8)
        return q("INSERT INTO users(role,name,email,phone,salt,pw,id_status) VALUES(?,?,?,?,?,?,'verified')",
                 (role, name, email, "98%08d" % secrets.randbelow(10**8), salt, hash_pw(pw, salt)), commit=True)

    mk("admin", "RentWise Admin", "admin@rentwise.local", "admin123")
    owner = mk("owner", "Ramesh Suresh Patil", "owner@demo.com", "demo123")
    tenants = {}
    for name, email, budget, rules in [
        ("Aarav Mehta", "aarav@demo.com", 15000, ("no", "no", "veg", "early", "rare")),
        ("Neha Kulkarni", "neha@demo.com", 14000, ("no", "no", "veg", "early", "often")),
        ("Rohan Iyer", "rohan@demo.com", 16000, ("no", "no", "veg", "late", "rare")),
        ("Priya Nair", "priya@demo.com", 9000, ("yes", "yes", "nonveg", "late", "often")),
    ]:
        t = mk("tenant", name, email, "demo123")
        tenants[name] = t
        q("INSERT INTO prefs VALUES(?,?,?,?,?,?,?,?)", (t, "Pune", budget) + rules, commit=True)
    q("INSERT INTO flats(owner_id,title,city,area,bedrooms,rent,kind,descr,bill_name,bill_status) VALUES(?,?,?,?,?,?,?,?,?,'verified')",
      (owner, "Spacious 3 BHK near Kothrud", "Pune", "Kothrud", 3, 36000, "long",
       "Semi-furnished, parking, 5 minutes from the metro.", "Ramesh Suresh Patil"), commit=True)
    stay = q("INSERT INTO flats(owner_id,title,city,area,bedrooms,rent,kind,descr,bill_name,bill_status) VALUES(?,?,?,?,?,?,?,?,?,'verified')",
             (owner, "Sunny 2 BHK short stay", "Pune", "Baner", 2, 2800, "short",
              "Fully furnished, Wi-Fi, ideal for 2 to 30 nights.", "Ramesh Suresh Patil"), commit=True)
    neha = tenants["Neha Kulkarni"]
    bid = q("INSERT INTO bookings(flat_id,tenant_id,start_day,end_day,status) VALUES(?,?,?,?,'approved')",
            (stay, neha, "2026-09-01", "2026-09-05"), commit=True)
    q("INSERT INTO reviews(author_id,target_id,booking_id,rating,body,created) VALUES(?,?,?,?,?,?)",
      (owner, neha, bid, 5, "Clean, respectful and left the flat spotless.", "2026-09-06"), commit=True)
    q("INSERT INTO reviews(author_id,target_id,booking_id,rating,body,created) VALUES(?,?,?,?,?,?)",
      (neha, owner, bid, 5, "Exactly as described. Quick replies, no broker fee.", "2026-09-06"), commit=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def user(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        uid = SESSIONS.get(c["tok"].value) if "tok" in c else None
        return q("SELECT * FROM users WHERE id=?", (uid,), one=True) if uid else None

    def send(self, code, obj, headers=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            v = json.loads(self.rfile.read(n))
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}

    def handle_any(self, method):
        p = urlparse(self.path)
        if not p.path.startswith("/api/"):
            with open(os.path.join(BASE, "static", "index.html"), "rb") as f:
                page = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        data = {k: v[0] for k, v in parse_qs(p.query).items()}
        if method != "GET":
            data.update(self.read_body())
        for m, rx, f in ROUTES:
            hit = rx.match(p.path)
            if m == method and hit:
                try:
                    res = f(self, self.user(), data, *hit.groups())
                    if res is None:
                        return
                    if isinstance(res, tuple):
                        self.send(*res)
                    else:
                        self.send(200, res)
                except Err as e:
                    self.send(e.code, {"error": e.msg})
                except Exception as e:
                    self.send(500, {"error": "Server error: %s" % e})
                return
        self.send(404, {"error": "Not found"})

    def do_GET(self):
        self.handle_any("GET")

    def do_POST(self):
        self.handle_any("POST")

    def do_PUT(self):
        self.handle_any("PUT")

    def do_DELETE(self):
        self.handle_any("DELETE")


if __name__ == "__main__":
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    cols = [r[1] for r in c.execute("PRAGMA table_info(flats)")]
    if "bill_status" not in cols:
        c.execute("ALTER TABLE flats ADD COLUMN bill_name TEXT")
        c.execute("ALTER TABLE flats ADD COLUMN bill_file TEXT")
        c.execute("ALTER TABLE flats ADD COLUMN bill_status TEXT DEFAULT 'verified'")
        if "reg_name" in cols:
            c.execute("UPDATE flats SET bill_name=reg_name")
        c.commit()
    if "photos" not in cols:
        c.execute("ALTER TABLE flats ADD COLUMN photos TEXT DEFAULT '[]'")
        c.commit()
    c.close()
    seed()
    print("RentWise Phase 4 and 5 running at http://localhost:%d  (Ctrl+C to stop)" % PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
