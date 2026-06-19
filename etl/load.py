"""
etl/load.py — Step 4: Populate consumption zone tables from curated data.
Note: Uses a 730-day lookback window to accommodate demo dataset date range (2023-2024).
"""
import sqlite3, datetime, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "warehouse.db")

# Use max date in data rather than today, so active-customers window always makes sense
def _get_cutoff(conn):
    row = conn.execute("SELECT MAX(txn_date) FROM curated_transaction_logs").fetchone()
    max_date = row[0] if row and row[0] else datetime.date.today().isoformat()
    max_dt = datetime.date.fromisoformat(str(max_date)[:10])
    cutoff = (max_dt - datetime.timedelta(days=90)).isoformat()
    return cutoff

def load_consumption(conn=None):
    close_after = conn is None
    if conn is None:
        conn = sqlite3.connect(DB_PATH)

    cutoff = _get_cutoff(conn)

    queries = {
        "cons_active_customers": f"""
            INSERT INTO cons_active_customers
                (customer_id, full_name, email, account_type, country, last_txn_date, txn_count)
            SELECT c.customer_id, c.full_name, c.email, c.account_type, c.country,
                   MAX(t.txn_date) AS last_txn_date, COUNT(t.txn_id) AS txn_count
            FROM curated_customer_profiles c
            JOIN curated_transaction_logs t ON c.customer_id = t.customer_id
            WHERE t.txn_date >= '{cutoff}'
              AND (c._quality_flag IS NULL OR c._quality_flag != 'POOR')
            GROUP BY c.customer_id, c.full_name, c.email, c.account_type, c.country
        """,
        "cons_high_value_transactions": """
            INSERT INTO cons_high_value_transactions
                (txn_id, customer_id, amount, amount_usd, currency, txn_date, merchant, status)
            SELECT txn_id, customer_id, amount, amount_usd, currency, txn_date, merchant, status
            FROM curated_transaction_logs
            WHERE CAST(amount_usd AS REAL) > 10000
              AND status NOT IN ('Failed','Cancelled')
        """,
        "cons_department_headcount": """
            INSERT INTO cons_department_headcount
                (department, headcount, avg_salary, avg_performance, active_count)
            SELECT department, COUNT(*) AS headcount,
                   ROUND(AVG(CAST(salary AS REAL)),2) AS avg_salary,
                   ROUND(AVG(CAST(performance_score AS REAL)),2) AS avg_performance,
                   SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) AS active_count
            FROM curated_hr_records
            GROUP BY department
        """,
        "cons_low_stock_products": """
            INSERT INTO cons_low_stock_products
                (product_id, product_name, category, price, stock_qty, supplier)
            SELECT product_id, product_name, category, price, stock_qty, supplier
            FROM curated_product_catalog
            WHERE CAST(stock_qty AS INTEGER) < 50
        """,
        "cons_sensor_alerts": """
            INSERT INTO cons_sensor_alerts
                (sensor_id, timestamp, location, temperature, humidity, battery_pct, alert_flag, is_anomaly)
            SELECT sensor_id, timestamp, location, temperature, humidity, battery_pct, alert_flag, is_anomaly
            FROM curated_sensor_telemetry
            WHERE alert_flag = 1
        """,
    }

    summary = {}
    for table, sql in queries.items():
        conn.execute(f"DELETE FROM {table}")
        conn.execute(sql)
        conn.commit()
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        summary[table] = count
        print(f"  [LOAD] {table}: {count:,} rows")

    if close_after:
        conn.close()
    return summary

if __name__ == "__main__":
    load_consumption()
