"""HTTP layer: import JSON and update/view the four tables.

Thin Flask routes — validation → service delegate → JSON response.
"""

import json
import sqlite3

from flask import Blueprint, current_app, jsonify, request

from . import services as svc
from .services.db import columns
from .validators import validate_import_inputs, validate_update_body

ccDataLedger_bp = Blueprint("ccDataLedger_bp", __name__, url_prefix="/ccDataLedger")

READONLY = {"id", "statement_id", "imported_at"}


def _conn():
    return svc.connect(current_app.config["DB_PATH"])


def _err(msgs, code):
    return jsonify({"status": "error", "logs": msgs if isinstance(msgs, list) else [msgs]}), code


@ccDataLedger_bp.route("/import", methods=["POST"])
def import_json():
    """POST /ccDataLedger/import — multipart ``file`` (repeatable .json)."""
    data = {"files": request.files.getlist("file")}
    ok, messages = validate_import_inputs(data)
    if not ok:
        return _err(messages, 400)

    docs = [(u.filename, u.read()) for u in data["files"]]

    conn, logs, ids, failed = _conn(), [], [], 0
    try:
        for name, raw in docs:
            try:
                doc = json.loads(raw)
                if not isinstance(doc, dict):
                    raise ValueError("top-level JSON must be an object")
                res = svc.import_statement(conn, doc, fallback_name=name)
            except (ValueError, sqlite3.Error) as exc:
                logs.append(f"{name}: failed — {exc}")
                failed += 1
                continue
            logs += res.logs
            if res.status == "success":
                ids.append(res.statement_id)
            else:
                failed += 1
                logs.append(f"{name}: failed")
    finally:
        conn.close()
    status = "success" if not failed else ("partial" if ids else "error")
    return jsonify({"status": status, "logs": logs, "statement_ids": ids}), 200 if ids else 400


def _register_crud(name: str, fk: bool):
    """Register list/get/update (+ create/delete for child tables) for one table."""

    def list_view():
        conn = _conn()
        try:
            filters = {k: v for k, v in request.args.items() if k not in ("limit", "offset")}
            rows = svc.list_rows(conn, name, filters, int(request.args.get("limit", 100)),
                                 int(request.args.get("offset", 0)))
        finally:
            conn.close()
        return jsonify({"status": "success", "count": len(rows), "data": rows})

    def get_view(row_id):
        conn = _conn()
        try:
            row = svc.get_row(conn, name, row_id)
        finally:
            conn.close()
        return (jsonify({"status": "success", "data": row}) if row else _err(f"{name} {row_id} not found", 404))

    def update_view(row_id):
        conn = _conn()
        try:
            body = request.get_json(silent=True)
            ok, msgs = validate_update_body(body, set(columns(conn, name)) - READONLY)
            if not ok:
                return _err(msgs, 400)
            try:
                row = svc.update_row(conn, name, row_id, body)
            except sqlite3.Error as exc:
                return _err(str(exc), 400)
        finally:
            conn.close()
        return (jsonify({"status": "success", "data": row}) if row else _err(f"{name} {row_id} not found", 404))

    def delete_view(row_id):
        conn = _conn()
        try:
            deleted = svc.delete_row(conn, name, row_id)
        finally:
            conn.close()
        return jsonify({"status": "success"}) if deleted else _err(f"{name} {row_id} not found", 404)

    def create_view():
        conn = _conn()
        try:
            body = request.get_json(silent=True)
            ok, msgs = validate_update_body(body, set(columns(conn, name)) - {"id"})
            if not ok:
                return _err(msgs, 400)
            if "statement_id" not in body:
                return _err("'statement_id' is required.", 400)
            try:
                row = svc.create_row(conn, name, body)
            except sqlite3.Error as exc:  # FK / unique violations
                return _err(str(exc), 400)
        finally:
            conn.close()
        return jsonify({"status": "success", "data": row}), 201

    ep = f"{name}_"
    bp = ccDataLedger_bp
    bp.add_url_rule(f"/{name}", ep + "list", list_view, methods=["GET"])
    bp.add_url_rule(f"/{name}/<int:row_id>", ep + "get", get_view, methods=["GET"])
    bp.add_url_rule(f"/{name}/<int:row_id>", ep + "update", update_view, methods=["PUT", "PATCH"])
    if fk:
        bp.add_url_rule(f"/{name}", ep + "create", create_view, methods=["POST"])
        bp.add_url_rule(f"/{name}/<int:row_id>", ep + "delete", delete_view, methods=["DELETE"])


_register_crud("statements", fk=False)
_register_crud("summary", fk=True)
_register_crud("transactions", fk=True)
_register_crud("additional_details", fk=True)


@ccDataLedger_bp.route("/statements/<int:row_id>", methods=["DELETE"])
def delete_statement(row_id):
    """DELETE a statement; children are removed by ON DELETE CASCADE."""
    conn = _conn()
    try:
        deleted = svc.delete_row(conn, "statements", row_id)
    finally:
        conn.close()
    return jsonify({"status": "success"}) if deleted else _err(f"statements {row_id} not found", 404)
