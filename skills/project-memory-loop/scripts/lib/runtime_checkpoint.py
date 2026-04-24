from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import semantic_store as ss


MAX_RETRIEVAL_TRACES_PER_TASK = 24


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _normalize_query(value: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def checkpoint_fingerprint(task: str) -> str:
    return hashlib.sha256(task.strip().encode("utf-8")).hexdigest()[:16]


def promotion_fingerprint(task: str, title: str, summary: str) -> str:
    seed = "\n".join([task.strip(), title.strip(), summary.strip(), _now_iso()])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def checkpoint_path(repo_root: Path) -> Path:
    return ss.store_path(repo_root)


def load_store(repo_root: Path) -> dict[str, Any]:
    return ss.read_checkpoint_store(repo_root)


def latest_checkpoint(repo_root: Path) -> dict[str, Any]:
    record = ss.latest_checkpoint_record(repo_root)
    return record or {}


def read_checkpoint(repo_root: Path, task: str) -> dict[str, Any]:
    fingerprint = checkpoint_fingerprint(task)
    record = ss.read_checkpoint_record(repo_root, fingerprint)
    if record is None:
        return {
            "exists": False,
            "task": task,
            "task_fingerprint": fingerprint,
            "key_facts": [],
            "related_assets": [],
            "task_assets": [],
            "reused_assets": [],
            "current_invariant": [],
            "verified_steps": [],
            "retrieval_traces": [],
            "closeout_ledger": {
                "coverage_mode": "",
                "runbook_paths": [],
                "benchmark_queries": [],
                "script_paths": [],
                "coverage_evidence": [],
            },
        }
    return {"exists": True, **record}


def read_promotions(repo_root: Path, task: str) -> dict[str, Any]:
    fingerprint = checkpoint_fingerprint(task)
    records = ss.read_promotion_records(repo_root, task_fingerprint=fingerprint)
    return {
        "task": task,
        "task_fingerprint": fingerprint,
        "count": len(records),
        "promotions": records,
    }


def read_promotion(repo_root: Path, *, task: str, promotion_id: str) -> dict[str, Any]:
    record = ss.read_promotion_record(repo_root, promotion_id)
    fingerprint = checkpoint_fingerprint(task)
    if record is None or str(record.get("task_fingerprint", "")).strip() != fingerprint:
        return {
            "exists": False,
            "task": task,
            "task_fingerprint": fingerprint,
            "promotion_id": promotion_id.strip(),
        }
    return {"exists": True, **record}


def _upsert_retrieval_trace(
    traces: list[dict[str, Any]],
    *,
    route_query: str,
    route_event_id: str,
    surfaced_hits_hash: str,
    surfaced_hits: list[str],
    selected_hit: str,
    adopted_hit: str,
    observed_actions: list[str],
    evidence_paths: list[str],
    corrections: list[dict[str, str]],
) -> list[dict[str, Any]]:
    trace = {
        "route_query": route_query,
        "route_event_id": route_event_id.strip(),
        "surfaced_hits_hash": surfaced_hits_hash.strip(),
        "surfaced_hits": _normalize_list(surfaced_hits),
        "selected_hit": selected_hit,
        "adopted_hit": adopted_hit,
        "adoption_state": "adopted" if adopted_hit else ("selected" if selected_hit else "surfaced"),
        "observed_actions": _normalize_list(observed_actions),
        "evidence_paths": _normalize_list(evidence_paths),
        "corrections": list(corrections),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    updated = list(traces)
    updated.append(trace)
    if len(updated) > MAX_RETRIEVAL_TRACES_PER_TASK:
        updated = updated[-MAX_RETRIEVAL_TRACES_PER_TASK:]
    return updated


def upsert_checkpoint(
    repo_root: Path,
    *,
    task: str,
    key_facts: list[str],
    task_assets: list[str],
    reused_assets: list[str],
    current_invariant: list[str],
    verified_steps: list[str],
    route_query: str = "",
    route_event_id: str = "",
    surfaced_hits_hash: str = "",
    surfaced_hits: list[str] | None = None,
    selected_hit: str = "",
    adopted_hit: str = "",
    observed_actions: list[str] | None = None,
    evidence_paths: list[str] | None = None,
    coverage_mode: str = "",
    runbook_paths: list[str] | None = None,
    benchmark_queries: list[str] | None = None,
    script_paths: list[str] | None = None,
    coverage_evidence: list[str] | None = None,
    corrections: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    fingerprint = checkpoint_fingerprint(task)
    record = ss.read_checkpoint_record(repo_root, fingerprint) or {
        "task": task,
        "task_fingerprint": fingerprint,
        "key_facts": [],
        "related_assets": [],
        "task_assets": [],
        "reused_assets": [],
        "current_invariant": [],
        "verified_steps": [],
        "retrieval_traces": [],
        "closeout_ledger": {
            "coverage_mode": "",
            "runbook_paths": [],
            "benchmark_queries": [],
            "script_paths": [],
            "coverage_evidence": [],
        },
        "created_at": _now_iso(),
    }
    record["task"] = task
    record["task_fingerprint"] = fingerprint
    record["key_facts"] = _normalize_list(record.get("key_facts", []) + key_facts)
    record["task_assets"] = _normalize_list(record.get("task_assets", []) + task_assets)
    record["related_assets"] = list(record["task_assets"])
    record["reused_assets"] = _normalize_list(record.get("reused_assets", []) + reused_assets)
    record["current_invariant"] = _normalize_list(record.get("current_invariant", []) + current_invariant)
    record["verified_steps"] = _normalize_list(record.get("verified_steps", []) + verified_steps)
    if route_query.strip():
        record["retrieval_traces"] = _upsert_retrieval_trace(
            list(record.get("retrieval_traces", [])),
            route_query=route_query.strip(),
            route_event_id=route_event_id.strip(),
            surfaced_hits_hash=surfaced_hits_hash.strip(),
            surfaced_hits=list(surfaced_hits or []),
            selected_hit=selected_hit.strip(),
            adopted_hit=adopted_hit.strip(),
            observed_actions=list(observed_actions or []),
            evidence_paths=list(evidence_paths or []),
            corrections=list(corrections or []),
        )
    else:
        record.setdefault("retrieval_traces", [])
    ledger = dict(record.get("closeout_ledger", {}))
    ledger["coverage_mode"] = coverage_mode.strip() or str(ledger.get("coverage_mode", "")).strip()
    ledger["runbook_paths"] = _normalize_list(list(ledger.get("runbook_paths", [])) + list(runbook_paths or []))
    ledger["benchmark_queries"] = _normalize_list(list(ledger.get("benchmark_queries", [])) + list(benchmark_queries or []))
    ledger["script_paths"] = _normalize_list(list(ledger.get("script_paths", [])) + list(script_paths or []))
    ledger["coverage_evidence"] = _normalize_list(list(ledger.get("coverage_evidence", [])) + list(coverage_evidence or []))
    record["closeout_ledger"] = ledger
    record["updated_at"] = _now_iso()
    ss.upsert_checkpoint_record(repo_root, fingerprint=fingerprint, task=task, record=record)
    return {"exists": True, **record}


def create_promotion(
    repo_root: Path,
    *,
    task: str,
    title: str,
    summary: str,
    doc_type: str,
    evidence_paths: list[str],
) -> dict[str, Any]:
    checkpoint = read_checkpoint(repo_root, task)
    if not checkpoint.get("exists"):
        raise ValueError("existing working checkpoint is required before promotion")
    normalized_evidence = _normalize_list(evidence_paths)
    if not normalized_evidence:
        raise ValueError("evidence_paths are required before promotion")
    now = _now_iso()
    promotion_id = promotion_fingerprint(task, title, summary)
    record = {
        "promotion_id": promotion_id,
        "task": task,
        "task_fingerprint": checkpoint["task_fingerprint"],
        "title": title.strip(),
        "summary": summary.strip(),
        "doc_type": doc_type.strip(),
        "evidence_paths": normalized_evidence,
        "promotion_state": "proposed",
        "source_checkpoint": {
            "task": checkpoint["task"],
            "task_fingerprint": checkpoint["task_fingerprint"],
            "key_facts": list(checkpoint.get("key_facts", [])),
            "current_invariant": list(checkpoint.get("current_invariant", [])),
            "verified_steps": list(checkpoint.get("verified_steps", [])),
            "task_assets": list(checkpoint.get("task_assets", [])),
            "reused_assets": list(checkpoint.get("reused_assets", [])),
            "retrieval_traces": list(checkpoint.get("retrieval_traces", [])),
            "closeout_ledger": dict(checkpoint.get("closeout_ledger", {})),
            "updated_at": str(checkpoint.get("updated_at", "")).strip(),
        },
        "created_at": now,
        "updated_at": now,
    }
    ss.upsert_promotion_record(
        repo_root,
        promotion_id=promotion_id,
        task_fingerprint=checkpoint["task_fingerprint"],
        task=task,
        record=record,
    )
    return record
