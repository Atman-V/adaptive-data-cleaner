"""
etl/custom_pipeline.py
Processes ANY uploaded CSV through the full ETL pipeline dynamically.
No hardcoded schema — auto-detects columns, creates tables, runs all steps.
"""

import csv
import hashlib
import sqlite3
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from governance.quality_checker import compute_quality_scores, compute_overall_score

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "warehouse.db")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_hash(values):
    return hashlib.sha256("|".join(str(v) for v in values).encode()).hexdigest()


def _safe_table_name(filename):
    """Turn filename into a safe SQL table name."""
    base = os.path.splitext(os.path.basename(filename))[0]
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", base).lower().strip("_")
    if safe and safe[0].isdigit():
        safe = "t_" + safe
    return safe or "custom_table"


def _infer_col_type(values):
    """Infer SQLite column type from a sample of values."""
    non_empty = [v for v in values if v and str(v).strip()]
    if not non_empty:
        return "TEXT"
    # try INTEGER
    try:
        [int(v) for v in non_empty[:20]]
        return "INTEGER"
    except (ValueError, TypeError):
        pass
    # try REAL
    try:
        [float(v) for v in non_empty[:20]]
        return "REAL"
    except (ValueError, TypeError):
        pass
    return "TEXT"


def _detect_primary_key(headers, rows):
    """Find the column most likely to be a unique identifier."""
    for col in headers:
        vals = [r.get(col, "") for r in rows if r.get(col)]
        if len(vals) == len(set(vals)) and len(vals) > 0:
            # Prefer columns with 'id', 'key', 'no', 'num', 'code' in name
            if any(kw in col.lower() for kw in ["id", "key", "no", "num", "code", "ref"]):
                return col
    # fallback: first column that's fully unique
    for col in headers:
        vals = [r.get(col, "") for r in rows if r.get(col)]
        if len(vals) == len(set(vals)) and len(vals) > 0:
            return col
    return None


def _detect_sensitivity(col_name):
    """Classify a column as PII/Financial/Public/Internal by name heuristics."""
    name = col_name.lower()
    pii_kws       = ["name","email","phone","mobile","address","dob","birth","ssn","passport",
                     "gender","age","ip","zip","postal","nic","aadhar","pan","license"]
    financial_kws = ["salary","amount","price","revenue","cost","balance","credit","debit",
                     "account","card","bank","payment","invoice","tax","wage","income"]
    public_kws    = ["category","type","status","country","city","region","product","sku",
                     "description","title","model","brand","color","size","rating"]

    if any(k in name for k in pii_kws):
        return "PII", True
    if any(k in name for k in financial_kws):
        return "Financial", False
    if any(k in name for k in public_kws):
        return "Public", False
    return "Internal", False


def _standardize_date(val):
    """Try to convert any date string to ISO 8601."""
    if not val or str(val).strip() == "":
        return val
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                "%Y/%m/%d", "%d.%m.%Y", "%m.%d.%Y"):
        try:
            return datetime.datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val


def _is_date_col(col_name, sample_vals):
    """Heuristic: is this column a date?"""
    name = col_name.lower()
    if any(k in name for k in ["date","time","created","updated","at","on","dob","birth",
                                "joined","hired","start","end","timestamp","ts"]):
        return True
    # try parsing first non-empty value
    for v in sample_vals[:5]:
        if v and str(v).strip():
            try:
                datetime.datetime.strptime(str(v).strip()[:10], "%Y-%m-%d")
                return True
            except ValueError:
                try:
                    datetime.datetime.strptime(str(v).strip()[:10], "%d/%m/%Y")
                    return True
                except ValueError:
                    pass
    return False


# ── Main pipeline function ────────────────────────────────────────────────────

