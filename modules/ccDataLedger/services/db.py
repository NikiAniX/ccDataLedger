"""SQLite persistence (file on disk, survives restarts). No Flask imports."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS statements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file    TEXT NOT NULL UNIQUE,
    source_files   TEXT,                       -- JSON array of original file names
    cardholder     TEXT,
    imported_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS summary (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_id               INTEGER NOT NULL UNIQUE REFERENCES statements(id) ON DELETE CASCADE,
    total_payment_due          TEXT,
    minimum_payment_due        TEXT,
    statement_period           TEXT,
    payment_due_date           TEXT,
    statement_generation_date  TEXT,
    credit_card_number         TEXT,
    credit_limit               TEXT,
    available_credit_limit     TEXT,
    available_cash_limit       TEXT,
    previous_statement_dues    TEXT,
    payments_credits           TEXT,
    purchases_debit            TEXT,
    finance_charges            TEXT,
    cash_advance               TEXT,
    surcharge                  TEXT,
    previous_balance           TEXT,           -- from balance_breakdown
    payments                   TEXT,
    credits                    TEXT,
    purchases                  TEXT,
    other_debits_charges       TEXT,
    total_payment_due_check    TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_id      INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    date              TEXT,
    time              TEXT,
    details           TEXT,
    emi               INTEGER,                 -- 0/1
    amount            TEXT,
    amount_type       TEXT,                    -- Dr / Cr
    min_confidence    REAL,
    merchant_category TEXT,
    reference         TEXT,
    reward_points     TEXT,
    channel           TEXT,
    cashback          TEXT,
    cashback_type     TEXT,
    card_no           TEXT
);
CREATE INDEX IF NOT EXISTS ix_transactions_statement ON transactions(statement_id);

-- Free-form data (extras, reconciliation, validation, unknown fields) as flattened key/value rows.
CREATE TABLE IF NOT EXISTS additional_details (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_id  INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    category      TEXT NOT NULL,               -- extras | reconciliation | validation | summary | transaction
    key           TEXT NOT NULL,               -- dotted path, e.g. points_summary.total
    value         TEXT
);
CREATE INDEX IF NOT EXISTS ix_details_statement ON additional_details(statement_id);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection, creating the file, its folder and the schema if missing."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
