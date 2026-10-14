# RentWise: Phase 2 + Phase 3 demo

Broker-free flat rental system. This build adds **Phase 2 (listing flats)** and **Phase 3 (searching and retrieving flats)**, with a clickable demo page.

Needs Python 3.9 or newer. No packages to install.

## Run it

- **Windows:** double-click `run.bat`, or in the VS Code terminal run `python run.py`
- **Mac/Linux:** `./run.sh` or `python3 run.py`

Your browser opens at http://127.0.0.1:8000/. The first run loads 11 sample flats so the search has something to show. The data lives in `rentwise.db` next to `run.py`; delete that file to start fresh.

## What to show your supervisor

1. **Find a flat**: filter by city, locality, rent range, bedrooms, property type, furnishing and amenities. Sort by rent or newest. Click a flat to see the full details and the owner's phone number.
2. **List your flat**: fill the form and publish. Try leaving fields empty or entering a bad phone number to show validation. The new flat appears in search straight away.

## Project layout

| File | Purpose |
|---|---|
| `rentwise/foundation.py` | Database, schema, validation (stand-in for Phase 1) |
| `rentwise/listings.py` | **Phase 2**: create, read, update, delete listings |
| `rentwise/search.py` | **Phase 3**: filters, sorting, paging |
| `rentwise/server.py` | HTTP server and API routes |
| `rentwise/seed.py` | Sample data |
| `web/index.html` | Demo page |
| `tests/test_rentwise.py` | 10 automated tests: `python -m unittest discover tests -v` |

If your own Phase 1 code is different, keep these names and swap the internals of `foundation.py`: `db()`, `init_db()`, `validate_listing()`, `ValidationError`, `NotFound`.

## API

| Method and path | What it does |
|---|---|
| `POST /api/listings` | Create a listing (returns 201, or 400 with a list of errors) |
| `GET /api/listings` | Search. Query options: `q`, `city`, `locality`, `min_rent`, `max_rent`, `bedrooms` (0 = studio, 4 = four or more), `property_type`, `furnishing`, `amenities` (comma list, all must match), `sort` (`newest`, `rent_asc`, `rent_desc`), `page`, `limit` |
| `GET /api/listings/<id>` | Retrieve one flat |
| `PUT /api/listings/<id>` | Update any fields |
| `DELETE /api/listings/<id>` | Remove a listing (soft delete) |
| `GET /api/meta` | Cities and choices used by the filters |

## Optional: build a single .exe (Windows)

```
pip install pyinstaller
pyinstaller --onefile --add-data "web;web" run.py
```

The file appears in `dist\run.exe`. It creates `rentwise.db` next to itself.

## Next three phases (proposed)

**Phase 4: Accounts and trust.** Owner and tenant sign-up and login, so owners manage only their own listings. Two-way reviews: future tenants can read owner reviews, and owners can see a tenant's reviews before finalising.

**Phase 5: More ways to rent.** Short-term rentals, Airbnb style (nightly price, availability calendar, booking requests). Flatmate Squads: group single tenants with similar budgets and house rules, then match the squad to multi-bedroom flats. The `rental_type` column is already in the database for this.

**Phase 6: Polish and deployment.** Final interface, security hardening (passwords, input limits), more tests, and deployment on a virtual machine with the app running as a service.
