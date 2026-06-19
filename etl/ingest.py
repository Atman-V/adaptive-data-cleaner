"""
etl/ingest.py — Step 1: Load raw CSVs into the raw_ zone of the warehouse.
Computes SHA-256 row hash, stamps ingested_at and source_file.
"""

import csv
import hashlib
import sqlite3
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "warehouse.db")
RAW_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")

SOURCE_MAP = {
    "customer_profiles.csv": "raw_customer_profiles",
    "transaction_logs.csv":  "raw_transaction_logs",
    "hr_records.csv":        "raw_hr_records",
    "product_catalog.csv":   "raw_product_catalog",
    "sensor_telemetry.csv":  "raw_sensor_telemetry",
    "audit_trail.csv":       "raw_audit_trail",
}


def _row_hash(row_values):
    joined = "|".join(str(v) for v in row_values)
    return hashlib.sha256(joined.encode()).hexdigest()


def ingest_all_sources(conn=None):
    close_after = conn is None
    if conn is None:
        conn = sqlite3.connect(DB_PATH)

    now = datetime.datetime.utcnow().isoformat()
    summary = {}

    for filename, table in SOURCE_MAP.items():
        filepath = os.path.join(RAW_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  [INGEST] WARNING: {filename} not found, skipping.")
            continue

        try:
            from etl.encoding_helper import open_csv
            f = open_csv(filepath)
        except ImportError:
            f = open(filepath, newline="", encoding="utf-8-sig", errors="replace")
        with f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            summary[table] = 0
            continue

        cols = list(rows[0].keys())
        # clear existing raw data for idempotency
        conn.execute(f"DELETE FROM {table}")

        batch = []
        for row in rows:
            values = [row.get(c, "") for c in cols]
            h = _row_hash(values)
            batch.append(tuple(values) + (now, filename, h))

        placeholders = ", ".join(["?"] * (len(cols) + 3))
        col_list = ", ".join(cols) + ", _ingested_at, _source_file, _row_hash"
        conn.executemany(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
            batch,
        )
        conn.commit()
        summary[table] = len(batch)
        print(f"  [INGEST] {table}: {len(batch):,} rows loaded")

    if close_after:
        conn.close()

    return summary


if __name__ == "__main__":
    result = ingest_all_sources()
    print(result)
