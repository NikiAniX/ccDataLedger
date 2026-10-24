import pytest

from app import create_app


def _import(client, samples_dir):
    files = [(f.open("rb"), f.name) for f in sorted(samples_dir.glob("*.json"))]
    return client.post("/ccDataLedger/import", data={"file": files}, content_type="multipart/form-data")


def test_import_dir_and_view(client, samples_dir):
    if not samples_dir.exists():
        pytest.skip("sample outputs missing")
    r = _import(client, samples_dir)
    assert r.status_code == 200 and r.json["status"] == "success"
    n = len(r.json["statement_ids"])
    assert client.get("/ccDataLedger/statements").json["count"] == n
    sid = r.json["statement_ids"][0]
    assert client.get(f"/ccDataLedger/summary?statement_id={sid}").json["count"] == 1
    assert client.get(f"/ccDataLedger/transactions?statement_id={sid}").json["count"] > 0
    assert client.get(f"/ccDataLedger/additional_details?statement_id={sid}").json["count"] > 0


def test_reimport_is_idempotent(client, samples_dir):
    _import(client, samples_dir)
    first = client.get("/ccDataLedger/statements").json["count"]
    _import(client, samples_dir)
    assert client.get("/ccDataLedger/statements").json["count"] == first


def test_update_and_validation(client, samples_dir):
    _import(client, samples_dir)
    sid = client.get("/ccDataLedger/statements").json["data"][0]["id"]
    r = client.put(f"/ccDataLedger/statements/{sid}", json={"cardholder": "X"})
    assert r.json["data"]["cardholder"] == "X"
    assert client.put(f"/ccDataLedger/statements/{sid}", json={"id": 9}).status_code == 400
    tid = client.get(f"/ccDataLedger/transactions?statement_id={sid}").json["data"][0]["id"]
    assert client.patch(f"/ccDataLedger/transactions/{tid}", json={"amount": "1.00"}).json["data"]["amount"] == "1.00"
    assert client.get("/ccDataLedger/summary/99999").status_code == 404


def test_fk_enforced_and_cascade(client, samples_dir):
    _import(client, samples_dir)
    assert client.post("/ccDataLedger/transactions", json={"statement_id": 99999}).status_code == 400
    sid = client.get("/ccDataLedger/statements").json["data"][0]["id"]
    client.delete(f"/ccDataLedger/statements/{sid}")
    assert client.get(f"/ccDataLedger/transactions?statement_id={sid}").json["count"] == 0


def test_persists_across_restart(db_path, samples_dir):
    _import(create_app(db_path).test_client(), samples_dir)
    assert create_app(db_path).test_client().get("/ccDataLedger/statements").json["count"] > 0


def test_import_validation(client):
    assert client.post("/ccDataLedger/import", data={}).status_code == 400


def test_swagger_covers_all_routes(db_path):
    import json
    from pathlib import Path

    spec = json.loads((Path(__file__).resolve().parent.parent / "swagger.json").read_text())
    documented = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    actual = set()
    for rule in create_app(db_path).url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        path = rule.rule.replace("<int:row_id>", "{row_id}")
        actual |= {(m, path) for m in rule.methods - {"HEAD", "OPTIONS"}}
    assert actual == documented
