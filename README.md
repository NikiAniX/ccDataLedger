# ccDataLedger

Flask API that loads the statement JSON files produced by [ccDataExtractor](../ccDataExtractor) into a **file-based SQLite database** and lets you view and update the data over HTTP.

- Input: JSON files such as those in `../target/ccDataExtractor/output/`.
- Storage: SQLite file `data/ledger.db`. It is created on first use and **never deleted or reset on shutdown**, so data persists across restarts.
- No network access, no external services; only Flask is needed at runtime (SQLite is in the Python standard library).

## Project structure

```
ccDataLedger/
├── app.py                         # Bootstrap: loads blueprints.json, creates Flask app, sets DB_PATH
├── blueprints.json                # Feature manifest (blueprint path / name / url_prefix)
├── requirements.txt               # flask, pytest
├── swagger.json                   # OpenAPI 3 spec for all routes
├── CLAUDE.md                      # Context for AI assistants (read this first)
├── data/                           # ledger.db lives here (git-ignored, auto-created)
├── modules/ccDataLedger/
│   ├── __init__.py                # re-exports ccDataLedger_bp
│   ├── routes.py                  # HTTP layer: /import and CRUD routes
│   ├── validators/inputs.py       # validate_import_inputs, validate_update_body -> (ok, messages)
│   └── services/                  # framework-free logic
│       ├── db.py                  # SCHEMA, connect(), columns()
│       ├── import_service.py      # import_statement(): JSON -> 4 tables
│       └── crud_service.py        # list/get/create/update/delete rows
└── tests/                         # conftest.py (temp DB per test), test_ccDataLedger.py
```

## Setup and run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                      # http://0.0.0.0:5008
.venv/bin/python -m pytest tests/  # uses a temp DB; sample JSON from ../target/ccDataExtractor/output
```

| Env var | Default | Meaning |
|---|---|---|
| `LEDGER_DB_PATH` | `data/ledger.db` | SQLite file location (parent folder is created) |
| `LEDGER_HOST` | `0.0.0.0` | bind address |
| `LEDGER_PORT` | `5008` | port |

`swagger.json` is the OpenAPI 3 spec (load it in Swagger UI/Editor or Postman). A test fails if a route is missing from it.

## Database

Foreign keys are enforced (`PRAGMA foreign_keys=ON`); deleting a statement cascades to its children. Amounts and dates are stored as the **text** found in the JSON (e.g. `"56,317.00"`, `"23/08/2026"`) because the source formats vary per bank.

| Table | Key | Rows per statement | Content |
|---|---|---|---|
| `statements` | PK `id`; `source_file` UNIQUE | 1 | `source_files` (JSON array text), `cardholder`, `imported_at` |
| `summary` | FK `statement_id` (UNIQUE) | 1 | `total_payment_due`, `minimum_payment_due`, `statement_period`, `payment_due_date`, `statement_generation_date`, `credit_card_number`, `credit_limit`, `available_credit_limit`, `available_cash_limit`, `previous_statement_dues`, `payments_credits`, `purchases_debit`, `finance_charges`, `cash_advance`, `surcharge`, plus the flattened `balance_breakdown` (`previous_balance`, `payments`, `credits`, `purchases`, `other_debits_charges`, `total_payment_due_check`) |
| `transactions` | FK `statement_id` | N | `date`, `time`, `details`, `emi` (0/1), `amount`, `amount_type` (Dr/Cr), `min_confidence`, `merchant_category`, `reference`, `reward_points`, `channel`, `cashback`, `cashback_type`, `card_no` |
| `additional_details` | FK `statement_id` | N | `category`, `key`, `value`. Categories: `extras`, `reconciliation`, `validation`, `summary` and `transaction` (fields with no column). Nested data is flattened to dotted keys, e.g. `points_summary.programs.0.points` |

### JSON → table mapping

| JSON key | Goes to |
|---|---|
| `source_file`, `source_files`, `cardholder` | `statements` |
| `summary.*`, `summary.balance_breakdown.*` | `summary` columns; unknown keys → `additional_details` (`summary`) |
| `transactions[]` | `transactions`; unknown keys → `additional_details` (`transaction`, key `<index>.<field>`) |
| `extras`, `reconciliation`, `validation` | `additional_details` |

Null values are not stored in `additional_details`. Re-importing a file with the same `source_file` **replaces** the old statement and its children (new `id`s).

## API (prefix `/ccDataLedger`)

Responses are JSON with `status` (`success` / `error` / `partial`) and `logs` (errors) or `data`.

### Import
`POST /ccDataLedger/import`, multipart/form-data:

| Field | Description |
|---|---|
| `file` | uploaded `.json`, repeatable |
| `path` | server-side JSON file or directory (all `*.json`; no `..`) |

At least one is required. Returns `statement_ids` and per-file `logs`. A bad file doesn't stop the others (`partial`).

### View and update

| Method | Path | Notes |
|---|---|---|
| GET | `/statements`, `/summary`, `/transactions`, `/additional_details` | filter by any column (`?statement_id=1&amount_type=Dr`), `limit` (100), `offset` |
| GET | `/<table>/<id>` | 404 if missing |
| PUT / PATCH | `/<table>/<id>` | partial update from a JSON object; `id`, `statement_id`, `imported_at` are read-only; unknown fields → 400 |
| DELETE | `/statements/<id>` | cascades to children |
| POST | `/summary`, `/transactions`, `/additional_details` | create a child row; `statement_id` required and must exist (summary: one per statement) |
| DELETE | `/summary/<id>`, `/transactions/<id>`, `/additional_details/<id>` | remove a child row |

```bash
curl -X POST -F path=/Users/ani/projectX/ecosystem/target/ccDataExtractor/output http://localhost:5008/ccDataLedger/import
curl -X POST -F file=@statement.json http://localhost:5008/ccDataLedger/import
curl 'http://localhost:5008/ccDataLedger/statements'
curl 'http://localhost:5008/ccDataLedger/transactions?statement_id=1&amount_type=Dr'
curl -X PUT -H 'Content-Type: application/json' -d '{"merchant_category":"FOOD"}' http://localhost:5008/ccDataLedger/transactions/1
```

Inspect the DB directly: `sqlite3 data/ledger.db ".tables"`.

## Extending

- **New JSON field:** it is saved to `additional_details` automatically. To get a real column, add it to `SCHEMA` in `services/db.py`. `CREATE TABLE IF NOT EXISTS` does not alter an existing DB, so run `ALTER TABLE ... ADD COLUMN` on `data/ledger.db` too (or delete the dev DB).
- **New feature module:** add a folder under `modules/` and an entry in `blueprints.json`.

## Known limitations

- No authentication; no schema migration tooling; no pagination metadata beyond `limit`/`offset`.
- Values are strings, so numeric/date sorting and aggregation need casting or a future typed-column migration.
