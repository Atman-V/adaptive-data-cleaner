"""
quality_checker.py — Computes 5-dimension quality scores per table.
Dimensions: Completeness, Uniqueness, Accuracy, Consistency, Timeliness
"""

import datetime


# ── Expected data types per table / column ────────────────────────────────────

EXPECTED_TYPES = {
    "raw_customer_profiles": {
        "customer_id": str, "full_name": str, "email": str,
        "dob": str, "account_type": str,
    },
    "raw_transaction_logs": {
        "txn_id": str, "amount": float, "currency": str,
        "txn_date": str, "status": str,
    },
    "raw_hr_records": {
        "emp_id": str, "salary": float, "performance_score": int,
        "is_active": int,
    },
    "raw_product_catalog": {
        "product_id": str, "price": float, "stock_qty": int,
    },
    "raw_sensor_telemetry": {
        "sensor_id": str, "temperature": float, "humidity": float,
        "pressure": float, "alert_flag": int,
    },
    "raw_audit_trail": {
        "audit_id": str, "user_id": str, "action": str,
        "ip_address": str, "status": str,
    },
}

BUSINESS_RULES = {
    "raw_transaction_logs": lambda row: float(row.get("amount", 0) or 0) >= 0,
    "raw_sensor_telemetry": lambda row: -50 <= float(row.get("temperature", 0) or 0) <= 100,
    "raw_hr_records":       lambda row: 1 <= int(row.get("performance_score", 3) or 3) <= 5,
}


def compute_quality_scores(table_name: str, rows: list, ingestion_start: datetime.datetime = None) -> dict:
    """
    Compute 5 quality dimensions for a list-of-dicts dataset.

    Args:
        table_name: Name of the table (used for rule lookup).
        rows: List of row dicts.
        ingestion_start: Datetime when pipeline started (for timeliness).

    Returns:
        Dict with completeness, uniqueness, accuracy, consistency, timeliness,
        and weighted overall score.
    """
    if not rows:
        return {d: 0.0 for d in ["completeness", "uniqueness", "accuracy",
                                   "consistency", "timeliness", "overall"]}

    n = len(rows)
    cols = list(rows[0].keys()) if rows else []
    total_cells = n * len(cols)

    # ── 1. Completeness ───────────────────────────────────────────────────────
    non_null_cells = sum(
        1
        for row in rows
        for v in row.values()
        if v is not None and v != ""
    )
    completeness = round((non_null_cells / total_cells) * 100, 2) if total_cells else 0.0

    # ── 2. Uniqueness ─────────────────────────────────────────────────────────
    # Treat each row as a frozenset of (col, val) for deduplication check
    seen = set()
    dupes = 0
    for row in rows:
        key = tuple(str(v) for v in row.values())
        if key in seen:
            dupes += 1
        seen.add(key)
    uniqueness = round(((n - dupes) / n) * 100, 2)

    # ── 3. Accuracy ───────────────────────────────────────────────────────────
    rule = BUSINESS_RULES.get(table_name)
    if rule:
        passing = sum(1 for row in rows if _safe_rule(rule, row))
        accuracy = round((passing / n) * 100, 2)
    else:
        accuracy = 100.0   # no rule defined → assume accurate

    # ── 4. Consistency ────────────────────────────────────────────────────────
    expected = EXPECTED_TYPES.get(table_name, {})
    if expected:
        consistent_cols = 0
        for col, expected_type in expected.items():
            ok = sum(
                1 for row in rows
                if _type_matches(row.get(col), expected_type)
            )
            consistent_cols += ok / n
        consistency = round((consistent_cols / len(expected)) * 100, 2)
    else:
        consistency = 100.0

    # ── 5. Timeliness ─────────────────────────────────────────────────────────
    if ingestion_start is None:
        ingestion_start = datetime.datetime.utcnow()
    elapsed_min = (datetime.datetime.utcnow() - ingestion_start).total_seconds() / 60.0
    if elapsed_min <= 10:
        timeliness = 100.0
    else:
        timeliness = max(0.0, round(100.0 - (elapsed_min - 10) * 2, 2))

    # ── Overall weighted score ────────────────────────────────────────────────
    overall = compute_overall_score({
        "completeness": completeness,
        "uniqueness":   uniqueness,
        "accuracy":     accuracy,
        "consistency":  consistency,
        "timeliness":   timeliness,
    })

    return {
        "completeness": completeness,
        "uniqueness":   uniqueness,
        "accuracy":     accuracy,
        "consistency":  consistency,
        "timeliness":   timeliness,
        "overall":      overall,
        "row_count":    n,
    }


def compute_overall_score(scores: dict) -> float:
    """Weighted average: Completeness 30%, Uniqueness 20%, Accuracy 25%, Consistency 15%, Timeliness 10%."""
    weights = {
        "completeness": 0.30,
        "uniqueness":   0.20,
        "accuracy":     0.25,
        "consistency":  0.15,
        "timeliness":   0.10,
    }
    weighted = sum(scores.get(k, 0) * w for k, w in weights.items())
    return round(weighted, 2)


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_rule(rule, row):
    try:
        return bool(rule(row))
    except Exception:
        return False


def _type_matches(value, expected_type):
    if value is None or value == "":
        return False
    try:
        expected_type(value)
        return True
    except (ValueError, TypeError):
        return False
