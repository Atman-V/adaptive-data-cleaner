-- =============================================================================
-- Data Modernization & Migration Pipeline — 3-Zone Warehouse Schema (SQLite)
-- Zones: RAW → CURATED → CONSUMPTION
-- =============================================================================

-- ─── RAW ZONE ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw_customer_profiles (
    customer_id   TEXT,
    full_name     TEXT,
    email         TEXT,
    phone         TEXT,
    dob           TEXT,
    address       TEXT,
    city          TEXT,
    country       TEXT,
    account_type  TEXT,
    created_at    TEXT,
    -- pipeline metadata
    _ingested_at  TIMESTAMP,
    _source_file  TEXT,
    _row_hash     TEXT
);

CREATE TABLE IF NOT EXISTS raw_transaction_logs (
    txn_id         TEXT,
    customer_id    TEXT,
    amount         REAL,
    currency       TEXT,
    txn_date       TEXT,
    txn_type       TEXT,
    merchant       TEXT,
    status         TEXT,
    account_number TEXT,
    card_last4     TEXT,
    _ingested_at   TIMESTAMP,
    _source_file   TEXT,
    _row_hash      TEXT
);

CREATE TABLE IF NOT EXISTS raw_hr_records (
    emp_id            TEXT,
    full_name         TEXT,
    email             TEXT,
    department        TEXT,
    designation       TEXT,
    salary            REAL,
    join_date         TEXT,
    manager_id        TEXT,
    performance_score INTEGER,
    is_active         INTEGER,
    _ingested_at      TIMESTAMP,
    _source_file      TEXT,
    _row_hash         TEXT
);

CREATE TABLE IF NOT EXISTS raw_product_catalog (
    product_id   TEXT,
    product_name TEXT,
    category     TEXT,
    sub_category TEXT,
    price        REAL,
    stock_qty    INTEGER,
    supplier     TEXT,
    last_updated TEXT,
    _ingested_at TIMESTAMP,
    _source_file TEXT,
    _row_hash    TEXT
);

CREATE TABLE IF NOT EXISTS raw_sensor_telemetry (
    sensor_id    TEXT,
    timestamp    TEXT,
    location     TEXT,
    temperature  REAL,
    humidity     REAL,
    pressure     REAL,
    battery_pct  REAL,
    alert_flag   INTEGER,
    _ingested_at TIMESTAMP,
    _source_file TEXT,
    _row_hash    TEXT
);

CREATE TABLE IF NOT EXISTS raw_audit_trail (
    audit_id     TEXT,
    user_id      TEXT,
    action       TEXT,
    entity       TEXT,
    entity_id    TEXT,
    ip_address   TEXT,
    timestamp    TEXT,
    status       TEXT,
    _ingested_at TIMESTAMP,
    _source_file TEXT,
    _row_hash    TEXT
);

-- ─── CURATED ZONE ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS curated_customer_profiles (
    customer_id   TEXT,
    full_name     TEXT,
    email         TEXT,
    phone         TEXT,
    dob           TEXT,
    address       TEXT,
    city          TEXT,
    country       TEXT,
    account_type  TEXT,
    created_at    TEXT,
    -- derived fields
    age_group     TEXT,
    -- governance
    _cleansed_at  TIMESTAMP,
    _is_duplicate INTEGER DEFAULT 0,
    _quality_flag TEXT DEFAULT 'OK'
);

CREATE TABLE IF NOT EXISTS curated_transaction_logs (
    txn_id          TEXT,
    customer_id     TEXT,
    amount          REAL,
    amount_usd      REAL,
    currency        TEXT,
    txn_date        TEXT,
    txn_type        TEXT,
    merchant        TEXT,
    status          TEXT,
    account_number  TEXT,
    card_last4      TEXT,
    _cleansed_at    TIMESTAMP,
    _is_duplicate   INTEGER DEFAULT 0,
    _quality_flag   TEXT DEFAULT 'OK'
);

