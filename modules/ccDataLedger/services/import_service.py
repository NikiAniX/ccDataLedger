"""Read statement JSON and save it into the four tables."""

import json
from dataclasses import dataclass, field

from .db import columns


@dataclass
class ImportResult:
    status: str = "success"
    logs: list[str] = field(default_factory=list)
    statement_id: int | None = None


def _flatten(value, prefix: str = ""):
    """Yield ``(dotted_key, str_value)`` leaves of nested dict/list data."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _flatten(v, f"{prefix}.{i}" if prefix else str(i))
    elif value is not None:
        yield prefix, str(value).lower() if isinstance(value, bool) else str(value)


def _scalar(v):
    return int(v) if isinstance(v, bool) else v


def import_statement(conn, data: dict, fallback_name: str = "") -> ImportResult:
    """Insert (or replace, keyed by ``source_file``) one statement JSON document."""
    result = ImportResult()
    source_file = data.get("source_file") or fallback_name
    if not source_file:
        return ImportResult("error", ["Missing 'source_file' in JSON."])

    summary_cols = set(columns(conn, "summary")) - {"id", "statement_id"}
    txn_cols = set(columns(conn, "transactions")) - {"id", "statement_id"}

    with conn:  # one transaction: all-or-nothing
        existing = conn.execute("SELECT id FROM statements WHERE source_file=?", (source_file,)).fetchone()
        if existing:
            conn.execute("DELETE FROM statements WHERE id=?", (existing["id"],))  # cascades to children
            result.logs.append(f"Replaced existing statement for {source_file}.")
        sid = conn.execute(
            "INSERT INTO statements (source_file, source_files, cardholder) VALUES (?,?,?)",
            (source_file, json.dumps(data.get("source_files") or []), data.get("cardholder")),
        ).lastrowid

        details: list[tuple[str, str, str]] = []

        # summary: balance_breakdown is flattened into the same row; unknown keys go to additional_details
        raw = dict(data.get("summary") or {})
        raw.update(raw.pop("balance_breakdown", None) or {})
        row = {k: v for k, v in raw.items() if k in summary_cols}
        details += [("summary", k, v) for k, v in _flatten({k: v for k, v in raw.items() if k not in summary_cols})]
        conn.execute(
            f"INSERT INTO summary (statement_id{''.join(',' + k for k in row)}) VALUES (?{',?' * len(row)})",
            (sid, *row.values()),
        )

        txns = data.get("transactions") or []
        for n, t in enumerate(txns):
            row = {k: _scalar(v) for k, v in t.items() if k in txn_cols}
            details += [("transaction", f"{n}.{k}", v) for k, v in _flatten({k: v for k, v in t.items() if k not in txn_cols})]
            conn.execute(
                f"INSERT INTO transactions (statement_id{''.join(',' + k for k in row)}) VALUES (?{',?' * len(row)})",
                (sid, *row.values()),
            )

        for category in ("extras", "reconciliation", "validation"):
            details += [(category, k, v) for k, v in _flatten(data.get(category) or {})]
        conn.executemany(
            "INSERT INTO additional_details (statement_id, category, key, value) VALUES (?,?,?,?)",
            [(sid, c, k, v) for c, k, v in details],
        )

    result.statement_id = sid
    result.logs.append(f"Imported {source_file}: {len(txns)} transactions, {len(details)} additional details.")
    return result
