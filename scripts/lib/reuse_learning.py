from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import query_intel as qi


LEARNING_PATH = Path(".codex/evolution/reuse-learning.json")
ROUTE_EVENTS_PATH = Path(".codex/evolution/route-events.jsonl")
MAX_EVENTS = 2000
EXACT_QUERY_BOOST = 1.4
RELATED_QUERY_BOOST = 0.8
MIN_OVERLAP_RATIO = 0.35
_LEARNING_PAYLOAD_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}
_NORMALIZED_TARGET_CACHE: dict[tuple[str, str], str] = {}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(repo_root: Path) -> Path:
    return repo_root / LEARNING_PATH


def _events_path(repo_root: Path) -> Path:
    return repo_root / ROUTE_EVENTS_PATH


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    if not isinstance(payload, dict):
        return default
    return payload


def _read_learning_payload(repo_root: Path) -> dict[str, Any]:
    path = _path(repo_root)
    if not path.exists():
        return {"version": 1, "records": []}
    try:
        stat = path.stat()
    except OSError:
        return {"version": 1, "records": []}
    key = str(path)
    cached = _LEARNING_PAYLOAD_CACHE.get(key)
    signature = (stat.st_mtime_ns, stat.st_size)
    if cached and cached[0] == signature[0] and cached[1] == signature[1]:
        return cached[2]
    payload = _read_json(path, default={"version": 1, "records": []})
    _LEARNING_PAYLOAD_CACHE[key] = (signature[0], signature[1], payload)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        stat = path.stat()
        _LEARNING_PAYLOAD_CACHE[str(path)] = (stat.st_mtime_ns, stat.st_size, payload)
    except OSError:
        _LEARNING_PAYLOAD_CACHE.pop(str(path), None)


def normalize_query(query: str) -> str:
    return qi.search_normalize(query)


def query_terms(query: str) -> list[str]:
    return qi.flatten_query_terms(query, limit=12)


def _record_terms(record: dict[str, Any]) -> list[str]:
    terms = [qi.search_normalize(term) for term in record.get("query_terms", []) if qi.search_normalize(term)]
    if terms:
        return list(dict.fromkeys(terms))[:12]
    return query_terms(str(record.get("query", "")))


