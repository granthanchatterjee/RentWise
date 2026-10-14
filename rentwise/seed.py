"""Sample listings, loaded once when the database is empty."""
from .foundation import db
from .listings import create_listing

KEYS = ("title", "city", "locality", "rent", "deposit", "bedrooms", "bathrooms", "area_sqft",
        "property_type", "furnishing", "amenities", "owner_name", "owner_phone", "description")

SAMPLES = [
    ("Bright 2 BHK near the river", "Pune", "Baner", 24000, 48000, 2, 2, 980, "apartment",
     "semi_furnished", ["parking", "lift", "power_backup", "balcony"], "Anil Deshmukh", "9822011001",
     "Fourth-floor corner flat with cross ventilation, ten minutes from the IT park."),
    ("Compact studio for one", "Pune", "Kothrud", 11500, 23000, 0, 1, 380, "studio",
     "furnished", ["wifi", "ac", "security"], "Meera Joshi", "9822011002",
     "Furnished studio with a kitchenette, quiet lane, walkable to the market."),
    ("Spacious 3 BHK with parking", "Pune", "Wakad", 32000, 64000, 3, 3, 1450, "apartment",
     "unfurnished", ["parking", "lift", "gym", "security", "power_backup"], "Rahul Kulkarni",
     "9822011003", "Gated society, two covered parking spots, family preferred."),
    ("1 BHK close to the metro", "Pune", "Hinjewadi", 15000, 30000, 1, 1, 560, "apartment",
     "semi_furnished", ["wifi", "lift", "water_24x7"], "Sneha Patil", "9822011004",
     "Ideal for a working professional, five minutes from the metro station."),
    ("Independent house with garden", "Guwahati", "Beltola", 21000, 42000, 3, 2, 1600,
     "independent_house", "unfurnished", ["parking", "pet_friendly", "water_24x7"], "Dipankar Baruah",
     "9854011005", "Ground-plus-one house with a small garden and a covered porch."),
    ("2 BHK in a quiet lane", "Guwahati", "Zoo Road", 17000, 34000, 2, 2, 900, "apartment",
     "furnished", ["wifi", "ac", "lift", "power_backup"], "Mamoni Das", "9854011006",
     "Fully furnished, near the college and the hospital, power backup included."),
    ("Single room in a shared flat", "Guwahati", "Ganeshguri", 6500, 13000, 1, 1, 180, "pg_room",
     "furnished", ["wifi", "security"], "Pranjal Sarma", "9854011007",
     "Room in a three-person flat, meals optional, students welcome."),
    ("Modern 2 BHK sea breeze", "Mumbai", "Andheri West", 52000, 156000, 2, 2, 860, "apartment",
     "furnished", ["lift", "security", "ac", "gym"], "Farah Shaikh", "9820011008",
     "Eleventh floor, modular kitchen, walking distance to the station."),
    ("Budget 1 BHK", "Mumbai", "Thane West", 22000, 66000, 1, 1, 520, "apartment",
     "unfurnished", ["lift", "water_24x7"], "Vivek Naik", "9820011009",
     "Well-kept 1 BHK in an older society, close to schools and the market."),
    ("3 BHK villa with terrace", "Bengaluru", "Whitefield", 68000, 204000, 3, 3, 2100, "villa",
     "semi_furnished", ["parking", "gym", "security", "power_backup", "pet_friendly"], "Lakshmi Rao",
     "9880011010", "Private terrace, club access, pets allowed."),
    ("Studio near the tech park", "Bengaluru", "Bellandur", 19000, 57000, 0, 1, 450, "studio",
     "furnished", ["wifi", "ac", "lift", "security"], "Karthik Reddy", "9880011011",
     "Move-in ready studio with a work desk, ten minutes from the tech park."),
    ("2 BHK with balcony and lift", "Bengaluru", "Koramangala", 38000, 114000, 2, 2, 1050,
     "apartment", "semi_furnished", ["lift", "balcony", "parking", "power_backup"], "Divya Menon",
     "9880011012", "Tree-lined street, cafes and a park within walking distance."),
]


def seed_if_empty():
    with db() as c:
        if c.execute("SELECT COUNT(*) FROM listings").fetchone()[0]:
            return 0
    for row in SAMPLES:
        create_listing(dict(zip(KEYS, row)))
    return len(SAMPLES)
