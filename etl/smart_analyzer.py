"""
etl/smart_analyzer.py
Deep analysis of any CSV file — finds every quality issue per column,
generates a per-column report, and suggests cleaning rules the user can choose from.
"""

import csv
import os
import re
import datetime
from collections import Counter

# Local helper for safe encoding handling
try:
    from etl.encoding_helper import open_csv, detect_encoding
    from etl.excel_helper import is_excel_file, read_excel_rows
except ImportError:
    # Fallback if invoked as a module from a different path
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from encoding_helper import open_csv, detect_encoding
    from excel_helper import is_excel_file, read_excel_rows


# ── Column type detection ─────────────────────────────────────────────────────

DATE_PATTERNS = [
    ("%Y-%m-%d",       "ISO date"),
    ("%Y/%m/%d",       "yyyy/mm/dd"),
    ("%d/%m/%Y",       "dd/mm/yyyy"),
    ("%m/%d/%Y",       "mm/dd/yyyy"),
    ("%d-%m-%Y",       "dd-mm-yyyy"),
    ("%d.%m.%Y",       "dd.mm.yyyy"),
    ("%Y-%m-%d %H:%M:%S", "ISO datetime"),
    ("%d %b %Y",       "dd Mon yyyy"),
    ("%b %d, %Y",      "Mon dd, yyyy"),
]

EMAIL_RE  = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
PHONE_RE  = re.compile(r"^[\+\-\(\)\s\d]{7,}$")
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


# ── Sensitivity heuristics ────────────────────────────────────────────────────

PII_KEYWORDS = ["name","email","phone","mobile","address","dob","birth","ssn","passport",
                 "gender","age","zip","postal","nic","aadhar","pan","license","userid",
                 "user_id","customerid","customer_id","first","last","contact"]
FIN_KEYWORDS = ["salary","amount","price","revenue","cost","balance","credit","debit",
                "account","card","bank","payment","invoice","tax","wage","income","fee",
                "discount","total","subtotal"]
PUB_KEYWORDS = ["category","type","status","country","city","region","product","sku",
                "description","title","model","brand","color","size","rating","department"]


def detect_sensitivity(col_name):
    name = col_name.lower()
    if any(k in name for k in PII_KEYWORDS):  return "PII", True
    if any(k in name for k in FIN_KEYWORDS):  return "Financial", False
    if any(k in name for k in PUB_KEYWORDS):  return "Public", False
    return "Internal", False


# ── Cell-level analysis ───────────────────────────────────────────────────────

def is_blank(v):
    return v is None or str(v).strip() == "" or str(v).strip().lower() in ("nan","null","none","n/a","na","-")


def try_parse_date(val):
    if not val or is_blank(val): return None
    s = str(val).strip()
    for fmt, _ in DATE_PATTERNS:
        try:
            return datetime.datetime.strptime(s, fmt), fmt
        except ValueError:
            continue
    return None


def try_parse_number(val):
    if not val or is_blank(val): return None
    try:
        # Handle "1,234.56" style
        clean = str(val).replace(",", "").strip()
        if "." in clean:
            return float(clean)
        return int(clean)
    except (ValueError, TypeError):
        return None


