"""
etl/smart_cleaner.py
Applies user-selected cleaning rules to a CSV file.
Takes the analysis report + user's rule choices, produces a cleaned CSV.
"""

import csv
import os
import datetime
import sqlite3
import hashlib
import re
from collections import Counter
from etl.smart_analyzer import (
    is_blank, try_parse_date, try_parse_number,
    detect_outliers, EMAIL_RE, DATE_PATTERNS
)
from etl.encoding_helper import open_csv, detect_encoding
from etl.excel_helper import is_excel_file, read_excel_rows

ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH       = os.path.join(ROOT, "db", "warehouse.db")
PROCESSED_DIR = os.path.join(ROOT, "data", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)


def _safe_table_name(filename):
    base = os.path.splitext(os.path.basename(filename))[0]
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", base).lower().strip("_")
    if safe and safe[0].isdigit(): safe = "t_" + safe
    return safe or "custom_table"


def apply_cleaning(filepath, report, user_rules, progress_cb=None):
    """
    Apply cleaning rules to a CSV file.

    Args:
        filepath:   path to original CSV
        report:     output from analyze_csv()
        user_rules: dict like {
            "global": {"remove_full_duplicates": True, "dedupe_by_pk": True},
            "columns": {
                "email":    {"action": "drop_rows_invalid_email"},
                "salary":   {"action": "fill_missing_median"},
                "name":     {"action": "trim_whitespace"},
                ...
            }
        }
        progress_cb: optional callable(step, msg)

    Returns:
        dict with summary, before/after stats, and output CSV path
    """
    def emit(step, msg):
        print(f"  [{step}] {msg}")
        if progress_cb: progress_cb(step, msg)

    start = datetime.datetime.utcnow()

    if is_excel_file(filepath):
        emit("LOAD", "Reading Excel workbook…")
        headers, rows, _excel_meta = read_excel_rows(filepath)
    else:
        emit("LOAD", "Reading CSV…")
        # Re-read with detected delimiter + auto-detected encoding
        delim_map = {"comma":",","tab":"\t","semicolon":";","pipe":"|"}
        delim = delim_map.get(report.get("delimiter","comma"), ",")
        with open_csv(filepath) as f:
            reader = csv.DictReader(f, delimiter=delim)
            headers = reader.fieldnames or []
            rows = list(reader)

    original_row_count = len(rows)
    original_null_count = sum(1 for r in rows for v in r.values() if is_blank(v))
    emit("LOAD", f"{original_row_count:,} rows · {len(headers)} columns")

    # Track changes
    changes = {h: {} for h in headers}
    rows_dropped = 0

    # Build column lookup from report
    col_report = {c["name"]: c for c in report["columns"]}

    # ── 1. Global rules first ─────────────────────────────────────────────────
    global_rules = user_rules.get("global", {})

    if global_rules.get("remove_full_duplicates"):
        emit("DEDUPE", "Removing fully duplicate rows…")
        seen = set(); deduped = []
        for r in rows:
            key = tuple(str(r.get(h,"")).strip() for h in headers)
            if key in seen: continue
            seen.add(key); deduped.append(r)
        rows_dropped += len(rows) - len(deduped)
        rows = deduped
        emit("DEDUPE", f"Removed {original_row_count - len(rows)} duplicates")

    if global_rules.get("remove_near_duplicates"):
        emit("DEDUPE", "Removing near-duplicate rows (case/whitespace variants)…")
        before = len(rows)
        seen = set(); deduped = []
        for r in rows:
            key = tuple(str(r.get(h,"")).strip().lower() for h in headers)
            if key in seen: continue
            seen.add(key); deduped.append(r)
        removed_now = before - len(deduped)
        rows_dropped += removed_now
        rows = deduped
        emit("DEDUPE", f"Removed {removed_now} near-duplicates")

    if global_rules.get("dedupe_by_pk") and report.get("suggested_primary_key"):
        pk = report["suggested_primary_key"]
        emit("DEDUPE", f"Deduplicating by '{pk}'…")
        seen = set(); deduped = []
        for r in rows:
            v = str(r.get(pk,"")).strip()
            if v and v in seen: continue
            seen.add(v); deduped.append(r)
        rows_dropped_now = len(rows) - len(deduped)
        rows_dropped += rows_dropped_now
        rows = deduped
        emit("DEDUPE", f"Removed {rows_dropped_now} PK duplicates")

    # ── 2. Per-column rules ───────────────────────────────────────────────────
    col_rules = user_rules.get("columns", {})

    # Build values cache for fill_with_mean/median/mode
    col_values_cache = {}
    col_stats_cache  = {}   # mean/median/mode/IQR bounds — pre-computed
    for col in headers:
        non_blank = [r.get(col) for r in rows if not is_blank(r.get(col))]
        col_values_cache[col] = non_blank
        nums = [try_parse_number(v) for v in non_blank]
        nums = [n for n in nums if n is not None]
        stats = {}
        if nums:
            stats["mean"]   = round(sum(nums)/len(nums), 2)
            sorted_nums = sorted(nums)
            stats["median"] = sorted_nums[len(sorted_nums)//2]
            if len(sorted_nums) >= 8:
                n = len(sorted_nums)
                q1, q3 = sorted_nums[n//4], sorted_nums[3*n//4]
                iqr = q3 - q1
                stats["lo"] = q1 - 1.5*iqr
                stats["hi"] = q3 + 1.5*iqr
                stats["outlier_set"] = set(detect_outliers(nums))
        if non_blank:
            stats["mode"] = Counter(str(v) for v in non_blank).most_common(1)[0][0]
        col_stats_cache[col] = stats

    new_rows = []
    drop_indices = set()

    for idx, row in enumerate(rows):
        row_dropped = False
        new_row = dict(row)

        for col, rule in col_rules.items():
            if row_dropped: break
            if col not in headers: continue
            action = rule.get("action")
            if not action or action == "keep_missing" or action == "keep_outliers":
                continue

            val = new_row.get(col, "")
            non_blank = col_values_cache[col]
            stats     = col_stats_cache[col]
            cinfo = col_report.get(col, {})

            # ── trim_whitespace ──
            if action == "trim_whitespace" and isinstance(val, str):
                if val != val.strip():
                    new_row[col] = val.strip()
                    changes[col]["trimmed"] = changes[col].get("trimmed", 0) + 1

            # ── case normalisation ──
            elif action == "standardize_lower" and isinstance(val, str) and not is_blank(val):
                new_row[col] = val.strip().lower()
                changes[col]["case_normalized"] = changes[col].get("case_normalized", 0) + 1
            elif action == "standardize_upper" and isinstance(val, str) and not is_blank(val):
                new_row[col] = val.strip().upper()
                changes[col]["case_normalized"] = changes[col].get("case_normalized", 0) + 1
            elif action == "standardize_title" and isinstance(val, str) and not is_blank(val):
                new_row[col] = val.strip().title()
                changes[col]["case_normalized"] = changes[col].get("case_normalized", 0) + 1

            # ── date standardise ──
            elif action == "standardize_date_iso" and not is_blank(val):
                parsed = try_parse_date(val)
                if parsed:
                    new_row[col] = parsed[0].strftime("%Y-%m-%d")
                    if str(val).strip() != new_row[col]:
                        changes[col]["dates_normalized"] = changes[col].get("dates_normalized", 0) + 1

            # ── fill missing ──
            elif action == "fill_missing_mean" and is_blank(val):
                if "mean" in stats:
                    new_row[col] = stats["mean"]
                    changes[col]["filled"] = changes[col].get("filled", 0) + 1
            elif action == "fill_missing_median" and is_blank(val):
                if "median" in stats:
                    new_row[col] = stats["median"]
                    changes[col]["filled"] = changes[col].get("filled", 0) + 1
            elif action == "fill_missing_zero" and is_blank(val):
                new_row[col] = 0
                changes[col]["filled"] = changes[col].get("filled", 0) + 1
            elif action == "fill_missing_mode" and is_blank(val):
                if "mode" in stats:
                    new_row[col] = stats["mode"]
                    changes[col]["filled"] = changes[col].get("filled", 0) + 1
            elif action == "fill_missing_unknown" and is_blank(val):
                new_row[col] = "Unknown"
                changes[col]["filled"] = changes[col].get("filled", 0) + 1
            elif action == "fill_missing_today" and is_blank(val):
                new_row[col] = datetime.date.today().isoformat()
                changes[col]["filled"] = changes[col].get("filled", 0) + 1

            # ── drop row if missing ──
            elif action == "drop_rows_missing" and is_blank(val):
                drop_indices.add(idx); row_dropped = True
                changes[col]["rows_dropped"] = changes[col].get("rows_dropped", 0) + 1
                continue

            # ── email invalid ──
            elif action == "drop_rows_invalid_email" and not is_blank(val):
                if not EMAIL_RE.match(str(val).strip()):
                    drop_indices.add(idx); row_dropped = True
                    changes[col]["rows_dropped"] = changes[col].get("rows_dropped", 0) + 1
                    continue
            elif action == "null_invalid_email" and not is_blank(val):
                if not EMAIL_RE.match(str(val).strip()):
                    new_row[col] = None
                    changes[col]["nulled"] = changes[col].get("nulled", 0) + 1

            # ── outliers ──  (uses precomputed bounds)
            elif action == "drop_outliers" and not is_blank(val) and "lo" in stats:
                num = try_parse_number(val)
                if num is not None and (num < stats["lo"] or num > stats["hi"]):
                    drop_indices.add(idx); row_dropped = True
                    changes[col]["rows_dropped"] = changes[col].get("rows_dropped", 0) + 1
                    continue
            elif action == "cap_outliers" and not is_blank(val) and "lo" in stats:
                num = try_parse_number(val)
                if num is not None:
                    if num < stats["lo"]:
                        new_row[col] = round(stats["lo"], 2)
                        changes[col]["capped"] = changes[col].get("capped", 0) + 1
                    elif num > stats["hi"]:
                        new_row[col] = round(stats["hi"], 2)
                        changes[col]["capped"] = changes[col].get("capped", 0) + 1

            # ── negatives ──
            elif action == "abs_values" and not is_blank(val):
                num = try_parse_number(val)
                if num is not None and num < 0:
                    new_row[col] = abs(num)
                    changes[col]["abs_applied"] = changes[col].get("abs_applied", 0) + 1
            elif action == "drop_rows_negative" and not is_blank(val):
                num = try_parse_number(val)
                if num is not None and num < 0:
                    drop_indices.add(idx); row_dropped = True
                    changes[col]["rows_dropped"] = changes[col].get("rows_dropped", 0) + 1
                    continue
            elif action == "null_negative" and not is_blank(val):
                num = try_parse_number(val)
                if num is not None and num < 0:
                    new_row[col] = None
                    changes[col]["nulled"] = changes[col].get("nulled", 0) + 1

        if not row_dropped:
            new_rows.append(new_row)

    rows_dropped += len(rows) - len(new_rows)
    rows = new_rows
    emit("CLEAN", f"{len(rows):,} rows after cleaning · {rows_dropped} total dropped")

    # ── 3. Add quality flag ──────────────────────────────────────────────────
    poor_count = 0
    for r in rows:
        nulls = sum(1 for v in r.values() if is_blank(v))
        r["_quality_flag"] = "POOR" if nulls / max(len(headers),1) > 0.30 else "OK"
        if r["_quality_flag"] == "POOR": poor_count += 1
    headers_out = headers + ["_quality_flag"]

    # ── 4. Save cleaned CSV ──────────────────────────────────────────────────
    base       = os.path.splitext(os.path.basename(filepath))[0]
    ts         = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = os.path.join(PROCESSED_DIR, f"{base}_cleaned_{ts}.csv")
    emit("SAVE", f"Writing cleaned CSV → {os.path.basename(output_csv)}")

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers_out)
        writer.writeheader()
        for r in rows:
            writer.writerow({h: ("" if is_blank(r.get(h)) else r.get(h)) for h in headers_out})

    # ── 5. Persist to SQLite warehouse ───────────────────────────────────────
    emit("DB", "Saving to warehouse.db…")
    try:
        conn = sqlite3.connect(DB_PATH)
        table_base = _safe_table_name(report["filename"])
        cur_table  = f"curated_{table_base}"

        # Infer column types from cleaned data
        col_types = {}
        for h in headers_out:
            sample = [r.get(h) for r in rows[:200] if not is_blank(r.get(h))]
            if not sample:
                col_types[h] = "TEXT"
            else:
                try:
                    [int(v) for v in sample[:20]]
                    col_types[h] = "INTEGER"
                except (ValueError, TypeError):
                    try:
                        [float(v) for v in sample[:20]]
                        col_types[h] = "REAL"
                    except (ValueError, TypeError):
                        col_types[h] = "TEXT"

        conn.execute(f"DROP TABLE IF EXISTS {cur_table}")
        col_defs = ", ".join(f'"{c}" {t}' for c, t in col_types.items())
        conn.execute(f"CREATE TABLE {cur_table} ({col_defs})")
        ph = ", ".join(["?"] * len(headers_out))
        col_list = ", ".join(f'"{c}"' for c in headers_out)
        conn.executemany(
            f"INSERT INTO {cur_table} ({col_list}) VALUES ({ph})",
            [tuple(r.get(h) for h in headers_out) for r in rows]
        )
        conn.commit()
        conn.close()
        emit("DB", f"Stored in table: {cur_table}")
    except Exception as e:
        emit("DB", f"Warning: {e}")

    # ── 6. Post-cleaning stats ───────────────────────────────────────────────
    after_null_count = sum(1 for r in rows for v in r.values() if is_blank(v))
    elapsed = round((datetime.datetime.utcnow() - start).total_seconds(), 2)

    # Per-column after stats
    col_after = {}
    for col in headers:
        non_blank = [r.get(col) for r in rows if not is_blank(r.get(col))]
        col_after[col] = {
            "completeness": round(len(non_blank) / max(len(rows),1) * 100, 1),
            "null_count":   len(rows) - len(non_blank),
        }

    return {
        "status":           "SUCCESS",
        "elapsed_sec":      elapsed,
        "filename":         report["filename"],
        "original_rows":    original_row_count,
        "cleaned_rows":     len(rows),
        "rows_dropped":     rows_dropped,
        "poor_rows":        poor_count,
        "original_nulls":   original_null_count,
        "cleaned_nulls":    after_null_count,
        "nulls_resolved":   original_null_count - after_null_count,
        "changes_by_col":   changes,
        "col_after":        col_after,
        "output_csv":       output_csv,
        "output_basename":  os.path.basename(output_csv),
        "table_name":       f"curated_{_safe_table_name(report['filename'])}",
        "preview":          rows[:10],
        "preview_headers":  headers_out,
    }


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python -m etl.smart_cleaner <file.csv>")
        sys.exit(1)
    from etl.smart_analyzer import analyze_csv
    rep = analyze_csv(sys.argv[1])
    # Apply ALL default suggestions
    user_rules = {
        "global": {"remove_full_duplicates": True, "dedupe_by_pk": True},
        "columns": {}
    }
    for c in rep["columns"]:
        for s in c["suggestions"]:
            if s.get("default"):
                user_rules["columns"][c["name"]] = {"action": s["action"]}
                break
        else:
            if c["suggestions"]:
                user_rules["columns"][c["name"]] = {"action": c["suggestions"][0]["action"]}
    result = apply_cleaning(sys.argv[1], rep, user_rules)
    print(json.dumps({k:v for k,v in result.items() if k not in ("preview","preview_headers")},
                     indent=2, default=str))
