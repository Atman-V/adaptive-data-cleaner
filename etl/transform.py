"""
etl/transform.py — Step 3: Apply business rules (fast rebuild approach).
Reads curated table, computes derived columns, rewrites table.
"""
import sqlite3, datetime, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "warehouse.db")

FX_RATES = {"USD":1.0,"EUR":1.09,"GBP":1.27,"CAD":0.74,"AUD":0.66,"JPY":0.0067,"INR":0.012}
IP_MAP   = {"192":"US","10":"US","172":"US","203":"AU","198":"GB","45":"US","104":"DE","178":"FR"}

def _age(dob):
    if not dob: return "Unknown"
    try:
        d = datetime.date.fromisoformat(str(dob)[:10])
        a = (datetime.date.today()-d).days//365
        if a<18: return "Under 18"
        if a<=25: return "18-25"
        if a<=40: return "26-40"
        if a<=60: return "41-60"
        return "60+"
    except: return "Unknown"

def _tenure(jd):
    if not jd: return None
    try: return round((datetime.date.today()-datetime.date.fromisoformat(str(jd)[:10])).days/365.25,2)
    except: return None

def _ipc(ip):
    return IP_MAP.get(str(ip).split(".")[0],"Unknown") if ip else "Unknown"

def _rebuild(conn, table, extra_fn, extra_cols):
    """Read all rows, add/update extra columns, delete+reinsert."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    all_cols = [r[1] for r in cur.fetchall()]
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    col_idx = {c:i for i,c in enumerate(all_cols)}
    
    new_rows = []
    for row in rows:
        row = list(row)
        extras = extra_fn(row, col_idx)
        for col, val in extras.items():
            row[col_idx[col]] = val
        new_rows.append(tuple(row))
    
    conn.execute(f"DELETE FROM {table}")
    ph = ",".join(["?"]*len(all_cols))
    conn.executemany(f"INSERT INTO {table} VALUES ({ph})", new_rows)
    conn.commit()
    return len(new_rows)

def transform_all(conn=None):
    close_after = conn is None
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
    results = {}

    # 1. transaction_logs → amount_usd
    def txn_fn(row, idx):
        cur = row[idx.get("currency","")]
        rate = FX_RATES.get(str(cur).upper(), 1.0)
        try: usd = round(float(row[idx["amount"]] or 0)*rate, 2)
        except: usd = None
        return {"amount_usd": usd}
    n = _rebuild(conn, "curated_transaction_logs", txn_fn, ["amount_usd"])
    results["transaction_logs"] = n
    print(f"  [TRANSFORM] transaction_logs: {n:,} rows → amount_usd set")

    # 2. customer_profiles → age_group
    def cust_fn(row, idx):
        return {"age_group": _age(row[idx["dob"]])}
    n = _rebuild(conn, "curated_customer_profiles", cust_fn, ["age_group"])
    results["customer_profiles"] = n
    print(f"  [TRANSFORM] customer_profiles: {n:,} rows → age_group set")

    # 3. hr_records → tenure_years
    def hr_fn(row, idx):
        return {"tenure_years": _tenure(row[idx["join_date"]])}
    n = _rebuild(conn, "curated_hr_records", hr_fn, ["tenure_years"])
    results["hr_records"] = n
    print(f"  [TRANSFORM] hr_records: {n:,} rows → tenure_years set")

    # 4. sensor_telemetry → is_anomaly (SQL is fine)
    conn.execute("""
        UPDATE curated_sensor_telemetry SET is_anomaly =
        CASE WHEN CAST(temperature AS REAL)>80 OR CAST(temperature AS REAL)<-10 THEN 1 ELSE 0 END
    """)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM curated_sensor_telemetry").fetchone()[0]
    results["sensor_telemetry"] = n
    print(f"  [TRANSFORM] sensor_telemetry: {n:,} rows → is_anomaly set")

    # 5. audit_trail → ip_country
    def audit_fn(row, idx):
        return {"ip_country": _ipc(row[idx["ip_address"]])}
    n = _rebuild(conn, "curated_audit_trail", audit_fn, ["ip_country"])
    results["audit_trail"] = n
    print(f"  [TRANSFORM] audit_trail: {n:,} rows → ip_country set")

    if close_after:
        conn.close()
    return results

if __name__ == "__main__":
    transform_all()
