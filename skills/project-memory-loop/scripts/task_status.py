from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_string_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    return [str(item) for item in values]


def _write_payload(status_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def read_status(status_path: str | Path) -> dict[str, Any]:
    path = Path(status_path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_status(
    status_path: str | Path,
    *,
    task_id: str,
    task_type: str,
    status: str,
    summary: str = "",
    artifact_paths: list[str] | tuple[str, ...] | None = None,
    errors: list[str] | tuple[str, ...] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = _now_iso()
    payload: dict[str, Any] = {
        "id": task_id,
        "type": task_type,
        "status": status,
        "started_at": timestamp,
        "updated_at": timestamp,
        "artifact_paths": _normalize_string_list(artifact_paths),
        "summary": summary,
        "errors": _normalize_string_list(errors),
    }
    if extra:
        payload.update(extra)
    return _write_payload(Path(status_path), payload)


def update_status(
    status_path: str | Path,
    *,
    status: str | None = None,
    summary: str | None = None,
    artifact_paths: list[str] | tuple[str, ...] | None = None,
    errors: list[str] | tuple[str, ...] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(status_path)
    payload = read_status(path)

    if status is not None:
        payload["status"] = status
    if summary is not None:
        payload["summary"] = summary
    if artifact_paths is not None:
        payload["artifact_paths"] = _normalize_string_list(artifact_paths)
    if errors is not None:
        payload["errors"] = _normalize_string_list(errors)

    payload["updated_at"] = _now_iso()
    if extra:
        payload.update(extra)

    return _write_payload(path, payload)