def normalize_target_path(repo_root: Path, raw_path: str) -> str:
    cache_key = (str(repo_root), raw_path)
    cached = _NORMALIZED_TARGET_CACHE.get(cache_key)
    if cached is not None:
        return cached
    candidate = Path(raw_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if resolved.is_relative_to(repo_root / ".codex" / "memory"):
            normalized = "memory/" + resolved.relative_to(repo_root / ".codex" / "memory").as_posix()
            _NORMALIZED_TARGET_CACHE[cache_key] = normalized
            return normalized
        if resolved.is_relative_to(repo_root):
            normalized = resolved.relative_to(repo_root).as_posix()
            _NORMALIZED_TARGET_CACHE[cache_key] = normalized
            return normalized
        normalized = raw_path.strip()
        _NORMALIZED_TARGET_CACHE[cache_key] = normalized
        return normalized
    cleaned = raw_path.strip()
    if cleaned.startswith(".codex/memory/"):
        normalized = "memory/" + cleaned.removeprefix(".codex/memory/")
        _NORMALIZED_TARGET_CACHE[cache_key] = normalized
        return normalized
    if cleaned.startswith("runbooks/") or cleaned.startswith("decisions/") or cleaned.startswith("patterns/") or cleaned.startswith("postmortems/"):
        normalized = "memory/" + cleaned
        _NORMALIZED_TARGET_CACHE[cache_key] = normalized
        return normalized
    _NORMALIZED_TARGET_CACHE[cache_key] = cleaned
    return cleaned


def surfaced_hits_hash(items: list[str]) -> str:
    normalized = [str(item).strip() for item in items if str(item).strip()]
    raw = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def event_hits(event: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    for item in event.get("hits", []):
        if isinstance(item, dict):
            path = str(item.get("path", "")).strip()
            if path:
                hits.append(path)
    return hits


def record_route_event(repo_root: Path, *, query: str, hits: list[dict[str, Any]], fallback_context: bool) -> dict[str, str]:
    path = _events_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event_id = "evt_" + uuid4().hex[:12]
    hits_hash = surfaced_hits_hash(
        [str(hit.get("path", "")).strip() for hit in hits if isinstance(hit, dict)]
    )
    event = {
        "event_id": event_id,
        "recorded_at": _utcnow(),
        "query": query,
        "normalized_query": normalize_query(query),
        "fallback_context": fallback_context,
        "hits_hash": hits_hash,
        "hits": hits,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {"event_id": event_id, "hits_hash": hits_hash}
    if len(lines) > MAX_EVENTS:
        path.write_text("\n".join(lines[-MAX_EVENTS:]) + "\n", encoding="utf-8")
    return {"event_id": event_id, "hits_hash": hits_hash}


def latest_route_event(repo_root: Path, *, query: str = "", event_id: str = "") -> dict[str, Any] | None:
    path = _events_path(repo_root)
    if not path.exists():
        return None
    normalized_query = normalize_query(query) if query else ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for raw_line in reversed(lines):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except Exception:
            continue
        if not isinstance(event, dict):
            continue
        if event_id and event.get("event_id") == event_id:
            return event
        if normalized_query and event.get("normalized_query") == normalized_query:
            return event
    return None


def record_success(
    repo_root: Path,
    *,
    query: str,
    target_paths: list[str],
    source: str,
    event_key: str = "",
) -> dict[str, Any]:
    payload = _read_learning_payload(repo_root)
    records = payload.setdefault("records", [])
    normalized_query = normalize_query(query)
    terms = query_terms(query)
    updated_records: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    by_key = {
        record.get("id"): record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    for raw_target in target_paths:
        target_path = normalize_target_path(repo_root, raw_target)
        record_id = hashlib.sha1(f"{normalized_query}\0{target_path}".encode("utf-8")).hexdigest()[:16]
        record = by_key.get(
            record_id,
            {
                "id": record_id,
                "query": query,
                "normalized_query": normalized_query,
                "query_terms": terms,
                "target_path": target_path,
                "success_count": 0,
                "sources": [],
                "source_counts": {},
                "created_at": _utcnow(),
            },
        )
        record["updated_at"] = _utcnow()
        record["query_terms"] = terms
        record["query"] = query
        sources = list(record.get("sources", []))
        if source not in sources:
            sources.append(source)
        record["sources"] = sources
        event_keys = {
            key: [str(item) for item in value if str(item).strip()]
            for key, value in dict(record.get("event_keys", {})).items()
            if isinstance(value, list)
        }
        source_event_keys = list(event_keys.get(source, []))
        if event_key and event_key in source_event_keys:
            by_key[record_id] = record
            changed.append(record)
            continue
        source_counts = dict(record.get("source_counts", {}))
        source_counts[source] = int(source_counts.get(source, 0)) + 1
        record["source_counts"] = source_counts
        if event_key:
            source_event_keys.append(event_key)
            event_keys[source] = source_event_keys[-32:]
            record["event_keys"] = event_keys
        record["success_count"] = int(record.get("success_count", 0)) + 1
        by_key[record_id] = record
        changed.append(record)
    updated_records.extend(sorted(by_key.values(), key=lambda item: (item.get("target_path", ""), item.get("normalized_query", ""))))
    payload["records"] = updated_records
    _write_json(_path(repo_root), payload)
    return {"count": len(changed), "records": changed}


def related_matches(
    repo_root: Path,
    *,
    query: str,
    target_path: str = "",
    limit: int = 3,
    min_overlap_ratio: float = MIN_OVERLAP_RATIO,
) -> list[dict[str, Any]]:
    payload = _read_json(_path(repo_root), default={"version": 1, "records": []})
    normalized_query = normalize_query(query)
    query_term_list = query_terms(query)
    normalized_target = normalize_target_path(repo_root, target_path) if target_path else ""
    matches: list[dict[str, Any]] = []

    for record in payload.get("records", []):
        if not isinstance(record, dict):
            continue
        record_target = normalize_target_path(repo_root, str(record.get("target_path", "")).strip())
        if normalized_target and record_target != normalized_target:
            continue
        success_count = int(record.get("success_count", 0))
        if success_count <= 0:
            continue
        source_counts = record.get("source_counts", {})
        adoption_count = int(source_counts.get("adoption", 0)) if isinstance(source_counts, dict) else 0
        record_query = str(record.get("query", "")).strip()
        if not record_query or not record_target:
            continue

        if str(record.get("normalized_query", "")).strip() == normalized_query:
            boost = EXACT_QUERY_BOOST + min(success_count - 1, 2) * 0.15 + min(adoption_count, 2) * 0.35
            matches.append(
                {
                    "query": record_query,
                    "target_path": record_target,
                    "match_type": "exact",
                    "overlap": 1.0,
                    "task_coverage": 1.0,
                    "record_coverage": 1.0,
                    "success_count": success_count,
                    "adoption_count": adoption_count,
                    "boost": round(boost, 4),
                    "history_score": round(boost, 4),
                    "reason": f"learned_exact_query:{success_count}/adoption:{adoption_count}",
                }
            )
            continue

        record_term_list = _record_terms(record)
        metrics = qi.overlap_metrics(query_term_list, record_term_list)
        overlap = float(metrics["overlap"])
        if overlap < min_overlap_ratio:
            continue
        boost = RELATED_QUERY_BOOST * overlap + min(success_count, 3) * 0.08 + min(adoption_count, 2) * 0.12
        matches.append(
            {
                "query": record_query,
                "target_path": record_target,
                "match_type": "related",
                "overlap": overlap,
                "task_coverage": float(metrics["left_coverage"]),
                "record_coverage": float(metrics["right_coverage"]),
                "success_count": success_count,
                "adoption_count": adoption_count,
                "boost": round(boost, 4),
                "history_score": round(boost, 4),
                "reason": f"learned_related_query:{overlap:.2f}/{success_count}/adoption:{adoption_count}",
            }
        )

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in matches:
        key = (item["query"], item["target_path"])
        previous = deduped.get(key)
        if previous is None or float(item["boost"]) > float(previous["boost"]):
            deduped[key] = item
    ordered = sorted(
        deduped.values(),
        key=lambda item: (-float(item["boost"]), item["target_path"], item["query"]),
    )
    return ordered[:limit]


def learning_boost(repo_root: Path, *, query: str, target_path: str) -> dict[str, Any] | None:
    matches = related_matches(repo_root, query=query, target_path=target_path, limit=1)
    if not matches:
        return None
    best = matches[0]
    return {"boost": round(float(best["boost"]), 4), "reason": str(best["reason"])}
