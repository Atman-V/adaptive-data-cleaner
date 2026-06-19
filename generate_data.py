"""
Synthetic data generator using Python builtins only.
Generates all 6 source CSV files into data/raw/.
"""

import csv
import random
import hashlib
import datetime
import os
import string

random.seed(42)

RAW_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")
os.makedirs(RAW_DIR, exist_ok=True)

N = 50_000

# ── helpers ──────────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda",
    "William","Barbara","David","Susan","Richard","Jessica","Joseph","Sarah",
    "Thomas","Karen","Charles","Lisa","Christopher","Nancy","Daniel","Betty",
    "Matthew","Margaret","Anthony","Sandra","Mark","Ashley","Donald","Dorothy",
    "Steven","Kimberly","Paul","Emily","Andrew","Donna","Joshua","Michelle",
    "Kenneth","Carol","Kevin","Amanda","Brian","Melissa","George","Deborah",
    "Timothy","Stephanie","Ronald","Rebecca","Edward","Sharon","Jason","Laura",
    "Jeffrey","Cynthia","Ryan","Kathleen","Jacob","Amy","Gary","Angela",
    "Nicholas","Shirley","Eric","Anna","Jonathan","Brenda","Stephen","Pamela",
    "Larry","Emma","Justin","Nicole","Scott","Helen","Brandon","Samantha",
    "Frank","Katherine","Raymond","Christine","Gregory","Debra","Samuel","Rachel",
    "Patrick","Carolyn","Benjamin","Janet","Jack","Catherine","Dennis","Maria",
    "Jerry","Heather","Alexander","Diane",
]

LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
    "Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson",
    "Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White",
    "Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker","Young",
    "Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores","Green",
    "Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts",
]

DOMAINS = ["gmail.com","yahoo.com","outlook.com","hotmail.com","icloud.com",
           "proton.me","live.com","aol.com","zoho.com","fastmail.com"]

CITIES = ["New York","Los Angeles","Chicago","Houston","Phoenix","Philadelphia",
          "San Antonio","San Diego","Dallas","San Jose","Austin","Jacksonville",
          "Fort Worth","Columbus","Charlotte","Indianapolis","San Francisco",
          "Seattle","Denver","Nashville","Oklahoma City","El Paso","Boston",
          "Portland","Las Vegas","Louisville","Baltimore","Milwaukee","Albuquerque",
          "Tucson","Fresno","Sacramento","Mesa","Kansas City","Atlanta","Omaha",
          "Colorado Springs","Raleigh","Miami","Long Beach","Virginia Beach",
          "Minneapolis","Tampa","New Orleans","Arlington","Bakersfield","Anaheim",
          "Aurora","Honolulu","Santa Ana"]

COUNTRIES = ["US","US","US","US","US","CA","CA","GB","GB","AU","DE","FR","IN","IN","BR","MX"]

ACCOUNT_TYPES = ["Standard","Premium","Business","Enterprise","Trial"]
CURRENCIES = ["USD","USD","USD","USD","EUR","GBP","CAD","AUD","JPY","INR"]
TXN_TYPES   = ["Purchase","Refund","Transfer","Withdrawal","Deposit","Fee"]
TXN_STATUSES = ["Completed","Completed","Completed","Pending","Failed","Cancelled"]
MERCHANTS   = ["Amazon","Walmart","Target","Apple","Netflix","Uber","DoorDash",
               "Starbucks","McDonald's","CVS","Walgreens","Best Buy","Home Depot",
               "Costco","Nike","Adidas","Steam","Spotify","Airbnb","Lyft"]

DEPARTMENTS = ["Engineering","Marketing","Sales","Finance","HR","Operations",
               "Legal","Product","Customer Success","Data","Design","Security"]
DESIGNATIONS = ["Analyst","Senior Analyst","Manager","Senior Manager","Director",
                "VP","Associate","Lead","Principal","Coordinator","Specialist","Head"]
PERF_SCORES  = [1,2,3,3,3,4,4,4,4,5]

CATEGORIES = ["Electronics","Clothing","Home & Garden","Sports","Books","Toys",
              "Automotive","Food & Beverage","Health & Beauty","Office Supplies"]