def run_custom_pipeline(filepath, progress_cb=None):
    """
    Full ETL + Governance pipeline for any CSV file.
    
    Args:
        filepath:    absolute path to the uploaded CSV
        progress_cb: optional callable(step, message) for progress updates
    
    Returns:
        dict with complete pipeline summary
    """
    def emit(step, msg):
        print(f"  [{step}] {msg}")
        if progress_cb:
            progress_cb(step, msg)

    start_time = datetime.datetime.utcnow()
    filename   = os.path.basename(filepath)
    table_base = _safe_table_name(filename)
    raw_table  = f"raw_{table_base}"
    cur_table  = f"curated_{table_base}"

    # ── 1. READ CSV ──────────────────────────────────────────────────────────
    emit("READ", f"Reading {filename}…")
    try:
        from etl.encoding_helper import open_csv
        f = open_csv(filepath)
    except ImportError:
        f = open(filepath, newline="", encoding="utf-8-sig", errors="replace")
    with f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)
        headers  = reader.fieldnames or list(raw_rows[0].keys()) if raw_rows else []

    if not raw_rows:
        raise ValueError("CSV file is empty or has no data rows.")

    emit("READ", f"{len(raw_rows):,} rows · {len(headers)} columns")

    # ── 2. DETECT SCHEMA ────────────────────────────────────────────────────
    emit("DETECT", "Inferring column types and detecting primary key…")

    col_types = {}
    for col in headers:
        sample = [r.get(col, "") for r in raw_rows[:200]]
        col_types[col] = _infer_col_type(sample)

    date_cols = [col for col in headers
                 if _is_date_col(col, [r.get(col,"") for r in raw_rows[:10]])]

    pk = _detect_primary_key(headers, raw_rows)
    emit("DETECT", f"Primary key: {pk or 'none detected'} · Date cols: {date_cols or 'none'}")

    # ── 3. GOVERNANCE CLASSIFICATION ────────────────────────────────────────
    emit("CLASSIFY", "Classifying column sensitivity…")
    gov_entries = []
    for col in headers:
        sens, is_pii = _detect_sensitivity(col)
        gov_entries.append({
            "column_name":      col,
            "sensitivity_label": sens,
            "is_pii":           is_pii,
            "inferred_type":    col_types[col],
            "is_date":          col in date_cols,
        })

    pii_count = sum(1 for g in gov_entries if g["is_pii"])
    emit("CLASSIFY", f"{len(gov_entries)} columns · PII={pii_count}")

    # ── 4. INIT DB ───────────────────────────────────────────────────────────
    emit("DB", "Creating dynamic tables in warehouse.db…")
    conn = sqlite3.connect(DB_PATH)

    # Drop and recreate dynamic raw table
    conn.execute(f"DROP TABLE IF EXISTS {raw_table}")
    col_defs = ", ".join(f'"{c}" {t}' for c, t in col_types.items())
    conn.execute(f"""
        CREATE TABLE {raw_table} (
            {col_defs},
            _ingested_at TEXT,
            _source_file TEXT,
            _row_hash    TEXT
        )
    """)

    # Drop and recreate dynamic curated table
    conn.execute(f"DROP TABLE IF EXISTS {cur_table}")
    conn.execute(f"""
        CREATE TABLE {cur_table} (
            {col_defs},
            _cleansed_at  TEXT,
            _is_duplicate INTEGER DEFAULT 0,
            _quality_flag TEXT DEFAULT 'OK'
        )
    """)
    conn.commit()
    emit("DB", f"Tables {raw_table} and {cur_table} created")

    # ── 5. INGEST ────────────────────────────────────────────────────────────
    emit("INGEST", f"Loading {len(raw_rows):,} rows into {raw_table}…")
    now = start_time.isoformat()

    batch = []
    for row in raw_rows:
        vals = [row.get(c, "") or None for c in headers]
        h    = _row_hash(vals)
        batch.append(tuple(vals) + (now, filename, h))

    ph      = ", ".join(["?"] * (len(headers) + 3))
    col_list = ", ".join(f'"{c}"' for c in headers) + ", _ingested_at, _source_file, _row_hash"
    conn.executemany(f"INSERT INTO {raw_table} ({col_list}) VALUES ({ph})", batch)
    conn.commit()
    emit("INGEST", f"{len(batch):,} rows loaded · SHA-256 hashes computed")

    # ── 6. CLEANSE ───────────────────────────────────────────────────────────
    emit("CLEANSE", "Deduplicating, normalising, flagging quality…")
    cleansed_rows = []
    seen_pks = set()
    dupes_removed = 0
    poor_count = 0
    cleanse_now = datetime.datetime.utcnow().isoformat()

    for row in raw_rows:
        # Strip whitespace, blank → None
        clean = {}
        for k, v in row.items():
            v = str(v).strip() if v else ""
            clean[k] = None if v == "" else v

        # Drop if PK is null
        if pk and (clean.get(pk) is None or clean.get(pk) == ""):
            dupes_removed += 1
            continue

        # Deduplicate by PK
        if pk and clean.get(pk):
            if clean[pk] in seen_pks:
                dupes_removed += 1
                continue
            seen_pks.add(clean[pk])

        # Standardise date columns
        for dc in date_cols:
            if dc in clean and clean[dc]:
                clean[dc] = _standardize_date(clean[dc])

        # Quality flag
        null_frac = sum(1 for v in clean.values() if v is None) / max(len(clean), 1)
        flag = "POOR" if null_frac > 0.30 else "OK"
        if flag == "POOR":
            poor_count += 1

        clean["_cleansed_at"]  = cleanse_now
        clean["_is_duplicate"] = 0
        clean["_quality_flag"] = flag
        cleansed_rows.append(clean)

    # Write curated rows
    cur_cols = headers + ["_cleansed_at", "_is_duplicate", "_quality_flag"]
    cur_ph   = ", ".join(["?"] * len(cur_cols))
    cur_list = ", ".join(f'"{c}"' for c in cur_cols)
    conn.execute(f"DELETE FROM {cur_table}")
    conn.executemany(
        f"INSERT INTO {cur_table} ({cur_list}) VALUES ({cur_ph})",
        [tuple(r.get(c) for c in cur_cols) for r in cleansed_rows]
    )
    conn.commit()
    emit("CLEANSE",
         f"{len(raw_rows):,} → {len(cleansed_rows):,} rows "
         f"(removed={dupes_removed}, poor={poor_count})")

    # ── 7. QUALITY SCORES ────────────────────────────────────────────────────
    emit("QUALITY", "Computing 5-dimension quality scores…")
    scores = compute_quality_scores(raw_table, cleansed_rows, start_time)
    emit("QUALITY",
         f"Overall={scores['overall']}% · "
         f"Completeness={scores['completeness']}% · "
         f"Uniqueness={scores['uniqueness']}%")

    # ── 8. GOVERNANCE CATALOG ────────────────────────────────────────────────
    emit("CATALOG", f"Writing {len(gov_entries)} entries to governance_catalog…")
    cat_now = datetime.datetime.utcnow().isoformat()
    # Remove old entries for this file
    conn.execute("DELETE FROM governance_catalog WHERE table_name = ?", (raw_table,))
    for g in gov_entries:
        conn.execute("""
            INSERT OR REPLACE INTO governance_catalog
                (table_name, column_name, sensitivity_label, is_pii,
                 owner, description, last_classified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            raw_table,
            g["column_name"],
            g["sensitivity_label"],
            1 if g["is_pii"] else 0,
            "Auto-detected",
            f"{g['inferred_type']} column" + (" · date" if g["is_date"] else ""),
            cat_now,
        ))
    conn.commit()

    # ── 9. BUILD SUMMARY ─────────────────────────────────────────────────────
    elapsed = round((datetime.datetime.utcnow() - start_time).total_seconds(), 2)
    run_id  = f"RUN_{start_time.strftime('%Y%m%d_%H%M%S')}"

    # Column completeness (null % per column)
    col_completeness = {}
    for col in headers:
        nulls = sum(1 for r in cleansed_rows if r.get(col) is None)
        col_completeness[col] = round((1 - nulls / max(len(cleansed_rows), 1)) * 100, 1)

    # Value distribution for first categorical column
    value_dist = {}
    for g in gov_entries:
        if g["sensitivity_label"] in ("Public", "Internal") and not g["is_date"]:
            col = g["column_name"]
            vals = [r.get(col) for r in cleansed_rows if r.get(col)]
            counts = {}
            for v in vals:
                counts[str(v)] = counts.get(str(v), 0) + 1
            if 2 <= len(counts) <= 30:
                top = dict(sorted(counts.items(), key=lambda x: -x[1])[:15])
                value_dist[col] = top
                break

    # Sensitivity breakdown counts
    sens_counts = {}
    for g in gov_entries:
        sens_counts[g["sensitivity_label"]] = sens_counts.get(g["sensitivity_label"], 0) + 1

    summary = {
        "run_id":            run_id,
        "filename":          filename,
        "table_base":        table_base,
        "raw_table":         raw_table,
        "curated_table":     cur_table,
        "total_elapsed_sec": elapsed,
        "raw_rows":          len(raw_rows),
        "curated_rows":      len(cleansed_rows),
        "dupes_removed":     dupes_removed,
        "poor_quality_rows": poor_count,
        "columns":           len(headers),
        "primary_key":       pk,
        "date_columns":      date_cols,
        "pii_columns":       pii_count,
        "ingestion_rate":    round(len(raw_rows) / max(elapsed, 0.1)),
        "quality_scores":    scores,
        "col_completeness":  col_completeness,
        "sens_counts":       sens_counts,
        "value_dist":        value_dist,
        "governance":        gov_entries,
        "col_types":         col_types,
        "status":            "SUCCESS",
    }

    conn.close()
    emit("DONE", f"Pipeline {run_id} complete in {elapsed}s")
    return summary


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m etl.custom_pipeline <path/to/file.csv>")
        sys.exit(1)
    result = run_custom_pipeline(sys.argv[1])
    import json
    print(json.dumps({k: v for k, v in result.items() if k != "governance"}, indent=2))
