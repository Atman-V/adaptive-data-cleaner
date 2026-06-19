"""
api_server.py — FastAPI backend for the Adaptive Data Cleaner Dashboard.

Endpoints (unchanged from the original http.server implementation, so
dashboard/index.html keeps working with zero changes):
  POST /analyze       — accepts a CSV or Excel (.xlsx/.xls) file, returns deep analysis report (no cleaning yet)
  POST /clean         — accepts {upload_path, report, rules}, runs cleaning, returns result
  GET  /status        — server health
  GET  /download/<f>  — downloads a processed file
  GET  /runs          — list previous runs
  GET  /run/<run_id>  — get specific run

Usage:
    python api_server.py
    uvicorn api_server:app --host localhost --port 7432
"""

import datetime
import glob
import json
import os
import re
import sys
import traceback

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

ROOT = os.path.dirname(__file__)
sys.path.insert(0, ROOT)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

LOGS_DIR      = os.path.join(ROOT, "logs")
UPLOADS_DIR   = os.path.join(ROOT, "data", "uploads")
PROCESSED_DIR = os.path.join(ROOT, "data", "processed")
PORT          = int(sys.argv[1]) if len(sys.argv) > 1 else 7432

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

app = FastAPI(title="Adaptive Data Cleaner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _json(code, obj):
    """Mirrors the old self._json(code, obj) — same default=str JSON encoding."""
    return Response(
        content=json.dumps(obj, default=str),
        status_code=code,
        media_type="application/json",
    )


def _safe_filename(name):
    base = os.path.basename(name)
    base = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem, ext = os.path.splitext(base)
    return f"{stem}_{ts}{ext}"


@app.get("/status")
def status():
    return _json(200, {"status": "ok", "port": PORT})


@app.get("/runs")
def list_runs():
    files = sorted(glob.glob(os.path.join(LOGS_DIR, "*.json")), reverse=True)
    runs = []
    for f in files[:20]:
        try:
            with open(f, encoding="utf-8") as fp:
                d = json.load(fp)
            runs.append({
                "run_id":   d.get("run_id", os.path.basename(f).replace(".json", "")),
                "filename": d.get("filename", "—"),
                "rows":     d.get("cleaned_rows", d.get("original_rows", 0)),
                "dropped":  d.get("rows_dropped", 0),
                "elapsed":  d.get("elapsed_sec", 0),
                "status":   d.get("status", "SUCCESS"),
            })
        except Exception:
            pass
    return _json(200, runs)


@app.get("/run/{run_id}")
def get_run(run_id: str):
    log_file = os.path.join(LOGS_DIR, f"{run_id}.json")
    if os.path.exists(log_file):
        with open(log_file, encoding="utf-8") as f:
            return Response(content=f.read(), media_type="application/json")
    return _json(404, {"error": "Run not found"})


@app.get("/download/{filename}")
def download(filename: str):
    safe = re.sub(r"[^a-zA-Z0-9._-]", "", filename)
    fpath = os.path.join(PROCESSED_DIR, safe)
    if os.path.exists(fpath):
        return FileResponse(fpath, media_type="text/csv", filename=safe)
    return _json(404, {"error": "File not found"})


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    file_data = await file.read()
    if not file_data:
        return _json(400, {"error": "No file data"})

    safe = _safe_filename(file.filename or "upload.csv")
    save_path = os.path.join(UPLOADS_DIR, safe)
    with open(save_path, "wb") as f:
        f.write(file_data)
    print(f"\n  Received for analysis: {file.filename} → {save_path}")

    try:
        from etl.smart_analyzer import analyze_csv
        report = analyze_csv(save_path)
        report["_upload_path"] = save_path
        print(f"  Analysis complete: {report['stats']['total_issues']} issues found in {report['stats']['affected_cols']} columns")
        return _json(200, report)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  Analysis ERROR: {e}\n{tb}")
        return _json(500, {"error": str(e), "traceback": tb})


@app.post("/clean")
async def clean(payload: dict):
    upload_path = payload.get("upload_path")
    report      = payload.get("report")
    rules       = payload.get("rules", {})

    if not upload_path or not os.path.exists(upload_path):
        return _json(400, {"error": "upload_path missing or invalid"})
    if not report:
        return _json(400, {"error": "report missing"})

    print(f"\n  Cleaning: {os.path.basename(upload_path)}")
    print(f"  Rules: {len(rules.get('columns', {}))} column rules · {len(rules.get('global', {}))} global rules")

    try:
        from etl.smart_cleaner import apply_cleaning
        result = apply_cleaning(upload_path, report, rules)

        run_id = f"RUN_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        result["run_id"] = run_id
        log_path = os.path.join(LOGS_DIR, f"{run_id}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            slim = {k: v for k, v in result.items() if k not in ("preview",)}
            json.dump(slim, f, indent=2, default=str)

        print(f"  Cleaning complete: {result['original_rows']} → {result['cleaned_rows']} rows in {result['elapsed_sec']}s")
        return _json(200, result)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  Cleaning ERROR: {e}\n{tb}")
        return _json(500, {"error": str(e), "traceback": tb})


def run():
    import uvicorn
    print(f"""
╔══════════════════════════════════════════════════════════╗
║         Adaptive Data Cleaner API Server (FastAPI)        ║
║         http://localhost:{PORT}                              ║
╠══════════════════════════════════════════════════════════╣
║  Endpoints:                                              ║
║    POST  /analyze   — analyse uploaded CSV/Excel         ║
║    POST  /clean     — apply user-selected cleaning rules ║
║    GET   /download/<file>  — download cleaned CSV        ║
║    GET   /runs      — list previous runs                 ║
║                                                          ║
║  1. Keep this window open                                ║
║  2. Open dashboard/index.html in your browser            ║
║  3. Upload → Review issues → Pick rules → Download       ║
╚══════════════════════════════════════════════════════════╝
""")
    uvicorn.run(app, host="localhost", port=PORT, log_level="warning")


if __name__ == "__main__":
    run()