SUBCATEGORIES = {
    "Electronics": ["Laptops","Phones","Tablets","TVs","Cameras","Audio"],
    "Clothing":    ["Shirts","Pants","Shoes","Jackets","Accessories","Sportswear"],
    "Home & Garden": ["Furniture","Decor","Tools","Kitchen","Bedding","Lighting"],
    "Sports":      ["Fitness","Outdoor","Team Sports","Water Sports","Winter","Cycling"],
    "Books":       ["Fiction","Non-Fiction","Science","History","Self-Help","Comics"],
    "Toys":        ["Action Figures","Board Games","Puzzles","Educational","Dolls","RC"],
    "Automotive":  ["Parts","Accessories","Tools","Electronics","Fluids","Tires"],
    "Food & Beverage": ["Snacks","Beverages","Organic","Frozen","Canned","Bakery"],
    "Health & Beauty": ["Skincare","Haircare","Vitamins","Supplements","Makeup","Dental"],
    "Office Supplies": ["Paper","Pens","Furniture","Tech","Filing","Mailing"],
}
SUPPLIERS = ["SupplierOne","MegaDistrib","QuickShip","GlobalSource","EastTrade",
             "NorthSupply","FastGoods","ProVendor","TrustCo","PrimeMfg"]

LOCATIONS = ["Zone-A","Zone-B","Zone-C","Zone-D","Zone-E","Warehouse-1",
             "Warehouse-2","Field-North","Field-South","Remote-01"]

ACTIONS = ["LOGIN","LOGOUT","CREATE","UPDATE","DELETE","VIEW","EXPORT","IMPORT","APPROVE","REJECT"]
ENTITIES = ["Customer","Transaction","Product","Employee","Report","Invoice","Order","Contract"]
IP_PREFIXES = ["192.168","10.0","172.16","203.45","198.51","45.33","104.21","178.62"]


def rnd_date(start_year=2015, end_year=2024):
    start = datetime.date(start_year, 1, 1)
    end   = datetime.date(end_year, 12, 31)
    delta = (end - start).days
    return (start + datetime.timedelta(days=random.randint(0, delta))).isoformat()


def rnd_ts(start_year=2023, end_year=2024):
    dt = datetime.datetime(start_year, 1, 1) + datetime.timedelta(
        seconds=random.randint(0, int((datetime.datetime(end_year+1,1,1)-datetime.datetime(start_year,1,1)).total_seconds()))
    )
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def rnd_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def rnd_email(name):
    parts = name.lower().split()
    sep   = random.choice([".", "_", ""])
    tag   = random.choice(["", str(random.randint(1, 999))])
    return f"{parts[0]}{sep}{parts[1]}{tag}@{random.choice(DOMAINS)}"


def rnd_phone():
    return f"+1-{random.randint(200,999)}-{random.randint(200,999)}-{random.randint(1000,9999)}"


def rnd_address():
    num  = random.randint(1, 9999)
    dirs = ["N","S","E","W","NE","NW","SE","SW",""]
    types= ["St","Ave","Blvd","Rd","Ln","Dr","Ct","Way","Pl","Cir"]
    street_names = ["Main","Oak","Maple","Cedar","Pine","Elm","Washington","Lincoln",
                    "Park","Lake","Hill","River","Sunset","Spring","Meadow","Forest"]
    return f"{num} {random.choice(dirs)} {random.choice(street_names)} {random.choice(types)}"


def null_maybe(value, pct):
    return "" if random.random() < pct else value


def duplicate_rows(rows, pct):
    n_dup = int(len(rows) * pct)
    dups  = random.choices(rows, k=n_dup)
    combined = rows + dups
    random.shuffle(combined)
    return combined[:len(rows)]   # keep total at N


# ── 1. customer_profiles.csv ─────────────────────────────────────────────────

