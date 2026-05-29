CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    site_name TEXT NOT NULL,
    site_id INTEGER NOT NULL,
    address TEXT,
    contact_email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    bill_period_from TEXT NOT NULL,
    bill_period_to TEXT NOT NULL,
    bill_kwh REAL,
    bill_excl_vat REAL,
    bill_incl_vat REAL,
    dash_consumption REAL,
    dash_production REAL,
    dash_grid_import REAL,
    savings_excl_vat REAL,
    savings_incl_vat REAL,
    combined_rate REAL,
    variance_pct REAL,
    report_token TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS rate_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    charge_name TEXT NOT NULL,
    rate REAL NOT NULL,
    applies_to TEXT,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

INSERT OR IGNORE INTO settings VALUES ('dash_username', 'bruce');
INSERT OR IGNORE INTO settings VALUES ('dash_password', 'Mufasa123');
INSERT OR IGNORE INTO settings VALUES ('dash_url', 'https://www.dash-iot.com');
