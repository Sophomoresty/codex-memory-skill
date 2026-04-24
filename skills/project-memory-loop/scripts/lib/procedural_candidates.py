from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


CANDIDATES_PATH = Path(".codex/evolution/procedural-candidates.json")
ALLOWED_TYPES = {"skill", "sop", "script"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _normalize_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _task_fingerprint(task_summary: str) -> str:
    return hashlib.sha256(task_summary.strip().encode("utf-8")).hexdigest()[:16]


def candidates_path(repo_root: Path) -> Path:
    return repo_root / CANDIDATES_PATH


def load_store(repo_root: Path) -> dict[str, Any]:
    path = candidates_path(repo_root)
    if not path.exists():
        return {"version": 1, "candidates": []}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {"version": 1, "candidates": []}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("procedural candidate store must be a mapping")
    payload.setdefault("version", 1)
    payload.setdefault("candidates", [])
    return payload


def create_candidate(
    repo_root: Path,
    *,
    task_summary: str,
    candidate_type: str,
    title: str,
    summary: str,
    source_paths: list[str],
    related_assets: list[str],
    event_ids: list[str],
    capsule_id: str | None,
    validation_mode: str | None,
    tests_passed: bool | None,
    user_confirmed: bool | None,
) -> dict[str, Any]:
    candidate_type = candidate_type.strip().lower()
    if candidate_type not in ALLOWED_TYPES:
        raise ValueError(f"candidate type must be one of {sorted(ALLOWED_TYPES)}")
    payload = load_store(repo_root)
    candidate = {
        "id": "cand_" + uuid4().hex[:10],
        "task_summary": task_summary.strip(),
        "task_fingerprint": _task_fingerprint(task_summary),
        "candidate_type": candidate_type,
        "title": title.strip(),
        "summary": summary.strip(),
        "source_paths": _normalize_list(source_paths),
        "related_assets": _normalize_list(related_assets),
        "event_ids": _normalize_list(event_ids),
        "capsule_id": capsule_id.strip() if capsule_id else None,
        "status": "candidate",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "evidence": {
            "validation_mode": validation_mode.strip() if validation_mode else None,
            "tests_passed": tests_passed,
            "user_confirmed": user_confirmed,
        },
    }
    payload.setdefault("candidates", []).append(candidate)
    _atomic_write(candidates_path(repo_root), payload)
    return candidate