def gen_customer_profiles():
    print("  Generating customer_profiles.csv …")
    rows = []
    for i in range(1, N + 1):
        name  = rnd_name()
        email = rnd_email(name)
        dob   = rnd_date(1950, 2005)
        row   = [
            f"CUST{i:06d}",
            name,
            null_maybe(email, 0.02),
            null_maybe(rnd_phone(), 0.03),
            dob,
            rnd_address(),
            random.choice(CITIES),
            random.choice(COUNTRIES),
            random.choice(ACCOUNT_TYPES),
            rnd_date(2018, 2024),
        ]
        rows.append(row)
    rows = duplicate_rows(rows, 0.015)
    header = ["customer_id","full_name","email","phone","dob","address",
              "city","country","account_type","created_at"]
    path = os.path.join(RAW_DIR, "customer_profiles.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"    → {len(rows):,} rows")


# ── 2. transaction_logs.csv ──────────────────────────────────────────────────

def gen_transaction_logs():
    print("  Generating transaction_logs.csv …")
    rows = []
    for i in range(1, N + 1):
        cust_id = f"CUST{random.randint(1, N):06d}"
        amount  = 0 if random.random() < 0.008 else round(random.uniform(0.5, 50000), 2)
        merchant = null_maybe(random.choice(MERCHANTS), 0.02)
        row = [
            f"TXN{i:07d}",
            cust_id,
            amount,
            random.choice(CURRENCIES),
            rnd_date(2023, 2024),
            random.choice(TXN_TYPES),
            merchant,
            random.choice(TXN_STATUSES),
            f"{''.join(random.choices(string.digits, k=12))}",
            f"{''.join(random.choices(string.digits, k=4))}",
        ]
        rows.append(row)
    header = ["txn_id","customer_id","amount","currency","txn_date","txn_type",
              "merchant","status","account_number","card_last4"]
    path = os.path.join(RAW_DIR, "transaction_logs.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"    → {len(rows):,} rows")


# ── 3. hr_records.csv ────────────────────────────────────────────────────────

def gen_hr_records():
    print("  Generating hr_records.csv …")
    rows = []
    for i in range(1, N + 1):
        name  = rnd_name()
        email = rnd_email(name)
        mgr   = null_maybe(f"EMP{random.randint(1, 10000):05d}", 0.04)
        row = [
            f"EMP{i:05d}",
            name,
            email,
            random.choice(DEPARTMENTS),
            random.choice(DESIGNATIONS),
            round(random.uniform(30000, 250000), 2),
            rnd_date(2010, 2024),
            mgr,
            random.choice(PERF_SCORES),
            random.choice([1, 1, 1, 0]),
        ]
        rows.append(row)
    header = ["emp_id","full_name","email","department","designation","salary",
              "join_date","manager_id","performance_score","is_active"]
    path = os.path.join(RAW_DIR, "hr_records.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"    → {len(rows):,} rows")


# ── 4. product_catalog.csv ───────────────────────────────────────────────────

def gen_product_catalog():
    print("  Generating product_catalog.csv …")
    rows = []
    for i in range(1, N + 1):
        cat  = random.choice(CATEGORIES)
        subs = SUBCATEGORIES.get(cat, ["General"])
        row  = [
            f"PROD{i:06d}",
            f"Product {random.choice(string.ascii_uppercase)}{random.randint(100,9999)}",
            cat,
            random.choice(subs),
            round(random.uniform(0.99, 4999.99), 2),
            random.randint(0, 5000),
            random.choice(SUPPLIERS),
            rnd_date(2023, 2024),
        ]
        rows.append(row)
    header = ["product_id","product_name","category","sub_category","price",
              "stock_qty","supplier","last_updated"]
    path = os.path.join(RAW_DIR, "product_catalog.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"    → {len(rows):,} rows")


# ── 5. sensor_telemetry.csv ──────────────────────────────────────────────────

def gen_sensor_telemetry():
    print("  Generating sensor_telemetry.csv …")
    rows = []
    for i in range(1, N + 1):
        is_anomaly = random.random() < 0.05
        if is_anomaly:
            temp = round(random.choice([random.uniform(81, 120), random.uniform(-20, -11)]), 2)
        else:
            temp = round(random.uniform(-10, 80), 2)
        humidity = round(random.uniform(10, 95), 2)
        pressure = round(random.uniform(950, 1050), 2)
        battery  = null_maybe(round(random.uniform(5, 100), 2), 0.03)
        alert    = 1 if (is_anomaly or humidity > 90 or float(battery or 50) < 10) else 0
        row = [
            f"SENS{i:06d}",
            rnd_ts(2023, 2024),
            random.choice(LOCATIONS),
            temp,
            humidity,
            pressure,
            battery,
            alert,
        ]
        rows.append(row)
    header = ["sensor_id","timestamp","location","temperature","humidity",
              "pressure","battery_pct","alert_flag"]
    path = os.path.join(RAW_DIR, "sensor_telemetry.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"    → {len(rows):,} rows")


# ── 6. audit_trail.csv ───────────────────────────────────────────────────────

def gen_audit_trail():
    print("  Generating audit_trail.csv …")
    rows = []
    for i in range(1, N + 1):
        ip = f"{random.choice(IP_PREFIXES)}.{random.randint(1,254)}.{random.randint(1,254)}"
        row = [
            f"AUD{i:07d}",
            f"USR{random.randint(1,5000):05d}",
            random.choice(ACTIONS),
            random.choice(ENTITIES),
            f"ENT{random.randint(1,N):06d}",
            ip,
            rnd_ts(2023, 2024),
            random.choice(["SUCCESS","SUCCESS","SUCCESS","FAILED","BLOCKED"]),
        ]
        rows.append(row)
    header = ["audit_id","user_id","action","entity","entity_id",
              "ip_address","timestamp","status"]
    path = os.path.join(RAW_DIR, "audit_trail.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"    → {len(rows):,} rows")


if __name__ == "__main__":
    print("Generating synthetic data …")
    gen_customer_profiles()
    gen_transaction_logs()
    gen_hr_records()
    gen_product_catalog()
    gen_sensor_telemetry()
    gen_audit_trail()
    print("Done — all 6 CSV files written to data/raw/")
