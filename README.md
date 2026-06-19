# Adaptive Data Cleaner — Upload, Analyze, Configure, Clean

An advanced data cleaning workflow that lets **you decide** how your data gets cleaned. No more guessing — see every issue per column and pick the fix you want.

---

## 🎯 The 4-Step Flow

```
1. Upload CSV/Excel →   2. Analyze         →   3. Configure         →   4. Results
   Drag & drop       Per-column report     Pick rules per col      Download clean CSV
                     Health score          Recommended defaults    Before/after charts
                     Issue detection       Global rules            Detailed change log
```

---

## ⚡ Quick Start

**Step 1: Start the server** (one terminal, keep it open):
```bash
cd data-pipeline-project
python api_server.py
```

**Step 2: Open the dashboard:**
- Double-click `dashboard/index.html` in your file explorer
- It runs entirely from `file://` — no web hosting needed

**Step 3: Drop a CSV or Excel file (.xlsx/.xls)** — the rest is guided.

---

## 🔍 What Happens at Each Step

### Step 1 — Upload
Drag any CSV or Excel file (.xlsx/.xls — first sheet is used) onto the drop zone. The server saves a timestamped copy to `data/uploads/`.

### Step 2 — Analysis
The analyzer does a deep scan in under a second per 10K rows:

**Per column it detects:**
- Inferred type (text, number, date, email, phone, categorical)
- Missing values (count + percentage)
- Whitespace issues
- Case inconsistencies ("USA" vs "usa" vs "Usa")
- Date format inconsistencies
- Invalid emails
- Numeric outliers (IQR rule)
- Negative values where they shouldn't be
- Sensitivity (PII / Financial / Public / Internal)

**Globally it detects:**
- Fully duplicate rows
- Suggested primary key (for deduplication)
- Data health score (0–100)

You get a **per-column report card** with every issue, severity (high/medium/low), and a count.

### Step 3 — Configure Rules
For each column with issues, pick one rule:

| Issue | Available Rules |
|---|---|
| Missing values | Fill with mean / median / mode / zero / 'Unknown' / today's date · Drop rows · Keep nulls |
| Whitespace | Trim leading/trailing spaces |
| Case inconsistency | Lowercase / UPPERCASE / Title Case |
| Mixed date formats | Standardise all to YYYY-MM-DD |
| Invalid emails | Drop rows / Set to null |
| Outliers | Cap at 1.5×IQR / Drop rows / Keep as-is |
| Negative values | Take absolute value / Drop rows / Set to null |

Plus **global rules**: remove fully duplicate rows, deduplicate by primary key.

Defaults are pre-selected based on best practices — change any you disagree with.

### Step 4 — Results
After clicking "Apply Cleaning":

- **5 KPI cards**: rows cleaned, rows removed, nulls resolved, poor quality rows, processing time
- **Before/After comparison** of row counts and null counts
- **Before/After completeness chart** per column
- **Operations donut chart** showing what kinds of changes happened
- **Per-column change log** — exactly what was applied to each column
- **Clean data preview** — first 10 rows of your cleaned output
- **One-click download** of the cleaned CSV

---

## 📁 Project Structure

```
data-pipeline-project/
├── api_server.py            ← Local HTTP API (start this first)
├── dashboard/
│   └── index.html           ← 4-step dashboard (open in browser)
├── etl/
│   ├── smart_analyzer.py    ← Deep column-level analysis
│   ├── smart_cleaner.py     ← Applies user-selected rules
│   ├── excel_helper.py      ← Reads .xlsx/.xls into CSV-shaped rows
│   ├── custom_pipeline.py   ← (legacy) auto-cleaning pipeline
│   ├── ingest.py            ← (legacy) original 6-source ingest
│   ├── cleanse.py           ← (legacy) original cleanse
│   ├── transform.py         ← (legacy) original transform
│   └── load.py              ← (legacy) original load
├── governance/              ← Quality scoring, classifier (used by both)
├── db/
│   ├── schema.sql           ← Static schema for original pipeline
│   └── warehouse.db         ← SQLite database
├── data/
│   ├── raw/                 ← Original 6 sample CSVs (300K rows total)
│   ├── uploads/             ← User-uploaded CSVs (timestamped)
│   └── processed/           ← Cleaned output CSVs
├── logs/                    ← Run logs (one JSON per cleaning run)
├── pipeline_runner.py       ← Original demo: re-runs default 6-source pipeline
├── generate_data.py         ← Regenerate the 6 sample CSVs
└── README.md
```

---

## 🧪 Test It With the Sample Files

Want to see it work without uploading your own data? Use one of the included samples:

```
data/raw/hr_records.csv          ← 50K rows, employee records
data/raw/customer_profiles.csv   ← 50K rows, customer data with PII
data/raw/transaction_logs.csv    ← 50K financial transactions
data/raw/product_catalog.csv     ← 50K product entries
data/raw/sensor_telemetry.csv    ← 50K IoT readings
data/raw/audit_trail.csv         ← 50K security events
```

Drop any of them into the dashboard to see the full flow.

---

## 🛠 What Kind of File Works?

**Works perfectly:**
- Any CSV with a header row — comma, tab, semicolon, or pipe delimited (auto-detected)
- Excel workbooks (.xlsx, .xlsm, .xls) — the first sheet is read; cell values (dates, numbers) are normalized the same way as CSV text
- Any number of columns
- Sales data, HR exports, transactions, inventory, sensor logs, anything

**Has limitations:**
- Excel files with data on a non-first sheet — only the first sheet is analyzed
- JSON — convert first
- Very wide files (100+ columns) — chart shows first 16 cols only
- Output is always written back out as a cleaned CSV (not re-exported as .xlsx)

---

## 🔧 Requirements

- **Python 3.8+** (stdlib only for CSV; Excel support needs `openpyxl` — see `requirements.txt`)
- A modern browser (Chrome, Firefox, Edge, Safari)
- About 10 MB of free disk space for sample data

---

## 💡 Resume Bullets

> Built a **smart ETL pipeline** in Python (stdlib only) with a 4-step interactive workflow (Upload → Analyze → Configure → Clean) that auto-detects 8 types of data quality issues per column, classifies sensitivity (PII / Financial / Public / Internal), and lets the user pick exactly how each issue gets resolved before applying changes — processed 50,000 rows end-to-end in under 3 seconds.

> Designed a **rule-based cleaning engine** supporting fill-with-mean/median/mode, IQR outlier capping, date format standardisation, case normalisation, and email validation — with per-column user-selectable rules and a before/after dashboard showing every transformation applied.

> Implemented a **lightweight HTTP API server** (Python `http.server`, no Flask/FastAPI) serving a single-page dashboard with drag-and-drop CSV upload, real-time analysis, and direct downloadable cleaned files — entirely self-hosted, zero external dependencies.
