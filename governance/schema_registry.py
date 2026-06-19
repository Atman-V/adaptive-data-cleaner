"""
Schema Registry — column-level metadata for all tables.
Maps (table, column) → sensitivity, PII flag, owner, description.
"""

SCHEMA_REGISTRY = {
    "raw_customer_profiles": {
        "full_name":    {"sensitivity": "PII",      "is_pii": True,  "owner": "CRM Team",     "description": "Customer legal full name"},
        "email":        {"sensitivity": "PII",      "is_pii": True,  "owner": "CRM Team",     "description": "Primary email address"},
        "phone":        {"sensitivity": "PII",      "is_pii": True,  "owner": "CRM Team",     "description": "Mobile or landline number"},
        "dob":          {"sensitivity": "PII",      "is_pii": True,  "owner": "CRM Team",     "description": "Date of birth"},
        "address":      {"sensitivity": "PII",      "is_pii": True,  "owner": "CRM Team",     "description": "Residential address"},
        "customer_id":  {"sensitivity": "Internal", "is_pii": False, "owner": "CRM Team",     "description": "Unique customer identifier"},
        "account_type": {"sensitivity": "Internal", "is_pii": False, "owner": "CRM Team",     "description": "Customer account tier"},
        "city":         {"sensitivity": "Public",   "is_pii": False, "owner": "CRM Team",     "description": "City of residence"},
        "country":      {"sensitivity": "Public",   "is_pii": False, "owner": "CRM Team",     "description": "Country of residence"},
        "created_at":   {"sensitivity": "Internal", "is_pii": False, "owner": "CRM Team",     "description": "Account creation timestamp"},
    },
    "raw_transaction_logs": {
        "txn_id":         {"sensitivity": "Internal",  "is_pii": False, "owner": "Finance Team", "description": "Unique transaction ID"},
        "customer_id":    {"sensitivity": "PII",       "is_pii": True,  "owner": "Finance Team", "description": "Reference to customer"},
        "amount":         {"sensitivity": "Financial", "is_pii": False, "owner": "Finance Team", "description": "Transaction amount"},
        "currency":       {"sensitivity": "Internal",  "is_pii": False, "owner": "Finance Team", "description": "Currency code (ISO 4217)"},
        "txn_date":       {"sensitivity": "Internal",  "is_pii": False, "owner": "Finance Team", "description": "Date of transaction"},
        "txn_type":       {"sensitivity": "Internal",  "is_pii": False, "owner": "Finance Team", "description": "Type of transaction"},
        "merchant":       {"sensitivity": "Public",    "is_pii": False, "owner": "Finance Team", "description": "Merchant name"},
        "status":         {"sensitivity": "Internal",  "is_pii": False, "owner": "Finance Team", "description": "Transaction status"},
        "account_number": {"sensitivity": "Financial", "is_pii": True,  "owner": "Finance Team", "description": "Bank account number"},
        "card_last4":     {"sensitivity": "Financial", "is_pii": True,  "owner": "Finance Team", "description": "Last 4 digits of card"},
    },
    "raw_hr_records": {
        "emp_id":            {"sensitivity": "Internal",  "is_pii": False, "owner": "HR Team",      "description": "Unique employee ID"},
        "full_name":         {"sensitivity": "PII",       "is_pii": True,  "owner": "HR Team",      "description": "Employee full name"},
        "email":             {"sensitivity": "PII",       "is_pii": True,  "owner": "HR Team",      "description": "Work email address"},
        "department":        {"sensitivity": "Internal",  "is_pii": False, "owner": "HR Team",      "description": "Employee department"},
        "designation":       {"sensitivity": "Internal",  "is_pii": False, "owner": "HR Team",      "description": "Job title/designation"},
        "salary":            {"sensitivity": "Financial", "is_pii": False, "owner": "HR Team",      "description": "Annual salary"},
        "join_date":         {"sensitivity": "Internal",  "is_pii": False, "owner": "HR Team",      "description": "Employment start date"},
        "manager_id":        {"sensitivity": "Internal",  "is_pii": False, "owner": "HR Team",      "description": "Direct manager employee ID"},
        "performance_score": {"sensitivity": "Internal",  "is_pii": False, "owner": "HR Team",      "description": "Annual performance rating (1-5)"},
        "is_active":         {"sensitivity": "Internal",  "is_pii": False, "owner": "HR Team",      "description": "Active employment status flag"},
    },
    "raw_product_catalog": {
        "product_id":   {"sensitivity": "Public",   "is_pii": False, "owner": "Product Team",  "description": "Unique product identifier"},
        "product_name": {"sensitivity": "Public",   "is_pii": False, "owner": "Product Team",  "description": "Product display name"},
        "category":     {"sensitivity": "Public",   "is_pii": False, "owner": "Product Team",  "description": "Top-level product category"},
        "sub_category": {"sensitivity": "Public",   "is_pii": False, "owner": "Product Team",  "description": "Product sub-category"},
        "price":        {"sensitivity": "Public",   "is_pii": False, "owner": "Finance Team",  "description": "Retail price"},
        "stock_qty":    {"sensitivity": "Internal", "is_pii": False, "owner": "Ops Team",      "description": "Current stock quantity"},
        "supplier":     {"sensitivity": "Internal", "is_pii": False, "owner": "Ops Team",      "description": "Supplier company name"},
        "last_updated": {"sensitivity": "Internal", "is_pii": False, "owner": "Product Team",  "description": "Catalog last update date"},
    },
    "raw_sensor_telemetry": {
        "sensor_id":   {"sensitivity": "Internal", "is_pii": False, "owner": "Ops Team",   "description": "Unique sensor identifier"},
        "timestamp":   {"sensitivity": "Internal", "is_pii": False, "owner": "Ops Team",   "description": "Reading timestamp"},
        "location":    {"sensitivity": "Internal", "is_pii": False, "owner": "Ops Team",   "description": "Physical sensor location zone"},
        "temperature": {"sensitivity": "Public",   "is_pii": False, "owner": "Ops Team",   "description": "Temperature reading in Celsius"},
        "humidity":    {"sensitivity": "Public",   "is_pii": False, "owner": "Ops Team",   "description": "Relative humidity percentage"},
        "pressure":    {"sensitivity": "Public",   "is_pii": False, "owner": "Ops Team",   "description": "Atmospheric pressure in hPa"},
        "battery_pct": {"sensitivity": "Internal", "is_pii": False, "owner": "Ops Team",   "description": "Sensor battery percentage remaining"},
        "alert_flag":  {"sensitivity": "Internal", "is_pii": False, "owner": "Ops Team",   "description": "Alert triggered flag (0/1)"},
    },
    "raw_audit_trail": {
        "audit_id":   {"sensitivity": "Internal",         "is_pii": False, "owner": "Security Team", "description": "Unique audit record ID"},
        "user_id":    {"sensitivity": "PII",              "is_pii": True,  "owner": "Security Team", "description": "Acting user identifier"},
        "action":     {"sensitivity": "Internal",         "is_pii": False, "owner": "Security Team", "description": "Action performed"},
        "entity":     {"sensitivity": "Internal",         "is_pii": False, "owner": "Security Team", "description": "Entity type affected"},
        "entity_id":  {"sensitivity": "Internal",         "is_pii": False, "owner": "Security Team", "description": "Affected entity ID"},
        "ip_address": {"sensitivity": "PII",              "is_pii": True,  "owner": "Security Team", "description": "Source IP address"},
        "timestamp":  {"sensitivity": "Internal",         "is_pii": False, "owner": "Security Team", "description": "Event timestamp"},
        "status":     {"sensitivity": "Internal",         "is_pii": False, "owner": "Security Team", "description": "Audit event outcome"},
    },
}


def get_all_entries():
    """Flatten registry into list of (table, column, metadata) tuples."""
    entries = []
    for table, columns in SCHEMA_REGISTRY.items():
        for col, meta in columns.items():
            entries.append((table, col, meta))
    return entries


def get_sensitivity_summary():
    """Return count of columns per sensitivity label."""
    counts = {}
    for _, columns in SCHEMA_REGISTRY.items():
        for _, meta in columns.items():
            label = meta["sensitivity"]
            counts[label] = counts.get(label, 0) + 1
    return counts
