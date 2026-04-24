from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _normalize_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def normalize_task_id(task_id: str) -> str:
    normalized = task_id.strip()
    if not normalized:
        raise ValueError("task_id is required")
    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError("task_id must be task-scoped, not an absolute path")
    if len(candidate.parts) != 1 or candidate.parts[0] in {".", ".."}:
        raise ValueError("task_id must be a single task directory name under .codex/tasks/")
    return normalized


def verify_root(repo_root: Path, task_id: str) -> Path:
    return repo_root / ".codex" / "tasks" / normalize_task_id(task_id) / "verify"


def context_path(repo_root: Path, task_id: str) -> Path:
    return verify_root(repo_root, task_id) / "verify_context.json"


def review_path(repo_root: Path, task_id: str) -> Path:
    return verify_root(repo_root, task_id) / "review.md"


def load_context(repo_root: Path, task_id: str) -> dict[str, Any] | None:
    path = context_path(repo_root, task_id)
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("verify_context.json must be a JSON object")
    return payload


def _review_markdown(payload: dict[str, Any]) -> str:
    deliverables = payload.get("deliverables", [])
    checks = payload.get("required_checks", [])
    evidence = payload.get("evidence_paths", [])
    bullets = lambda items: "\n".join(f"- `{item}`" for item in items) if items else "- (pending)"
    return (
        "# Verifier Review Sidecar\n\n"
        "> non-canonical verifier sidecar. Do not flush this artifact into `.codex/memory/` by default.\n\n"
        f"- Task ID: `{payload['task_id']}`\n"
        f"- Task Summary: {payload['task_summary']}\n"
        f"- Sidecar Root: `{payload['sidecar_root']}`\n\n"
        "## Deliverables\n"
        f"{bullets(deliverables)}\n\n"
        "## Required Checks\n"
        f"{bullets(checks)}\n\n"
        "## Evidence Paths\n"
        f"{bullets(evidence)}\n\n"
        "## Review Notes\n"
        "- Outcome:\n"
        "- Blocking Findings:\n"
        "- Follow-up Checks:\n"
    )


def _build_payload(
    repo_root: Path,
    *,
    task_id: str,
    task_summary: str,
    deliverables: list[str],
    required_checks: list[str],
    evidence_paths: list[str],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_task_id = normalize_task_id(task_id)
    normalized_summary = task_summary.strip()
    if not normalized_summary and not existing:
        raise ValueError("task_summary is required when creating a verifier sidecar")
    sidecar_root = verify_root(repo_root, normalized_task_id)
    existing_payload = existing or {}
    created_at = existing_payload.get("created_at", _now_iso())
    return {
        "task_id": normalized_task_id,
        "task_summary": normalized_summary or existing_payload.get("task_summary", ""),
        "deliverables": _normalize_list(deliverables or existing_payload.get("deliverables", [])),
        "required_checks": _normalize_list(required_checks or existing_payload.get("required_checks", [])),
        "evidence_paths": _normalize_list(evidence_paths or existing_payload.get("evidence_paths", [])),
        "created_at": created_at,
        "updated_at": _now_iso(),
        "canonical": False,
        "sidecar_root": str(sidecar_root.relative_to(repo_root)),
    }


def upsert_sidecar(
    repo_root: Path,
    *,
    task_id: str,
    task_summary: str,
    deliverables: list[str],
    required_checks: list[str],
    evidence_paths: list[str],
) -> dict[str, Any]:
    existing = load_context(repo_root, task_id)
    payload = _build_payload(
        repo_root,
        task_id=task_id,
        task_summary=task_summary,
        deliverables=deliverables,
        required_checks=required_checks,
        evidence_paths=evidence_paths,
        existing=existing,
    )
    _atomic_write_json(context_path(repo_root, task_id), payload)
    review_file = review_path(repo_root, task_id)
    if not review_file.exists():
        _atomic_write_text(review_file, _review_markdown(payload))
    return read_sidecar(repo_root, task_id)


def read_sidecar(repo_root: Path, task_id: str) -> dict[str, Any]:
    payload = load_context(repo_root, task_id)
    if payload is None:
        raise FileNotFoundError(f"Verifier sidecar not found for task_id '{normalize_task_id(task_id)}'")
    verify_dir = verify_root(repo_root, task_id)
    context_file = context_path(repo_root, task_id)
    review_file = review_path(repo_root, task_id)
    return {
        "task_id": payload["task_id"],
        "task_summary": payload["task_summary"],
        "sidecar_root": str(verify_dir.relative_to(repo_root)),
        "verify_context_path": str(context_file.relative_to(repo_root)),
        "review_path": str(review_file.relative_to(repo_root)),
        "review_exists": review_file.exists(),
        "verify_context": payload,
    }
