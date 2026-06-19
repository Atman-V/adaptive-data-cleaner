"""
classifier.py — Populates the governance_catalog table from SCHEMA_REGISTRY.
"""

import sqlite3
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from governance.schema_registry import SCHEMA_REGISTRY, get_sensitivity_summary

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "warehouse.db")


def run_classification(conn=None):
    """
    Insert every (table, column) pair from SCHEMA_REGISTRY into governance_catalog.
    Returns a summary dict.
    """
    close_after = conn is None
    if conn is None:
        conn = sqlite3.connect(DB_PATH)

    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    # Clear previous entries
    cur.execute("DELETE FROM governance_catalog")

    total = 0
    for table_name, columns in SCHEMA_REGISTRY.items():
        for col_name, meta in columns.items():
            cur.execute(
                """
                INSERT INTO governance_catalog
                    (table_name, column_name, sensitivity_label, is_pii,
                     owner, description, last_classified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    table_name,
                    col_name,
                    meta["sensitivity"],
                    1 if meta["is_pii"] else 0,
                    meta.get("owner", "Unknown"),
                    meta.get("description", ""),
                    now,
                ),
            )
            total += 1

    conn.commit()

    summary = get_sensitivity_summary()
    pii_count = sum(
        1
        for _, cols in SCHEMA_REGISTRY.items()
        for _, meta in cols.items()
        if meta["is_pii"]
    )

    if close_after:
        conn.close()

    result = {
        "total_columns_classified": total,
        "pii_columns": pii_count,
        "by_sensitivity": summary,
    }

    print(f"  [CLASSIFY] {total} columns classified | PII={pii_count} | {summary}")
    return result


if __name__ == "__main__":
    run_classification()
