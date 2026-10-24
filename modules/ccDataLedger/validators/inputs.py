"""Input validation. Validators follow the `(ok, messages)` convention — they never raise."""

from pathlib import Path


def validate_import_inputs(merged: dict) -> tuple[bool, list[str]]:
    """Expect an uploaded ``files`` list of .json files."""
    uploads = merged.get("files") or []
    if not uploads:
        return False, ["'file' is required (uploaded .json, repeatable)."]
    if any(not getattr(u, "filename", "") or Path(u.filename).suffix.lower() != ".json" for u in uploads):
        return False, ["Uploaded files must be .json."]
    return True, []


def validate_update_body(body, allowed: set[str]) -> tuple[bool, list[str]]:
    """Body must be a non-empty JSON object with at least one updatable field."""
    if not isinstance(body, dict) or not body:
        return False, ["Request body must be a non-empty JSON object."]
    unknown = sorted(set(body) - allowed)
    if unknown:
        return False, [f"Unknown or read-only fields: {', '.join(unknown)}."]
    return True, []