def detect_outliers(numbers):
    """Returns list of outlier indices using IQR rule."""
    if len(numbers) < 8: return []
    sorted_nums = sorted(numbers)
    n  = len(sorted_nums)
    q1 = sorted_nums[n // 4]
    q3 = sorted_nums[3 * n // 4]
    iqr = q3 - q1
    if iqr == 0: return []
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [i for i, v in enumerate(numbers) if v < lo or v > hi]


# ── Main analyzer ─────────────────────────────────────────────────────────────

def analyze_csv(filepath):
    """
    Deep analysis of a CSV file. Returns a detailed report with:
    - File metadata
    - Per-column inferred type, null count, unique count, issues found
    - Suggested cleaning rules per column
    - Sample values
    - Overall quality preview
    """
    excel_meta = None
    if is_excel_file(filepath):
        headers, rows, excel_meta = read_excel_rows(filepath)
        delim = ","
        detected_enc = "n/a (Excel)"
        file_kind = "excel"
    else:
        detected_enc = detect_encoding(filepath)
        with open_csv(filepath) as f:
            # Sniff delimiter
            sample = f.read(8192); f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                delim = dialect.delimiter
            except Exception:
                delim = ","
            reader = csv.DictReader(f, delimiter=delim)
            headers = reader.fieldnames or []
            rows = list(reader)
        file_kind = "csv"

    if not headers or not rows:
        raise ValueError("File appears empty or has no headers.")

    total_rows = len(rows)
    report     = {
        "filename":     os.path.basename(filepath),
        "file_kind":    file_kind,
        "total_rows":   total_rows,
        "total_cols":   len(headers),
        "delimiter":    "excel" if file_kind == "excel" else ("comma" if delim == "," else "tab" if delim == "\t" else "semicolon" if delim == ";" else "pipe"),
        "encoding":     detected_enc,
        "columns":      [],
        "row_issues":   {},
        "fully_duplicate_rows": 0,
        "near_duplicate_rows": 0,
        "recommended_rules": [],
        "preview_rows": rows[:5],
    }
    if excel_meta:
        report["excel_structure"] = excel_meta

    # ── 1. Detect fully duplicate rows (entire row identical) ────────────────
    # and near-duplicate rows: rows that only differ by case/whitespace,
    # i.e. they collapse to the same row once every cell is trimmed+lowered.
    seen_full = {}
    seen_norm = {}
    for i, row in enumerate(rows):
        key = tuple(str(row.get(h, "")).strip() for h in headers)
        if key in seen_full:
            report["fully_duplicate_rows"] += 1
        else:
            seen_full[key] = i

        norm_key = tuple(str(row.get(h, "")).strip().lower() for h in headers)
        if norm_key in seen_norm:
            if key != seen_norm[norm_key]:
                report["near_duplicate_rows"] += 1
        else:
            seen_norm[norm_key] = key

    # ── 2. Per-column analysis ───────────────────────────────────────────────
    for col in headers:
        values    = [r.get(col, "") for r in rows]
        non_blank = [v for v in values if not is_blank(v)]
        unique_vals = set(str(v).strip() for v in non_blank)
        null_count  = total_rows - len(non_blank)
        null_pct    = round(null_count / total_rows * 100, 2)

        # Type inference
        inferred_type = "text"
        date_format   = None
        if non_blank:
            n_dates   = sum(1 for v in non_blank[:200] if try_parse_date(v))
            n_nums    = sum(1 for v in non_blank[:200] if try_parse_number(v) is not None)
            n_emails  = sum(1 for v in non_blank[:200] if EMAIL_RE.match(str(v).strip()))
            n_phones  = sum(1 for v in non_blank[:200] if PHONE_RE.match(str(v).strip()) and not NUMBER_RE.match(str(v).strip().replace(" ","").replace("-","")))
            sample_n  = min(len(non_blank), 200)

            if n_dates / max(sample_n, 1) > 0.7:
                inferred_type = "date"
                # Find most common date format
                fmts = []
                for v in non_blank[:50]:
                    parsed = try_parse_date(v)
                    if parsed: fmts.append(parsed[1])
                if fmts:
                    date_format = Counter(fmts).most_common(1)[0][0]
            elif n_emails / max(sample_n, 1) > 0.7:
                inferred_type = "email"
            elif n_nums / max(sample_n, 1) > 0.85:
                inferred_type = "number"
            elif n_phones / max(sample_n, 1) > 0.7:
                inferred_type = "phone"
            elif len(unique_vals) <= 20 and len(unique_vals) > 1:
                inferred_type = "categorical"

        # Whitespace issues
        whitespace_count = sum(1 for v in values if isinstance(v, str) and v != v.strip())

        # Case inconsistency (for text)
        case_issues = 0
        if inferred_type in ("text", "categorical", "email"):
            # Group originals by their lowercased version in one pass — O(n)
            groups = {}
            for v in non_blank:
                key = str(v).strip().lower()
                orig = str(v).strip()
                if key not in groups: groups[key] = {}
                groups[key][orig] = groups[key].get(orig, 0) + 1
            for variants in groups.values():
                if len(variants) > 1:
                    case_issues += sum(variants.values()) - max(variants.values())

        # Format inconsistency for dates
        format_issues = 0
        if inferred_type == "date" and date_format:
            for v in non_blank[:500]:
                parsed = try_parse_date(v)
                if parsed and parsed[1] != date_format:
                    format_issues += 1

        # Email validity
        email_invalid = 0
        if inferred_type == "email":
            email_invalid = sum(1 for v in non_blank if not EMAIL_RE.match(str(v).strip()))

        # Number outliers
        outlier_count = 0
        negative_count = 0
        if inferred_type == "number":
            nums = [try_parse_number(v) for v in non_blank]
            nums = [n for n in nums if n is not None]
            outlier_count = len(detect_outliers(nums))
            negative_count = sum(1 for n in nums if n < 0)

        # Sensitivity
        sens, is_pii = detect_sensitivity(col)

        # Build issues list
        issues = []
        suggestions = []

        if null_count > 0:
            issues.append({
                "type": "missing",
                "severity": "high" if null_pct > 30 else "medium" if null_pct > 5 else "low",
                "count": null_count,
                "message": f"{null_count} missing values ({null_pct}%)"
            })
            if inferred_type == "number":
                suggestions.append({"action":"fill_missing_mean",  "label":"Fill with column mean"})
                suggestions.append({"action":"fill_missing_median","label":"Fill with column median"})
                suggestions.append({"action":"fill_missing_zero",  "label":"Fill with zero"})
            elif inferred_type == "categorical":
                suggestions.append({"action":"fill_missing_mode",    "label":"Fill with most common value"})
                suggestions.append({"action":"fill_missing_unknown", "label":"Fill with 'Unknown'"})
            elif inferred_type == "date":
                suggestions.append({"action":"fill_missing_today",   "label":"Fill with today's date"})
            else:
                suggestions.append({"action":"fill_missing_unknown", "label":"Fill with 'Unknown'"})
            suggestions.append({"action":"drop_rows_missing", "label":"Drop rows where this is missing"})
            suggestions.append({"action":"keep_missing",       "label":"Keep as null (no change)"})

        if whitespace_count > 0:
            issues.append({
                "type": "whitespace",
                "severity": "low",
                "count": whitespace_count,
                "message": f"{whitespace_count} values have extra whitespace"
            })
            suggestions.append({"action":"trim_whitespace", "label":"Trim leading/trailing spaces", "default": True})

        if case_issues > 0:
            issues.append({
                "type": "case",
                "severity": "medium",
                "count": case_issues,
                "message": f"{case_issues} values differ only by capitalisation"
            })
            suggestions.append({"action":"standardize_lower", "label":"Convert to lowercase"})
            suggestions.append({"action":"standardize_upper", "label":"Convert to UPPERCASE"})
            suggestions.append({"action":"standardize_title", "label":"Convert to Title Case"})

        if format_issues > 0:
            issues.append({
                "type": "format",
                "severity": "high",
                "count": format_issues,
                "message": f"{format_issues} dates in mixed formats (expected {date_format})"
            })
            suggestions.append({"action":"standardize_date_iso", "label":"Standardise all dates to YYYY-MM-DD", "default": True})

        if email_invalid > 0:
            issues.append({
                "type": "invalid_email",
                "severity": "high",
                "count": email_invalid,
                "message": f"{email_invalid} invalid email addresses"
            })
            suggestions.append({"action":"drop_rows_invalid_email", "label":"Drop rows with invalid emails"})
            suggestions.append({"action":"null_invalid_email",      "label":"Set invalid emails to null"})

        if outlier_count > 0:
            issues.append({
                "type": "outliers",
                "severity": "medium",
                "count": outlier_count,
                "message": f"{outlier_count} numeric outliers detected (IQR rule)"
            })
            suggestions.append({"action":"cap_outliers",  "label":"Cap outliers at 1.5×IQR boundaries"})
            suggestions.append({"action":"drop_outliers", "label":"Drop rows with outliers"})
            suggestions.append({"action":"keep_outliers", "label":"Keep outliers as-is"})

        if negative_count > 0 and any(kw in col.lower() for kw in ["amount","price","salary","count","qty","quantity","stock"]):
            issues.append({
                "type": "negative",
                "severity": "medium",
                "count": negative_count,
                "message": f"{negative_count} negative values in a column that should be positive"
            })
            suggestions.append({"action":"abs_values",       "label":"Take absolute value"})
            suggestions.append({"action":"drop_rows_negative","label":"Drop rows with negative values"})
            suggestions.append({"action":"null_negative",    "label":"Set negative values to null"})

        # Get sample values
        samples = list(unique_vals)[:5] if unique_vals else []

        report["columns"].append({
            "name":            col,
            "inferred_type":   inferred_type,
            "date_format":     date_format,
            "null_count":      null_count,
            "null_pct":        null_pct,
            "unique_count":    len(unique_vals),
            "completeness":    round((1 - null_count / total_rows) * 100, 1),
            "sensitivity":     sens,
            "is_pii":          is_pii,
            "issues":          issues,
            "suggestions":     suggestions,
            "samples":         samples,
            "whitespace_count": whitespace_count,
            "case_issues":     case_issues,
            "format_issues":   format_issues,
            "outlier_count":   outlier_count,
            "negative_count":  negative_count,
            "issue_count":     len(issues),
        })

    # ── 3. Recommended global rules ──────────────────────────────────────────
    if report["fully_duplicate_rows"] > 0:
        report["recommended_rules"].append({
            "rule":    "remove_full_duplicates",
            "label":   f"Remove {report['fully_duplicate_rows']} fully duplicate rows",
            "default": True,
        })

    if report["near_duplicate_rows"] > 0:
        report["recommended_rules"].append({
            "rule":    "remove_near_duplicates",
            "label":   f"Remove {report['near_duplicate_rows']} near-duplicate rows (differ only by case/whitespace)",
            "default": False,
        })

    # Detect potential primary key
    pk_candidate = None
    for c in report["columns"]:
        if c["null_count"] == 0 and c["unique_count"] == total_rows:
            if any(kw in c["name"].lower() for kw in ["id","key","no","num","code"]):
                pk_candidate = c["name"]
                break
    if not pk_candidate:
        for c in report["columns"]:
            if c["null_count"] == 0 and c["unique_count"] == total_rows:
                pk_candidate = c["name"]; break
    report["suggested_primary_key"] = pk_candidate

    if pk_candidate:
        report["recommended_rules"].append({
            "rule":     "dedupe_by_pk",
            "label":    f"Deduplicate by '{pk_candidate}' (keep first occurrence)",
            "default":  True,
            "param":    pk_candidate,
        })

    # ── 4. Compute issue stats ───────────────────────────────────────────────
    total_issues   = sum(c["issue_count"] for c in report["columns"])
    affected_cols  = sum(1 for c in report["columns"] if c["issue_count"] > 0)
    clean_cols     = report["total_cols"] - affected_cols

    # Overall data health pre-cleaning
    avg_completeness = sum(c["completeness"] for c in report["columns"]) / max(report["total_cols"],1)
    issue_score      = max(0, 100 - (total_issues / max(report["total_cols"],1)) * 8)
    health_score     = round((avg_completeness * 0.6 + issue_score * 0.4), 1)

    report["stats"] = {
        "total_issues":   total_issues,
        "affected_cols":  affected_cols,
        "clean_cols":     clean_cols,
        "avg_completeness": round(avg_completeness, 1),
        "health_score":   health_score,
        "pii_columns":    sum(1 for c in report["columns"] if c["is_pii"]),
        "sensitivity_breakdown": dict(Counter(c["sensitivity"] for c in report["columns"])),
    }

    return report


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python -m etl.smart_analyzer <file.csv>")
        sys.exit(1)
    rep = analyze_csv(sys.argv[1])
    # Don't print the row data
    out = {k:v for k,v in rep.items() if k != "preview_rows"}
    print(json.dumps(out, indent=2, default=str))
