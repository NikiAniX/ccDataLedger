"""Generic list/get/update/create/delete over the four tables. No Flask imports."""

from .db import columns

READONLY = {"id", "statement_id", "imported_at"}


def _cols(conn, table):
    return columns(conn, table)


def list_rows(conn, table: str, filters: dict, limit: int = 100, offset: int = 0) -> list[dict]:
    allowed = set(_cols(conn, table))
    keys = [k for k in filters if k in allowed]
    where = " AND ".join(f"{k}=?" for k in keys)
    sql = f"SELECT * FROM {table}" + (f" WHERE {where}" if where else "") + " ORDER BY id LIMIT ? OFFSET ?"
    return [dict(r) for r in conn.execute(sql, (*[filters[k] for k in keys], limit, offset))]


def get_row(conn, table: str, row_id: int) -> dict | None:
    r = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    return dict(r) if r else None


def update_row(conn, table: str, row_id: int, changes: dict) -> dict | None:
    fields = {k: v for k, v in changes.items() if k in set(_cols(conn, table)) - READONLY}
    if fields:
        with conn:
            conn.execute(f"UPDATE {table} SET {','.join(f'{k}=?' for k in fields)} WHERE id=?",
                         (*fields.values(), row_id))
    return get_row(conn, table, row_id)


def create_row(conn, table: str, values: dict) -> dict:
    fields = {k: v for k, v in values.items() if k in set(_cols(conn, table)) - {"id", "imported_at"}}
    with conn:
        rid = conn.execute(
            f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join('?' * len(fields))})",
            tuple(fields.values()),
        ).lastrowid
    return get_row(conn, table, rid)


def delete_row(conn, table: str, row_id: int) -> bool:
    with conn:
        return conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,)).rowcount > 0
