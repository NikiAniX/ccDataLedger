# ccDataLedger — context for AI assistants

Flask + SQLite service that imports credit-card statement JSON (output of the sibling project `../ccDataExtractor`, sample files in `../target/ccDataExtractor/output/`) into 4 tables and exposes view/update endpoints. Full user docs: `README.md` (schema, mapping, endpoints). Read it before changing behavior.

```bash
python app.py                      # dev server :5008 (env LEDGER_HOST, LEDGER_PORT, LEDGER_DB_PATH)
.venv/bin/python -m pytest tests/  # 6 tests, temp DB per test
```

## Architecture

`app.py` (factory `create_app(db_path=None)`, sets `app.config["DB_PATH"]`) → `blueprints.json` → `modules/ccDataLedger/`:
`routes.py` → `validators/inputs.py` → `services/{import_service,crud_service,db}.py`.

## Rules / conventions (mirrors ccDataExtractor)

- **No hardcoded blueprint imports.** Blueprints are declared in `blueprints.json` and loaded with `importlib`; the blueprint variable name must equal the manifest `name` (`ccDataLedger_bp`).
- **Validators** return `(ok, messages)` and never raise. **Services** have no Flask imports. **Routes** stay thin: validate → call service → JSON.
- **Response shape:** `{"status": "success"|"error"|"partial", "logs": [...]}` for errors/import, `{"status": "success", "data": ...}` for reads.
- **DB must persist.** Never drop tables, delete `data/ledger.db`, or use in-memory SQLite outside tests. Tests pass a temp path via `create_app(db_path)`.
- Open a connection per request (`_conn()` in `routes.py` → `db.connect()`), close in `finally`. `connect()` also runs the idempotent `SCHEMA`, sets `foreign_keys=ON` (per connection — required for cascades) and WAL mode.
- **SQL safety:** column and table names in dynamic SQL (`crud_service`, `import_service`) come only from `PRAGMA table_info` whitelists or hardcoded route names, never directly from request data. Keep it that way; values are always bound parameters.
- Values stay as **text** exactly as in the JSON (formats differ per bank: `"2,820.00"`, `"4,829.00 DR"`, `"13 Oct, 2026"`). Don't parse or normalize without discussing.

## Data model (summary)

`statements` (PK, `source_file` UNIQUE) ← `summary` (1:1, `statement_id` UNIQUE) · `transactions` (1:N) · `additional_details` (1:N key/value, flattened dotted keys). All FKs `ON DELETE CASCADE`.

Import (`import_statement`) runs in one transaction, keyed by `source_file` (falls back to the uploaded filename): an existing statement is deleted and re-inserted, so ids change. `summary.balance_breakdown` is flattened into the summary row. Any key without a column is written to `additional_details` instead of being lost; `extras`, `reconciliation` and `validation` always go there.

## API spec

`swagger.json` must stay in sync with `routes.py` (changed fields/responses/routes). `test_swagger_covers_all_routes` checks that every method+path is documented, but not schema details. Column schemas were generated from `SCHEMA`; when adding a column, update the relevant schemas in the file.

## Gotchas

- Adding a column to `SCHEMA` does not migrate an existing DB file (`CREATE TABLE IF NOT EXISTS`); an `ALTER TABLE` or a fresh dev DB is needed. Update the README table and mapping too.
- Update routes accept only existing columns minus `id`, `statement_id`, `imported_at` (`READONLY` is defined in both `routes.py` and `crud_service.py`). Create routes require `statement_id`; FK/UNIQUE violations surface as `sqlite3.Error` → 400.
- `list_rows` silently ignores filter params that are not columns, and `limit`/`offset` are cast with `int()` (non-numeric values currently cause a 500).
- `bool` values in JSON (`emi`) are stored as 0/1 in `transactions`, as `"true"/"false"` in `additional_details`.
- The test suite skips/depends on sample files at `../target/ccDataExtractor/output`; most tests would fail without them (`test_import_dir_and_view` skips, others assume data).

## Not done yet

auth, migrations tooling, typed numeric/date columns, bulk-update endpoints, git commits (repo was still empty when this was written).
