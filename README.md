# RentWise: Broker-Free Flat Rental System (Phase 6 Integrated)

RentWise is a broker-free flat rental matching engine and property management platform. This repository contains the fully integrated Phase 6 prototype, completing core property listing functionalities, media asset management, trust verification protocols, and algorithmic tenant matching.

Architected entirely on Python's standard library (`http.server`, `sqlite3`), this system deliberately avoids bloated external web frameworks (such as Django or Flask) to demonstrate raw HTTP request handling, local relational database management, and custom deterministic algorithm design from first principles.

## Local Setup & Execution

**Prerequisites:** Python 3.9 or newer. The environment is strictly dependency-free; no external packages, virtual environments, or `pip install` commands are required.

1. **Initialize the Server:** 
   - **Windows Environments:** Execute `run_phase6.bat` or run `python server.py` directly in your terminal.
   - **Unix/Linux/macOS:** Run `python3 server.py`
2. **Access the Interface:** Navigate to `http://localhost:8000/` in any standard web browser.
3. **Database Generation:** Upon the first execution, the Python backend automatically provisions the local SQLite database, executes the schema creation scripts, and injects sample demo data for immediate testing. To perform a hard factory reset, manually delete the `.db` file and restart the server instance.

### Role-Based Demo Credentials
To evaluate the isolated session states and role-specific UI routing, utilize the following pre-configured database credentials:
- **System Administrator (KYC / ID Verification):** `admin@rentwise.local` / `admin123`
- **Property Owner (Listing Management):** `owner@demo.com` / `demo123`
- **Tenants (Bookings & Squad Matching):** `aarav@demo.com` or `neha@demo.com` / `demo123`

---

## System Architecture & Matching Algorithms

To handle complex tenant requirements without relying on opaque, non-deterministic AI models, the system implements a **Deterministic Percentage-Matching Engine**.

### 1. Flatmate Squad Engine
To programmatically solve the affordability gap for single tenants, the system executes an automated grouping sequence to match compatible users for multi-bedroom rentals. The algorithm executes in three strict phases:
1. **Hard Geographical & Financial Constraints:** Instantly filters out candidates residing in different target cities. It then applies a strict financial ceiling formula (`lower_budget * 1.25`) to ensure the higher budget candidate does not exceed the lower candidate's budget by more than 25%.
2. **Soft Constraint Scoring Matrix:** For candidates passing the hard constraints, the system calculates a percentage score based on 5 boolean lifestyle variables (Smoking, Pets, Diet, Sleep Schedule, Guests). Each alignment adds a 20% weight to the total compatibility score.
3. **Algorithmic Thresholding:** The engine automatically discards any pairing scoring below the 60% minimum threshold, returning a localized, sorted array of highly compatible flatmates.

### 2. Trust, Security & Media Architecture
- **KYC & Utility Verification:** Identity proofs and electricity bills are uploaded directly to the local `uploads/` directory. The user account and property listings are placed in restrictive `pending` states until the System Administrator manually validates the documents via the admin portal.
- **Media Optimization:** To prevent server bloat, property photos uploaded by owners undergo automatic client-side canvas compression (downscaled to a maximum of 1200px and converted to optimized JPEG format) prior to binary transmission and storage.
- **Cryptographic Security:** User authentication avoids plaintext storage entirely. All passwords are encrypted during account creation using PBKDF2 hashing algorithms with 100,000 iterations and dynamically generated unique salts.

---

## Core State Machine Constraints

To maintain data integrity and prevent platform abuse, the backend enforces a strictly linear booking lifecycle using hardcoded state transitions:
- **`pending`**: Initial state, awaiting property owner decision.
- **`approved`**: Terminal success state. This cryptographic state change is the sole trigger that unlocks the Two-Way Review logic, ensuring users can only review flats they have verifiably booked.
- **`declined` / `cancelled`**: Terminal failure state. Permanently locks the booking record in the SQLite database to prevent subsequent modification or spam API requests.

---

## Project Directory Layout

| File / Directory | Architectural Purpose |
|---|---|
| `server.py` | Core monolithic backend engine handling HTTP routing, matching algorithms, JSON API endpoints, media uploads, and direct SQL queries. |
| `static/index.html` | Frontend UI wireframe utilizing vanilla JavaScript to bridge client interactions to the JSON API, including client-side image compression logic. |
| `rentwise.db` | Auto-generated local SQLite database storing all persistent platform states, hashed user credentials, image paths, and active listings. |
| `uploads/` | Dedicated local directory for storing binary data (pending KYC documents, utility bills, and property listing photos). |
| `run_phase6.bat` | Quick-start execution script optimized for Windows command-line environments. |

---

## Known Prototype Limitations
- **Session Persistence:** User authentication sessions are currently managed via a volatile RAM dictionary (`SESSIONS`). A server reboot will intentionally flush all active login tokens to facilitate rapid testing.
- **Concurrency & Scaling:** The system utilizes local SQLite. While optimal for demonstrating dependency-free architecture in a controlled environment, production deployment will necessitate migration to a concurrent relational database (e.g., PostgreSQL) to handle parallel transactional writes and dedicated cloud storage (e.g., AWS S3) for media assets.

---

## Development Roadmap

- [x] **Phase 1-3: Core Engine.** Local SQLite database provisioning, RESTful CRUD operations, and strict SQL search filtering.
- [x] **Phase 4: Accounts and Trust.** Role-based session management, Admin ID verification, electricity consumer validation, and conditional Two-Way Reviews.
- [x] **Phase 5: More Ways to Rent.** Short-term availability scheduling and the multi-variable Flatmate Squad matching algorithm.
- [x] **Phase 6: Media Management.** Property photo uploads, dynamic client-side image compression, and gallery rendering.