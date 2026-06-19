"""
pipeline_runner.py — Master ETL + Governance pipeline runner.
Executes all steps sequentially, logs results to logs/RUN_*.json.

Usage:
    python pipeline_runner.py
"""

import time
import json
import datetime
import sqlite3
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from etl.ingest      import ingest_all_sources
from etl.cleanse     import cleanse_all
from etl.transform   import transform_all
from etl.load        import load_consumption
from governance.classifier    import run_classification
from governance.quality_checker import compute_quality_scores

DB_PATH  = os.path.join(os.path.dirname(__file__), "db", "warehouse.db")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
SCHEMA   = os.path.join(os.path.dirname(__file__), "db", "schema.sql")


def init_db(conn):
    """Create all tables from schema.sql."""
    with open(SCHEMA, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    print("[INIT] Database schema created/verified.")


def compute_all_quality(conn, start_time):
    """Run quality checks across all curated tables."""
    tables = [
        "curated_customer_profiles",
        "curated_transaction_logs",
        "curated_hr_records",
        "curated_product_catalog",
        "curated_sensor_telemetry",
        "curated_audit_trail",
    ]
    all_scores = {}
    for table in tables:
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        raw = conn.execute(f"SELECT * FROM {table} LIMIT 5000").fetchall()
        rows = [dict(zip(cols, r)) for r in raw]
        raw_table = table.replace("curated_", "raw_")
        scores = compute_quality_scores(raw_table, rows, start_time)
        all_scores[table] = scores

    # aggregate overall
    if all_scores:
        keys = ["completeness","uniqueness","accuracy","consistency","timeliness"]
        avg = {}
        for k in keys:
            avg[k] = round(sum(s[k] for s in all_scores.values()) / len(all_scores), 2)
        from governance.quality_checker import compute_overall_score
        avg["overall"] = compute_overall_score(avg)
        all_scores["_aggregate"] = avg

    return all_scores


def run():
    run_id = f"RUN_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(LOGS_DIR, exist_ok=True)
    pipeline_start = datetime.datetime.utcnow()

    print(f"\n{'='*60}")
    print(f"  DATA PIPELINE — {run_id}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    log = []

    steps = [
        ("INGEST",    lambda: ingest_all_sources(conn)),
        ("CLEANSE",   lambda: cleanse_all(conn)),
        ("TRANSFORM", lambda: transform_all(conn)),
        ("LOAD",      lambda: load_consumption(conn)),
        ("CLASSIFY",  lambda: run_classification(conn)),
        ("QUALITY",   lambda: compute_all_quality(conn, pipeline_start)),
    ]

    quality_scores = {}

    for step_name, fn in steps:
        t0 = time.time()
        print(f"\n── {step_name} ──────────────────────────────")
        try:
            result = fn()
            elapsed = round(time.time() - t0, 2)
            status  = "SUCCESS"
            if step_name == "QUALITY":
                quality_scores = result
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            status  = "ERROR"
            result  = {"error": str(e)}
            print(f"  ERROR in {step_name}: {e}")

        entry = {
            "step":        step_name,
            "status":      status,
            "elapsed_sec": elapsed,
            "started_at":  datetime.datetime.utcnow().isoformat(),
            "result":      result,
        }
        log.append(entry)
        print(f"  → {step_name} completed in {elapsed}s [{status}]")

    # ── Summary ───────────────────────────────────────────────────────────────
    total_elapsed = round((datetime.datetime.utcnow() - pipeline_start).total_seconds(), 2)
    agg = quality_scores.get("_aggregate", {})
    overall_score = agg.get("overall", 0)

    # Count raw totals
    raw_tables = ["raw_customer_profiles","raw_transaction_logs","raw_hr_records",
                  "raw_product_catalog","raw_sensor_telemetry","raw_audit_trail"]
    total_raw = sum(
        conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in raw_tables
    )
    total_curated = sum(
        conn.execute(f"SELECT COUNT(*) FROM {t.replace('raw_','curated_')}").fetchone()[0]
        for t in raw_tables
    )
    total_poor = sum(
        conn.execute(f"SELECT COUNT(*) FROM {t.replace('raw_','curated_')} WHERE _quality_flag='POOR'").fetchone()[0]
        for t in raw_tables
    )
    pii_cols = conn.execute(
        "SELECT COUNT(*) FROM governance_catalog WHERE is_pii=1"
    ).fetchone()[0]

    summary = {
        "run_id":           run_id,
        "total_elapsed_sec": total_elapsed,
        "total_raw_rows":   total_raw,
        "total_curated_rows": total_curated,
        "poor_quality_rows": total_poor,
        "pii_columns_tagged": pii_cols,
        "ingestion_rate":   round(total_raw / max(total_elapsed, 1), 0),
        "quality_scores":   quality_scores,
        "pipeline_log":     log,
    }

    log_path = os.path.join(LOGS_DIR, f"{run_id}.json")
    with open(log_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    conn.close()

    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE — {run_id}")
    print(f"  Total time      : {total_elapsed}s")
    print(f"  Raw rows        : {total_raw:,}")
    print(f"  Curated rows    : {total_curated:,}")
    print(f"  Poor quality    : {total_poor:,}")
    print(f"  Overall quality : {overall_score}%")
    print(f"  PII cols tagged : {pii_cols}")
    print(f"  Log saved to    : {log_path}")
    print(f"{'='*60}\n")
    print("  Open dashboard/index.html in your browser to view results.")

    return summary


if __name__ == "__main__":
    run()
