from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import memory_tool as mt
import query_intel as qi
import semantic_store as ss
from llm_semantic_client import LocalEmbeddingClient, PROMPT_VERSION, SemanticLLMClient


SCHEMA_VERSION = 1
TOP_K_DEFAULT = 5
LOCAL_EMBEDDING_SCORE_SCALE = 5.0


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def index_path(repo_root: Path) -> Path:
    return ss.store_path(repo_root)


def meta_path(repo_root: Path) -> Path:
    return ss.store_path(repo_root)


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    return []


def _candidate_notes(repo_root: Path) -> list[mt.NoteRecord]:
    notes = mt.scan_memory_notes(repo_root)
    return [
        note
        for note in notes
        if mt.note_is_runtime_eligible(note) and note.frontmatter.get("canonical") is True
    ]


def _source_hash(note: mt.NoteRecord) -> str:
    frontmatter = note.frontmatter
    payload = {
        "title": frontmatter.get("title", ""),
        "aliases": _normalize_list(frontmatter.get("aliases", [])),
        "keywords": _normalize_list(frontmatter.get("keywords", [])),
        "triggers": _normalize_list(frontmatter.get("triggers", [])),
        "when_to_read": _normalize_list(frontmatter.get("when_to_read", [])),
        "body_excerpt": note.body[:1200],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _note_payload(note: mt.NoteRecord) -> dict[str, Any]:
    frontmatter = note.frontmatter
    return {
        "path": f"memory/{note.rel_path}",
        "doc_type": str(frontmatter.get("doc_type", "")).strip(),
        "asset_type": "memory",
        "title": str(frontmatter.get("title", "")).strip(),
        "aliases": _normalize_list(frontmatter.get("aliases", [])),
        "keywords": _normalize_list(frontmatter.get("keywords", [])),
        "triggers": _normalize_list(frontmatter.get("triggers", [])),
        "when_to_read": _normalize_list(frontmatter.get("when_to_read", [])),
        "excerpt": mt.note_excerpt(note),
    }


def _embedding_text(entry: dict[str, Any]) -> str:
    return " ".join(
        [
            str(entry.get("title", "")),
            " ".join(_normalize_list(entry.get("aliases"))),
            " ".join(_normalize_list(entry.get("keywords"))),
            " ".join(_normalize_list(entry.get("triggers"))),
            " ".join(_normalize_list(entry.get("when_to_read"))),
            str(entry.get("intent", "")),
            " ".join(_normalize_list(entry.get("problem_signals"))),
            " ".join(_normalize_list(entry.get("paraphrases"))),
            " ".join(_normalize_list(entry.get("related_queries"))),
            str(entry.get("action_summary", "")),
            str(entry.get("excerpt", "")),
        ]
    ).strip()


def _coerce_embedding(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    vector: list[float] = []
    for item in value:
        try:
            vector.append(float(item))
        except (TypeError, ValueError):
            return []
    return vector


def _score_entry(query: str, entry: dict[str, Any]) -> tuple[float, list[str]]:
    query_terms = qi.flatten_query_terms(query, limit=16)
    scores: list[tuple[str, float, list[str]]] = []
    field_weights = {
        "intent": 1.6,
        "problem_signals": 1.4,
        "paraphrases": 1.2,
        "when_to_use": 1.0,
        "related_queries": 0.9,
        "action_summary": 0.6,
    }
    for field_name, weight in field_weights.items():
        value = entry.get(field_name, "")
        if isinstance(value, list):
            field_terms = []
            for item in value:
                field_terms.extend(qi.flatten_query_terms(str(item), limit=8))
        else:
            field_terms = qi.flatten_query_terms(str(value), limit=12)
        metrics = qi.overlap_metrics(query_terms, field_terms)
        if metrics["overlap"] <= 0:
            continue
        score = round(weight * metrics["overlap"], 4)
        scores.append((field_name, score, metrics["shared_terms"]))
    total = sum(item[1] for item in scores)
    reasons = [f"{field}:{','.join(shared[:3])} (+{score:.2f})" for field, score, shared in scores]
    return round(total, 4), reasons


def build_semantic_index(repo_root: Path, *, force: bool = False) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    existing_entries, _ = ss.read_semantic_index(repo_root)
    existing_by_path = {
        str(entry.get("path", "")).strip(): entry
        for entry in existing_entries
        if isinstance(entry, dict) and str(entry.get("path", "")).strip()
    }
    client = SemanticLLMClient(repo_root)
    embedding_client = LocalEmbeddingClient()
    entries: list[dict[str, Any]] = []
    rebuilt_paths: list[str] = []
    reused_paths: list[str] = []
    for note in _candidate_notes(repo_root):
        payload = _note_payload(note)
        note_path = payload["path"]
        source_hash = _source_hash(note)
        cached = existing_by_path.get(note_path)
        if (
            not force
            and cached
            and cached.get("schema_version") == SCHEMA_VERSION
            and cached.get("prompt_version") == PROMPT_VERSION
            and cached.get("source_hash") == source_hash
        ):
            entries.append(cached)
            reused_paths.append(note_path)
            continue
        generated = client.generate_index_entry(payload)
        entry = {
            "path": note_path,
            "doc_type": payload["doc_type"],
            "asset_type": payload["asset_type"],
            "title": payload["title"],
            "aliases": payload["aliases"],
            "keywords": payload["keywords"],
            "triggers": payload["triggers"],
            "when_to_read": payload["when_to_read"],
            "excerpt": payload["excerpt"],
            "source_hash": source_hash,
            "schema_version": SCHEMA_VERSION,
            "model": generated["model"],
            "prompt_version": generated["prompt_version"],
            "indexed_at": _utcnow(),
            "invalidation_reason": "force_rebuild" if force else "source_changed",
            "intent": generated["intent"],
            "problem_signals": generated["problem_signals"],
            "paraphrases": generated["paraphrases"],
            "when_to_use": generated["when_to_use"],
            "when_not_to_use": generated["when_not_to_use"],
            "related_queries": generated["related_queries"],
            "action_summary": generated["action_summary"],
            "confidence": generated["confidence"],
            "evidence_spans": generated["evidence_spans"],
            "source_excerpt_refs": generated["source_excerpt_refs"],
        }
        entries.append(entry)
        rebuilt_paths.append(note_path)
    entries.sort(key=lambda item: item["path"])
    embedding_mode = client.mode
    if embedding_client.available and entries:
        embedding_vectors = embedding_client.encode_texts([_embedding_text(entry) for entry in entries])
        if len(embedding_vectors) == len(entries):
            for entry, vector in zip(entries, embedding_vectors):
                entry["embedding"] = vector
                entry["embedding_model"] = embedding_client.model_name
            embedding_mode = embedding_client.mode
    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utcnow(),
        "entry_count": len(entries),
        "mode": embedding_mode,
        "embedding_model": embedding_client.model_name if embedding_mode == "local_embedding" else "",
        "rebuilt_paths": rebuilt_paths,
        "reused_paths": reused_paths,
        "prompt_version": PROMPT_VERSION,
        "storage_backend": "sqlite",
    }
    ss.replace_semantic_index(repo_root, entries=entries, meta=meta)
    return {
        "semantic_index": {
            "path": str(index_path(repo_root).relative_to(repo_root)),
            "meta_path": str(meta_path(repo_root).relative_to(repo_root)),
            "entry_count": len(entries),
            "mode": embedding_mode,
            "rebuilt_paths": rebuilt_paths,
            "reused_paths": reused_paths,
            "storage_backend": "sqlite",
        }
    }


def inspect_semantic_candidates(repo_root: Path, *, task: str, top_k: int = TOP_K_DEFAULT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    entry_payloads, meta = ss.read_semantic_index(repo_root)
    embedding_client = LocalEmbeddingClient(str(meta.get("embedding_model", "")).strip() or None)
    entry_vectors = [_coerce_embedding(entry.get("embedding")) for entry in entry_payloads]
    embedding_scores = (
        embedding_client.score_candidates(task, entry_vectors)
        if embedding_client.available and entry_payloads and all(vector for vector in entry_vectors)
        else []
    )
    candidates: list[dict[str, Any]] = []
    for index, entry in enumerate(entry_payloads):
        score, reasons = _score_entry(task, entry)
        if index < len(embedding_scores):
            embedding_score = max(float(embedding_scores[index]), 0.0)
            if embedding_score > 0:
                score = max(score, round(embedding_score * LOCAL_EMBEDDING_SCORE_SCALE, 4))
                reasons = list(reasons) + [f"embedding_cosine:{embedding_score:.3f}"]
        if score <= 0:
            continue
        candidates.append(
            {
                "path": str(entry.get("path", "")).strip(),
                "title": str(entry.get("title", "")).strip(),
                "doc_type": str(entry.get("doc_type", "")).strip(),
                "score": score,
                "semantic_reasons": reasons,
                "intent": str(entry.get("intent", "")).strip(),
                "action_summary": str(entry.get("action_summary", "")).strip(),
                "source_hash": str(entry.get("source_hash", "")).strip(),
            }
        )
    candidates.sort(key=lambda item: (-float(item["score"]), item["path"]))
    return {
        "query": task,
        "semantic_mode": "cached",
        "semantic_index_path": str(index_path(repo_root).relative_to(repo_root)),
        "semantic_index_mode": str(meta.get("mode", "missing")),
        "semantic_storage_backend": str(meta.get("storage_backend", "sqlite")),
        "candidates": candidates[: max(top_k, 1)],
    }


def drop_semantic_note(repo_root: Path, *, path: str) -> bool:
    return ss.remove_semantic_entry(repo_root.resolve(), path=path)