CREATE TABLE IF NOT EXISTS curated_hr_records (
    emp_id            TEXT,
    full_name         TEXT,
    email             TEXT,
    department        TEXT,
    designation       TEXT,
    salary            REAL,
    join_date         TEXT,
    manager_id        TEXT,
    performance_score INTEGER,
    is_active         INTEGER,
    tenure_years      REAL,
    _cleansed_at      TIMESTAMP,
    _is_duplicate     INTEGER DEFAULT 0,
    _quality_flag     TEXT DEFAULT 'OK'
);

CREATE TABLE IF NOT EXISTS curated_product_catalog (
    product_id    TEXT,
    product_name  TEXT,
    category      TEXT,
    sub_category  TEXT,
    price         REAL,
    stock_qty     INTEGER,
    supplier      TEXT,
    last_updated  TEXT,
    _cleansed_at  TIMESTAMP,
    _is_duplicate INTEGER DEFAULT 0,
    _quality_flag TEXT DEFAULT 'OK'
);

CREATE TABLE IF NOT EXISTS curated_sensor_telemetry (
    sensor_id    TEXT,
    timestamp    TEXT,
    location     TEXT,
    temperature  REAL,
    humidity     REAL,
    pressure     REAL,
    battery_pct  REAL,
    alert_flag   INTEGER,
    is_anomaly   INTEGER DEFAULT 0,
    _cleansed_at  TIMESTAMP,
    _is_duplicate INTEGER DEFAULT 0,
    _quality_flag TEXT DEFAULT 'OK'
);

CREATE TABLE IF NOT EXISTS curated_audit_trail (
    audit_id      TEXT,
    user_id       TEXT,
    action        TEXT,
    entity        TEXT,
    entity_id     TEXT,
    ip_address    TEXT,
    ip_country    TEXT,
    timestamp     TEXT,
    status        TEXT,
    _cleansed_at  TIMESTAMP,
    _is_duplicate INTEGER DEFAULT 0,
    _quality_flag TEXT DEFAULT 'OK'
);

-- ─── CONSUMPTION ZONE ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cons_active_customers (
    customer_id  TEXT,
    full_name    TEXT,
    email        TEXT,
    account_type TEXT,
    country      TEXT,
    last_txn_date TEXT,
    txn_count    INTEGER
);

CREATE TABLE IF NOT EXISTS cons_high_value_transactions (
    txn_id       TEXT,
    customer_id  TEXT,
    amount       REAL,
    amount_usd   REAL,
    currency     TEXT,
    txn_date     TEXT,
    merchant     TEXT,
    status       TEXT
);

CREATE TABLE IF NOT EXISTS cons_department_headcount (
    department      TEXT,
    headcount       INTEGER,
    avg_salary      REAL,
    avg_performance REAL,
    active_count    INTEGER
);

CREATE TABLE IF NOT EXISTS cons_low_stock_products (
    product_id   TEXT,
    product_name TEXT,
    category     TEXT,
    price        REAL,
    stock_qty    INTEGER,
    supplier     TEXT
);

CREATE TABLE IF NOT EXISTS cons_sensor_alerts (
    sensor_id   TEXT,
    timestamp   TEXT,
    location    TEXT,
    temperature REAL,
    humidity    REAL,
    battery_pct REAL,
    alert_flag  INTEGER,
    is_anomaly  INTEGER
);

-- ─── GOVERNANCE CATALOG ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS governance_catalog (
    table_name           TEXT NOT NULL,
    column_name          TEXT NOT NULL,
    sensitivity_label    TEXT NOT NULL,   -- PII / Financial / Public / Internal
    is_pii               INTEGER NOT NULL, -- 0 or 1
    owner                TEXT,
    description          TEXT,
    last_classified_at   TIMESTAMP,
    PRIMARY KEY (table_name, column_name)
);

-- ─── PIPELINE RUN LOG ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pipeline_run_log (
    run_id      TEXT,
    step        TEXT,
    status      TEXT,
    rows_in     INTEGER,
    rows_out    INTEGER,
    elapsed_sec REAL,
    started_at  TIMESTAMP,
    message     TEXT
);
