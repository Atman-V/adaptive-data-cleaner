"""
etl/cleanse.py — Step 2: Clean, deduplicate, normalize raw_ tables → curated_ tables.
"""

import sqlite3
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "warehouse.db")

# Map raw → curated, plus which column is the primary key
TABLE_MAP = {
    "raw_customer_profiles": ("curated_customer_profiles", "customer_id"),
    "raw_transaction_logs":  ("curated_transaction_logs",  "txn_id"),
    "raw_hr_records":        ("curated_hr_records",        "emp_id"),
    "raw_product_catalog":   ("curated_product_catalog",   "product_id"),
    "raw_sensor_telemetry":  ("curated_sensor_telemetry",  "sensor_id"),
    "raw_audit_trail":       ("curated_audit_trail",       "audit_id"),
}

# Columns to carry into curated tables (no pipeline meta columns)
CURATED_COLS = {
    "curated_customer_profiles": ["customer_id","full_name","email","phone","dob",
                                   "address","city","country","account_type","created_at"],
    "curated_transaction_logs":  ["txn_id","customer_id","amount","currency","txn_date",
                                   "txn_type","merchant","status","account_number","card_last4"],
    "curated_hr_records":        ["emp_id","full_name","email","department","designation",
                                   "salary","join_date","manager_id","performance_score","is_active"],
    "curated_product_catalog":   ["product_id","product_name","category","sub_category",
                                   "price","stock_qty","supplier","last_updated"],
    "curated_sensor_telemetry":  ["sensor_id","timestamp","location","temperature",
                                   "humidity","pressure","battery_pct","alert_flag"],
    "curated_audit_trail":       ["audit_id","user_id","action","entity","entity_id",
                                   "ip_address","timestamp","status"],
}


def _fetch_rows(conn, table):
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    cur2 = conn.execute(f"SELECT * FROM {table}")
    return cols, [dict(zip(cols, r)) for r in cur2.fetchall()]


def _null_fraction(row):
    vals = list(row.values())
    nulls = sum(1 for v in vals if v is None or str(v).strip() == "")
    return nulls / len(vals) if vals else 0


def _standardize_date(val):
    if not val or str(val).strip() == "":
        return val
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val


def cleanse_all(conn=None):
    close_after = conn is None
    if conn is None:
        conn = sqlite3.connect(DB_PATH)

    now = datetime.datetime.utcnow().isoformat()
    report = {}

    for raw_table, (cur_table, pk) in TABLE_MAP.items():
        raw_cols, rows = _fetch_rows(conn, raw_table)
        rows_in = len(rows)

        # 1. Strip whitespace, blank → None
        for row in rows:
            for k, v in row.items():
                if isinstance(v, str):
                    v = v.strip()
                    row[k] = None if v == "" else v

        # 2. Drop rows where PK is null
        rows = [r for r in rows if r.get(pk) not in (None, "")]

        # 3. Standardize date columns (columns ending in _date, _at, join_date, dob, timestamp, last_updated)
        date_cols = [c for c in raw_cols if any(c.endswith(s) for s in
                     ("_date","_at","dob","join_date","last_updated","timestamp"))]
        for row in rows:
            for dc in date_cols:
                if dc in row:
                    row[dc] = _standardize_date(row.get(dc))

        # 4. Deduplicate — track duplicates
        seen_pks = set()
        dupes_removed = 0
        clean_rows = []
        for row in rows:
            key = row.get(pk)
            if key in seen_pks:
                dupes_removed += 1
            else:
                seen_pks.add(key)
                clean_rows.append(row)
        rows = clean_rows

        # 5. Quality flag rows with >30% nulls
        for row in rows:
            row["_quality_flag"] = "POOR" if _null_fraction(row) > 0.30 else "OK"
            row["_is_duplicate"] = 0
            row["_cleansed_at"] = now

        rows_out = len(rows)

        # 6. Write to curated table
        conn.execute(f"DELETE FROM {cur_table}")
        dest_cols = CURATED_COLS[cur_table] + ["_cleansed_at", "_is_duplicate", "_quality_flag"]

        # Extra derived cols that will be added in transform step — insert as NULL placeholders
        extra = {}
        if cur_table == "curated_customer_profiles":
            extra = {"age_group": None}
        elif cur_table == "curated_transaction_logs":
            extra = {"amount_usd": None}
        elif cur_table == "curated_hr_records":
            extra = {"tenure_years": None}
        elif cur_table == "curated_sensor_telemetry":
            extra = {"is_anomaly": 0}
        elif cur_table == "curated_audit_trail":
            extra = {"ip_country": None}

        all_dest = CURATED_COLS[cur_table] + list(extra.keys()) + ["_cleansed_at","_is_duplicate","_quality_flag"]

        batch = []
        for row in rows:
            vals = [row.get(c) for c in CURATED_COLS[cur_table]]
            vals += [extra.get(c) for c in extra.keys()]
            vals += [row["_cleansed_at"], row["_is_duplicate"], row["_quality_flag"]]
            batch.append(tuple(vals))

        placeholders = ", ".join(["?"] * len(all_dest))
        col_list = ", ".join(all_dest)
        conn.executemany(
            f"INSERT INTO {cur_table} ({col_list}) VALUES ({placeholders})",
            batch,
        )
        conn.commit()

        report[raw_table] = {
            "rows_in":       rows_in,
            "rows_out":      rows_out,
            "dupes_removed": dupes_removed,
            "poor_quality":  sum(1 for r in rows if r.get("_quality_flag") == "POOR"),
        }
        print(f"  [CLEANSE] {raw_table}: {rows_in:,} → {rows_out:,} "
              f"(dupes={dupes_removed}, poor={report[raw_table]['poor_quality']})")

    if close_after:
        conn.close()

    return report


if __name__ == "__main__":
    cleanse_all()
