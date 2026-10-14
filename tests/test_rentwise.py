import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

os.environ["RENTWISE_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from rentwise import listings, search  # noqa: E402
from rentwise.foundation import NotFound, ValidationError, init_db  # noqa: E402
from rentwise.seed import seed_if_empty  # noqa: E402
from rentwise.server import make_server  # noqa: E402

GOOD = {"title": "Test 2 BHK flat", "city": "Nashik", "locality": "College Road", "rent": 18000,
        "bedrooms": 2, "property_type": "apartment", "furnishing": "furnished",
        "owner_name": "Test Owner", "owner_phone": "+91 98765 43210", "amenities": ["wifi", "lift"]}


def setUpModule():
    init_db()
    seed_if_empty()


class Phase2Listings(unittest.TestCase):
    def test_create_and_get(self):
        made = listings.create_listing(GOOD)
        self.assertEqual(made["owner_phone"], "9876543210")
        self.assertEqual(made["deposit"], 0)
        self.assertEqual(listings.get_listing(made["id"])["title"], GOOD["title"])

    def test_validation_collects_all_errors(self):
        with self.assertRaises(ValidationError) as cm:
            listings.create_listing({"title": "x", "rent": "abc", "owner_phone": "123"})
        self.assertGreaterEqual(len(cm.exception.errors), 5)

    def test_update_and_delete(self):
        made = listings.create_listing(GOOD)
        self.assertEqual(listings.update_listing(made["id"], {"rent": 20000})["rent"], 20000)
        listings.delete_listing(made["id"])
        with self.assertRaises(NotFound):
            listings.get_listing(made["id"])


class Phase3Search(unittest.TestCase):
    def test_city_and_rent_filters(self):
        r = search.search_listings({"city": "pune", "max_rent": "25000"})
        self.assertTrue(r["total"] >= 2)
        self.assertTrue(all(i["city"] == "Pune" and i["rent"] <= 25000 for i in r["items"]))

    def test_bedrooms_and_amenities(self):
        r = search.search_listings({"bedrooms": "2", "amenities": "lift,balcony"})
        self.assertTrue(r["total"] >= 1)
        for i in r["items"]:
            self.assertEqual(i["bedrooms"], 2)
            self.assertTrue({"lift", "balcony"} <= set(i["amenities"]))

    def test_sort_and_paging(self):
        a = search.search_listings({"sort": "rent_asc", "limit": "3", "page": "1"})
        b = search.search_listings({"sort": "rent_asc", "limit": "3", "page": "2"})
        rents = [i["rent"] for i in a["items"] + b["items"]]
        self.assertEqual(rents, sorted(rents))
        self.assertEqual(len(a["items"]), 3)

    def test_bad_input_rejected(self):
        with self.assertRaises(ValidationError):
            search.search_listings({"min_rent": "cheap"})
        with self.assertRaises(ValidationError):
            search.search_listings({"amenities": "jacuzzi"})


class HttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = make_server(0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, path, method="GET", body=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_page_and_search(self):
        code, html = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn(b"RentWise", html)
        code, body = self.call("/api/listings?city=Guwahati")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(json.loads(body)["total"], 3)

    def test_create_bad_and_missing(self):
        code, body = self.call("/api/listings", "POST", {"title": "no"})
        self.assertEqual(code, 400)
        self.assertIn("errors", json.loads(body))
        self.assertEqual(self.call("/api/listings/999999")[0], 404)

    def test_create_then_find(self):
        code, body = self.call("/api/listings", "POST", {**GOOD, "city": "Nagpur"})
        self.assertEqual(code, 201)
        code, body = self.call("/api/listings?city=Nagpur")
        self.assertEqual(json.loads(body)["total"], 1)


if __name__ == "__main__":
    unittest.main()
