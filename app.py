"""Bootstrap — loads blueprints from JSON, creates Flask app, starts server."""

import importlib.util
import json
import os
import sys

from flask import Flask


def create_app(db_path: str | None = None) -> Flask:
    """Build the Flask application from ``blueprints.json``.

    ``db_path`` overrides the SQLite file location (env ``LEDGER_DB_PATH``, default ``data/ledger.db``).
    """
    app = Flask(__name__)
    base = os.path.dirname(__file__)
    app.config["DB_PATH"] = db_path or os.environ.get("LEDGER_DB_PATH", os.path.join(base, "data", "ledger.db"))

    with open(os.path.join(base, "blueprints.json"), "r") as f:
        config = json.load(f)

    for entry in config.get("blueprints", []):
        abs_path = os.path.join(base, entry["path"], "__init__.py")
        spec = importlib.util.spec_from_file_location(entry["name"], abs_path,
                                                      submodule_search_locations=[os.path.dirname(abs_path)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[entry["name"]] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        app.register_blueprint(getattr(mod, entry["name"]), url_prefix=entry["url_prefix"])

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=os.environ.get("LEDGER_HOST", "0.0.0.0"), port=int(os.environ.get("LEDGER_PORT", 5008)))
