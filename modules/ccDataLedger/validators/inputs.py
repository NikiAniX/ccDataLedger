"""Input validation. Validators follow the `(ok, messages)` convention — they never raise."""

from pathlib import Path


def validate_import_inputs(merged: dict) -> tuple[bool, list[str]]:
    """Expect an uploaded ``files`` list (.json) and/or a server-side ``path`` (file or directory)."""
    errors: list[str] = []
    uploads = merged.get("files") or []
    path = str(merged.get("path", "")).strip()

    if not uploads and not path:
        errors.append("Provide 'file' (uploaded .json, repeatable) or 'path' (JSON file or directory).")
    if any(not getattr(u, "filename", "") or Path(u.filename).suffix.lower() != ".json" for u in uploads):
        errors.append("Uploaded files must be .json.")
    if path:
        p = Path(path)
        if ".." in p.parts:
            errors.append("'path' must not contain '..'.")
        elif not p.exists():
            errors.append(f"'path' does not exist: {path}")
    return (not errors, errors)


def validate_update_body(body, allowed: set[str]) -> tuple[bool, list[str]]:
    """Body must be a non-empty JSON object with at least one updatable field."""
    if not isinstance(body, dict) or not body:
        return False, ["Request body must be a non-empty JSON object."]
    unknown = sorted(set(body) - allowed)
    if unknown:
        return False, [f"Unknown or read-only fields: {', '.join(unknown)}."]
    return True, []
