#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
LIB_DIR = SCRIPT_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import build_asset_index as bai
import memory_tool as mt
import query_intel as qi
for parent in Path(__file__).resolve().parents:
    shared_lib_dir = parent / ".codex" / "scripts" / "lib"
    if shared_lib_dir == LIB_DIR:
        continue
    if (shared_lib_dir / "evolution_promote.py").exists() and str(shared_lib_dir) not in sys.path:
        sys.path.insert(0, str(shared_lib_dir))
        break

import evolution_promote as ep
import procedural_candidates as pc
import reuse_learning as rl
import runtime_checkpoint as rc
import semantic_index as sidx
import session_archive as sa
import verifier_sidecar as vs
from llm_semantic_client import SemanticLLMClient

AGENT_CONTEXT_VERSION = 1
MEMORY_CONTEXT_LIMIT = 3
PROMPT_EXCERPT_LIMIT = 320
QUERY_VARIANT_LIMIT = 4
HYBRID_RECALL_TOP_K = 6
LEXICAL_RECALL_TOP_N = 12
SEMANTIC_RECALL_TOP_M = 8
RERANK_TOP_K = 5
VARIANT_RANK_BONUS = 0.12
REPEATED_HIT_BONUS = 0.18
RUNBOOK_CANDIDATE_BONUS = 0.2
HISTORY_MATCH_LIMIT = 3
HISTORY_TARGET_BONUS = 0.45
SEMANTIC_AMBIGUITY_RATIO = 0.8
SEMANTIC_ABSTRACT_TERMS = {
    "restore",
    "recover",
    "recovery",
    "review",
    "audit",
    "history",
    "recall",
    "找回",
    "恢复",
    "恢复线程",
    "聊天记录",
    "会话历史",
    "线程恢复",
}
GOVERNANCE_CORE_TERMS = {
    "governance",
    "hygiene",
    "治理",
    "记忆治理",
    "治理入口",
}
GOVERNANCE_SUPPORT_TERMS = {
    "aliases",
    "alias",
    "keywords",
    "routing",
    "route",
    "cleanup",
    "enrichment",
    "scan",
    "检索面",
    "补齐",
    "清理",
}
SESSION_STRATEGY_TERMS = {
    "session",
    "recall",
    "archived",
    "archive",
    "window",
    "priority",
}
STRONG_LEXICAL_RUNBOOK_MIN_SCORE = 3.0
STRONG_LEXICAL_RUNBOOK_MARGIN = 2.5
PROMOTION_DOC_TYPES = ("decision", "pattern", "runbook")

QUERY_PHRASE_REWRITES = {
    "找回之前聊天记录": [
        "recover previous chat history",
        "restore previous chat history",
        "session history recovery",
        "thread recovery",
    ],
    "聊天记录": [
        "chat history",
        "session history",
        "thread history",
    ],
    "会话历史": [
        "session history",
        "chat history",
    ],
    "线程恢复": [
        "thread recovery",
        "restore thread",
    ],
    "找回": [
        "recover",
        "restore",
        "recovery",
    ],
    "恢复": [
        "recover",
        "restore",
        "recovery",
    ],
    "聊天": [
        "chat",
        "session",
        "thread",
    ],
    "会话": [
        "session",
        "chat",
    ],
    "线程": [
        "thread",
    ],
}

TOOL_NAME = "codex-memo"


def emit_json(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def fail(command: str, exc: Exception) -> int:
    emit_json({"command": command, "error": str(exc)}, stream=sys.stderr)
    return 1


def positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return value


def resolve_home_root() -> Path:
    raw = os.environ.get("CODEX_MEMO_HOME_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home().resolve()


def load_bootstrap_module():
    script_path = Path(__file__).resolve().parents[1] / "skills" / "project-memory-loop" / "scripts" / "bootstrap_project_codex.py"
    spec = importlib.util.spec_from_file_location("codex_memo_bootstrap_project_codex", script_path)
    if not spec or not spec.loader:
        raise FileNotFoundError(f"Bootstrap script not found: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def infer_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".codex" / "memory").exists():
            return candidate
    return current


def project_memory_exists(repo_root: Path) -> bool:
    return mt.repo_memory_root(repo_root).exists()


def home_memory_exists(home_root: Path) -> bool:
    return mt.repo_memory_root(home_root).exists()


def home_is_distinct(repo_root: Path, home_root: Path) -> bool:
    return repo_root != home_root and home_memory_exists(home_root)


def resolve_extra_roots(repo_root: Path, home_root: Path, raw: str) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = {str(repo_root.resolve()), str(home_root.resolve())}
    for item in mt.normalize_list(raw):
        candidate = Path(item).expanduser().resolve()
        key = str(candidate)
        if key in seen or not project_memory_exists(candidate):
            continue
        roots.append(candidate)
        seen.add(key)
    return roots


def summarize_hits(hits: list[dict[str, Any]], *, source: str) -> list[dict[str, Any]]:
    return [{**hit, "source": source, "ref": f"{source}:{hit.get('path', '')}"} for hit in hits]


def merge_hits(
    project_hits: list[dict[str, Any]],
    home_hits: list[dict[str, Any]],
    top_k: int,
    *,
    extra_hits: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    def normalize_hits(hits: list[dict[str, Any]], *, default_source: str) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for hit in hits:
            source = str(hit.get("source", "")).strip() or default_source
            normalized.append({**hit, "source": source, "ref": str(hit.get("ref", "")).strip() or f"{source}:{hit.get('path', '')}"})
        return normalized

    source_rank = {"project": 0, "home": 1}
    merged = (
        normalize_hits(project_hits, default_source="project")
        + normalize_hits(home_hits, default_source="home")
        + normalize_hits(list(extra_hits or []), default_source="extra")
    )
    merged.sort(
        key=lambda item: (
            -float(item.get("score", 0)),
            source_rank.get(str(item.get("source", "")).strip(), 2),
            item.get("path", ""),
        )
    )
    return merged[: max(top_k, 1)]


def trim_hits(hits: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return hits[: max(limit, 1)]


def lexical_reasons_by_path(hits: list[dict[str, Any]], *, limit: int = RERANK_TOP_K) -> dict[str, list[str]]:
    return {
        str(hit.get("path", "")).strip(): list(hit.get("reasons", []))
        for hit in hits[:limit]
        if str(hit.get("path", "")).strip()
    }


def semantic_reasons_by_path(candidates: list[dict[str, Any]], *, limit: int = RERANK_TOP_K) -> dict[str, list[str]]:
    return {
        str(item.get("path", "")).strip(): list(item.get("semantic_reasons", []))
        for item in candidates[:limit]
        if str(item.get("path", "")).strip()
    }


def query_is_mixed_language(task: str) -> bool:
    has_ascii = bool(re.search(r"[A-Za-z]", task))
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", task))
    return has_ascii and has_cjk


def query_has_precise_lookup(task: str) -> bool:
    normalized = normalize_query_variant(task).lower()
    precise_markers = [".md", ".py", ".json", ".toml", ".yml", ".yaml", ".csv", "memory/", ".codex/"]
    if any(marker in normalized for marker in precise_markers):
        return True
    path_like = re.findall(r"(?<!\S)[A-Za-z0-9_.-]+[/\\][A-Za-z0-9_.\\/-]+(?!\S)", task)
    path_prefixes = ("memory/", ".codex/", "src/", "app/", "docs/", "tests/", "scripts/")
    for candidate in path_like:
        lowered_candidate = candidate.lower().replace("\\", "/")
        segments = [segment for segment in re.split(r"[/\\]+", candidate) if segment]
        if lowered_candidate.startswith(path_prefixes) or "." in candidate or len(segments) >= 3:
            return True
    if any(term in normalized for term in ["prd", "context.md", "plan", "task.json", "summary.md", "issue-"]):
        return True
    return False


def semantic_candidates_to_hits(
    semantic_candidates: list[dict[str, Any]],
    *,
    existing_paths: set[str],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for item in semantic_candidates[:SEMANTIC_RECALL_TOP_M]:
        path = str(item.get("path", "")).strip()
        if not path or path in existing_paths or not path.startswith("memory/"):
            continue
        doc_type = str(item.get("doc_type", "")).strip()
        if not doc_type:
            continue
        hits.append(
            {
                "path": path,
                "ref": f"project:{path}",
                "title": str(item.get("title", "")).strip(),
                "kind": "memory",
                "doc_type": doc_type,
                "source": "project",
                "score": 0.0,
                "reasons": [f"semantic_cache:{float(item.get('score', 0.0)):.2f}"],
            }
        )
        existing_paths.add(path)
    return hits


def query_has_abstract_intent(task: str) -> bool:
    terms = [str(term).strip().lower() for term in qi.flatten_query_terms(task, limit=24)]
    if any(term in SEMANTIC_ABSTRACT_TERMS for term in terms):
        return True
    abstract_markers = (
        "memory system",
        "memory retrieval",
        "semantic recall",
        "review baseline",
        "chat history",
        "session history",
        "thread recovery",
        "记忆系统",
        "记忆检索",
        "语义召回",
        "聊天记录",
        "会话历史",
        "线程恢复",
        "记忆收敛",
        "thin entry",
    )
    normalized_task = normalize_query_variant(task).lower()
    return any(marker in normalized_task for marker in abstract_markers)


def query_has_governance_intent(task: str) -> bool:
    normalized_task = normalize_query_variant(task).lower()
    if "记忆治理入口" in task or "memory governance" in normalized_task:
        return True
    terms = {str(term).strip().lower() for term in qi.flatten_query_terms(task, limit=24)}
    has_core = bool(terms & GOVERNANCE_CORE_TERMS) or any(term in normalized_task for term in GOVERNANCE_CORE_TERMS)
    has_support = bool(terms & GOVERNANCE_SUPPORT_TERMS) or any(term in normalized_task for term in GOVERNANCE_SUPPORT_TERMS)
    return has_core and has_support


def candidate_signal_blob(candidate: dict[str, Any]) -> str:
    parts: list[str] = [
        str(candidate.get("path", "")).strip(),
        str(candidate.get("title", "")).strip(),
        str(candidate.get("intent", "")).strip(),
        str(candidate.get("action_summary", "")).strip(),
    ]
    parts.extend(str(item).strip() for item in candidate.get("semantic_reasons", [])[:4])
    return normalize_query_variant(" ".join(part for part in parts if part)).lower()


def candidate_is_governance_runbook(candidate: dict[str, Any]) -> bool:
    if candidate.get("kind") != "memory" or candidate.get("doc_type") != "runbook":
        return False
    blob = candidate_signal_blob(candidate)
    has_core = any(term in blob for term in GOVERNANCE_CORE_TERMS)
    has_support = any(term in blob for term in GOVERNANCE_SUPPORT_TERMS)
    return has_core or (has_support and "memory/" in str(candidate.get("path", "")).strip())


def candidate_is_session_strategy_runbook(candidate: dict[str, Any]) -> bool:
    if candidate.get("kind") != "memory" or candidate.get("doc_type") != "runbook":
        return False
    blob = candidate_signal_blob(candidate)
    path = str(candidate.get("path", "")).strip().lower()
    has_session_strategy = any(term in blob for term in SESSION_STRATEGY_TERMS) or "session-recall" in path
    return has_session_strategy and not candidate_is_governance_runbook(candidate)


def governance_guard_override(
    *,
    task: str,
    candidates: list[dict[str, Any]],
    selected_candidate: dict[str, Any] | None,
    execution_gate: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    if not query_has_governance_intent(task):
        return selected_candidate, []
    gate_selected_path = str(execution_gate.get("selected_path", "")).strip()
    gate_candidate = next((item for item in candidates if item.get("path") == gate_selected_path), None)
    if (
        gate_candidate
        and selected_candidate
        and gate_candidate.get("path") != selected_candidate.get("path")
        and gate_candidate.get("kind") == "memory"
        and gate_candidate.get("doc_type") == "runbook"
        and candidate_is_governance_runbook(gate_candidate)
        and float(gate_candidate.get("lexical_score", 0.0)) > float(selected_candidate.get("lexical_score", 0.0)) * 1.2
    ):
        return gate_candidate, ["governance_guard:keep_lexical_governance_entry"]
    if selected_candidate and not candidate_is_session_strategy_runbook(selected_candidate):
        return selected_candidate, []
    if gate_candidate and gate_candidate.get("kind") == "memory" and gate_candidate.get("doc_type") == "runbook":
        return gate_candidate, ["governance_guard:keep_execution_gate_runbook"]
    governance_candidates = [item for item in candidates if candidate_is_governance_runbook(item)]
    if not governance_candidates:
        return selected_candidate, []
    governance_candidates.sort(
        key=lambda item: (
            -(float(item.get("lexical_score", 0.0)) + float(item.get("semantic_score", 0.0))),
            item.get("path", ""),
        )
    )
    best_governance = governance_candidates[0]
    if selected_candidate and best_governance.get("path") == selected_candidate.get("path"):
        return selected_candidate, []
    return best_governance, ["governance_guard:keep_governance_runbook_over_session_strategy"]


def strong_lexical_runbook_guard(
    *,
    candidates: list[dict[str, Any]],
    selected_candidate: dict[str, Any] | None,
    execution_gate: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    if execution_gate.get("state") != "hit":
        return selected_candidate, []
    gate_selected_path = str(execution_gate.get("selected_path", "")).strip()
    if not gate_selected_path:
        return selected_candidate, []
    gate_candidate = next((item for item in candidates if item.get("path") == gate_selected_path), None)
    if gate_candidate is None or selected_candidate is None:
        return selected_candidate, []
    if gate_candidate.get("path") == selected_candidate.get("path"):
        return selected_candidate, []
    if gate_candidate.get("kind") != "memory" or gate_candidate.get("doc_type") != "runbook":
        return selected_candidate, []
    if selected_candidate.get("kind") != "memory" or selected_candidate.get("doc_type") != "runbook":
        return selected_candidate, []
    gate_lexical = float(gate_candidate.get("lexical_score", 0.0))
    selected_lexical = float(selected_candidate.get("lexical_score", 0.0))
    if selected_lexical <= 0:
        return selected_candidate, []
    if gate_lexical < STRONG_LEXICAL_RUNBOOK_MIN_SCORE:
        return selected_candidate, []
    if gate_lexical < selected_lexical * STRONG_LEXICAL_RUNBOOK_MARGIN:
        return selected_candidate, []
    return gate_candidate, ["lexical_guard:keep_strong_execution_gate_runbook"]


def should_apply_semantic_rerank(
    *,
    task: str,
    merged_hits: list[dict[str, Any]],
    semantic_candidates: list[dict[str, Any]],
    execution_gate: dict[str, Any],
) -> tuple[bool, str]:
    if query_has_precise_lookup(task):
        return False, "precise_lookup"
    top_hit = merged_hits[0] if merged_hits else None
    second_hit = merged_hits[1] if len(merged_hits) > 1 else None
    mixed_language = query_is_mixed_language(task)
    abstract_intent = query_has_abstract_intent(task)
    governance_intent = query_has_governance_intent(task)
    top_is_runbook = bool(
        top_hit
        and top_hit.get("kind") == "memory"
        and top_hit.get("doc_type") == "runbook"
        and top_hit.get("source") == "project"
    )
    if top_hit and not top_is_runbook:
        return True, "top1_not_canonical_runbook"
    semantic_top = semantic_candidates[0] if semantic_candidates else None
    lexical_top_path = str(top_hit.get("path", "")).strip() if top_hit else ""
    semantic_top_path = str(semantic_top.get("path", "")).strip() if semantic_top else ""
    if (
        top_is_runbook
        and execution_gate.get("state") == "hit"
        and lexical_top_path
        and (not semantic_top_path or semantic_top_path == lexical_top_path)
    ):
        if governance_intent:
            return True, "governance_intent_query"
        if mixed_language:
            return True, "mixed_language_query"
        if not second_hit or float(top_hit.get("score", 0.0)) <= 0:
            if abstract_intent:
                return True, "abstract_intent_query"
            return False, "high_confidence_runbook_hit"
        if second_hit and second_hit.get("kind") == "asset" and second_hit.get("asset_type") in {"session", "archived_session"}:
            return False, "high_confidence_runbook_hit"
        if second_hit:
            ratio = float(second_hit.get("score", 0.0)) / float(top_hit.get("score", 0.0))
        else:
            ratio = 0.0
        if ratio >= SEMANTIC_AMBIGUITY_RATIO:
            return True, "lexical_gap_ambiguous"
        if abstract_intent:
            return True, "abstract_intent_query"
        return False, "high_confidence_runbook_hit"
    if mixed_language:
        return True, "mixed_language_query"
    if governance_intent:
        return True, "governance_intent_query"
    if top_hit and second_hit and float(top_hit.get("score", 0.0)) > 0:
        ratio = float(second_hit.get("score", 0.0)) / float(top_hit.get("score", 0.0))
        if ratio >= SEMANTIC_AMBIGUITY_RATIO:
            return True, "lexical_gap_ambiguous"
    if abstract_intent:
        return True, "abstract_intent_query"
    if semantic_top_path and semantic_top_path != lexical_top_path:
        return True, "semantic_conflict"
    if execution_gate.get("state") != "hit":
        return True, "non_executable_gate"
    return False, "high_confidence_runbook_hit"


def determine_gate_from_candidate(
    candidate: dict[str, Any] | None,
    *,
    current_gate: dict[str, Any],
) -> tuple[str, str]:
    if candidate is None:
        return current_gate.get("state", "miss"), ""
    source = str(candidate.get("source", "")).strip() or "project"
    path = str(candidate.get("path", "")).strip()
    if candidate.get("kind") == "memory" and candidate.get("doc_type") == "runbook" and source == "project":
        return "hit", f"{source}:{path}"
    return "reference_only", f"{source}:{path}"


def build_rerank_candidates(
    *,
    lexical_hits: list[dict[str, Any]],
    semantic_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for hit in lexical_hits[:LEXICAL_RECALL_TOP_N]:
        path = str(hit.get("path", "")).strip()
        if not path:
            continue
        combined[path] = {
            "path": path,
            "ref": str(hit.get("ref", "")).strip(),
            "title": compact_text(str(hit.get("title", "")).strip(), limit=120),
            "kind": str(hit.get("kind", "")).strip(),
            "doc_type": str(hit.get("doc_type", "")).strip(),
            "asset_type": str(hit.get("asset_type", "")).strip(),
            "source": str(hit.get("source", "")).strip() or "project",
            "lexical_score": float(hit.get("score", 0.0)),
            "semantic_score": 0.0,
            "lexical_reasons": [compact_text(item, limit=96) for item in list(hit.get("reasons", []))[:3]],
            "semantic_reasons": [],
            "intent": "",
            "action_summary": "",
        }
    for item in semantic_candidates[:SEMANTIC_RECALL_TOP_M]:
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        entry = combined.setdefault(
            path,
            {
                "path": path,
                "ref": f"project:{path}",
                "title": compact_text(str(item.get("title", "")).strip(), limit=120),
                "kind": "memory",
                "doc_type": str(item.get("doc_type", "")).strip(),
                "asset_type": "memory",
                "source": "project",
                "lexical_score": 0.0,
                "semantic_score": 0.0,
                "lexical_reasons": [],
                "semantic_reasons": [],
                "intent": "",
                "action_summary": "",
            },
        )
        entry["semantic_score"] = max(float(entry.get("semantic_score", 0.0)), float(item.get("score", 0.0)))
        entry["semantic_reasons"] = [compact_text(reason, limit=96) for reason in list(item.get("semantic_reasons", []))[:3]]
        entry["intent"] = compact_text(str(item.get("intent", "")).strip(), limit=120)
        entry["action_summary"] = compact_text(str(item.get("action_summary", "")).strip(), limit=220)
        if not entry.get("title"):
            entry["title"] = compact_text(str(item.get("title", "")).strip(), limit=120)
    candidates = list(combined.values())
    candidates.sort(
        key=lambda item: (
            -(float(item.get("lexical_score", 0.0)) + float(item.get("semantic_score", 0.0))),
            0 if item.get("kind") == "memory" and item.get("doc_type") == "runbook" else 1,
            item.get("path", ""),
        )
    )
    return candidates[:RERANK_TOP_K]


def apply_semantic_rerank(
    *,
    repo_root: Path,
    task: str,
    lexical_hits: list[dict[str, Any]],
    semantic_candidates: list[dict[str, Any]],
    execution_gate: dict[str, Any],
) -> dict[str, Any]:
    cache_hit = sidx.index_path(repo_root).exists()
    should_rerank, trigger_reason = should_apply_semantic_rerank(
        task=task,
        merged_hits=lexical_hits,
        semantic_candidates=semantic_candidates,
        execution_gate=execution_gate,
    )
    base_payload = {
        "semantic_mode": "skipped",
        "semantic_cache_hit": cache_hit,
        "semantic_model_used": "",
        "semantic_trigger_reason": trigger_reason,
        "semantic_reasons": semantic_reasons_by_path(semantic_candidates),
        "lexical_reasons": lexical_reasons_by_path(lexical_hits),
        "rerank_reasons": [],
        "gate_override_reason": "",
        "rerank_candidates": [],
        "rerank_skipped_reason": "" if should_rerank else trigger_reason,
        "semantic_index_rebuild": {},
    }
    if not should_rerank:
        return base_payload

    candidates = build_rerank_candidates(lexical_hits=lexical_hits, semantic_candidates=semantic_candidates)
    if not candidates:
        base_payload["rerank_skipped_reason"] = "no_rerank_candidates"
        return base_payload
    reranked = SemanticLLMClient.local_rerank(
        {
            "query": task,
            "current_gate": {
                "state": execution_gate.get("state", ""),
                "selected_path": execution_gate.get("selected_path", ""),
                "selected_kind": execution_gate.get("selected_kind", ""),
            },
            "candidates": candidates,
        }
    )
    selected_path = str(reranked.get("selected_path", "")).strip()
    selected_candidate = next((item for item in candidates if item["path"] == selected_path), None)
    selected_candidate, governance_reasons = governance_guard_override(
        task=task,
        candidates=candidates,
        selected_candidate=selected_candidate,
        execution_gate=execution_gate,
    )
    selected_candidate, lexical_guard_reasons = strong_lexical_runbook_guard(
        candidates=candidates,
        selected_candidate=selected_candidate,
        execution_gate=execution_gate,
    )
    if selected_candidate is not None:
        selected_path = str(selected_candidate.get("path", "")).strip()
    selected_state, selected_ref = determine_gate_from_candidate(selected_candidate, current_gate=execution_gate)
    return {
        **base_payload,
        "semantic_mode": "local",
        "semantic_model_used": "local-semantic-rerank",
        "rerank_reasons": list(reranked.get("rerank_reasons", [])) + governance_reasons + lexical_guard_reasons,
        "gate_override_reason": (
            "governance guard kept the governance runbook over a competing rerank candidate"
            if governance_reasons
            else (
                "lexical guard kept the strongest surfaced runbook over a weaker semantic competitor"
                if lexical_guard_reasons
                else str(reranked.get("gate_override_reason", "")).strip()
            )
        ),
        "rerank_candidates": candidates,
        "rerank_selected_path": selected_path,
        "rerank_selected_ref": selected_ref,
        "rerank_selected_state": selected_state,
    }


def build_execution_gate(
    *,
    project_memory_hits: list[dict[str, Any]],
    project_hits: list[dict[str, Any]],
    merged_hits: list[dict[str, Any]],
    project_fallback_context: bool,
    fallback_context: bool,
) -> dict[str, Any]:
    top_project_hit = project_hits[0] if project_hits else None
    top_project_runbook = next(
        (
            hit
            for hit in project_hits
            if hit.get("kind") == "memory" and hit.get("doc_type") == "runbook"
        ),
        None,
    )
    if (
        top_project_hit
        and not project_fallback_context
        and top_project_hit.get("kind") == "memory"
        and top_project_hit.get("doc_type") == "runbook"
    ):
        selected_hit = top_project_hit
        return {
            "state": "hit",
            "selected_ref": selected_hit.get("ref", ""),
            "selected_path": selected_hit.get("path", ""),
            "selected_title": selected_hit.get("title", ""),
            "selected_kind": selected_hit.get("kind", ""),
            "selected_source": selected_hit.get("source", ""),
            "required_closeout": ["adoption_evidence"],
            "prompt": (
                f"已命中可执行记忆: {selected_hit.get('path', '')}. "
                "本次按该记忆执行. 若偏离, 必须说明原因并在收尾补 adoption evidence."
            ),
        }
    if (
        top_project_runbook
        and top_project_hit
        and not project_fallback_context
        and top_project_hit.get("kind") == "asset"
        and top_project_hit.get("asset_type") in {"session", "archived_session"}
    ):
        return {
            "state": "hit",
            "selected_ref": top_project_runbook.get("ref", ""),
            "selected_path": top_project_runbook.get("path", ""),
            "selected_title": top_project_runbook.get("title", ""),
            "selected_kind": top_project_runbook.get("kind", ""),
            "selected_source": top_project_runbook.get("source", ""),
            "required_closeout": ["adoption_evidence"],
            "prompt": (
                f"已命中可执行记忆: {top_project_runbook.get('path', '')}. "
                "本次按该记忆执行. 若偏离, 必须说明原因并在收尾补 adoption evidence."
            ),
        }
    top_hit = merged_hits[0] if merged_hits else None
    if top_hit:
        prompt = (
            f"已命中参考项: {top_hit.get('path', '')}. "
            "该命中项可作为线索或参考, 但不计作可执行记忆. 收尾前必须补齐: runbook + benchmark query + adoption evidence, 需要时补 script."
        )
        if fallback_context:
            prompt = (
                f"已命中低置信参考项: {top_hit.get('path', '')}. "
                "该命中项只可作为线索或参考, 不能当作可执行记忆. 收尾前必须补齐: runbook + benchmark query + adoption evidence, 需要时补 script."
            )
        return {
            "state": "reference_only",
            "selected_ref": top_hit.get("ref", ""),
            "selected_path": top_hit.get("path", ""),
            "selected_title": top_hit.get("title", ""),
            "selected_kind": top_hit.get("kind", ""),
            "selected_source": top_hit.get("source", ""),
            "required_closeout": ["runbook", "benchmark_query", "adoption_evidence", "script_if_needed"],
            "prompt": prompt,
        }
    return {
        "state": "miss",
        "selected_ref": "",
        "selected_path": "",
        "selected_title": "",
        "selected_kind": "",
        "selected_source": "",
        "required_closeout": ["runbook", "benchmark_query", "adoption_evidence", "script_if_needed"],
        "prompt": (
            "未命中可执行记忆. 本次按新问题族处理. "
            "收尾前必须补齐: runbook + benchmark query + adopted evidence, 需要时补 script."
        ),
    }


def build_closeout_gate(payload: dict[str, Any]) -> dict[str, Any]:
    traces = payload.get("retrieval_traces", [])
    ledger = dict(payload.get("closeout_ledger", {}))
    if not traces:
        return {
            "status": "not_started",
            "required": [],
            "prompt": "当前任务还没有 retrieval trace. 若本次未经过 route, 无额外收尾要求.",
        }
    latest = traces[-1] if isinstance(traces[-1], dict) else {}
    if str(latest.get("adopted_hit", "")).strip() and latest.get("evidence_paths"):
        return {
            "status": "satisfied",
            "required": [],
            "prompt": "收尾闭环已完成: adopted evidence 已记录.",
        }
    if (
        str(ledger.get("coverage_mode", "")).strip() == "new_family"
        and ledger.get("runbook_paths")
        and ledger.get("benchmark_queries")
        and ledger.get("coverage_evidence")
    ):
        return {
            "status": "satisfied",
            "required": [],
            "prompt": "收尾闭环已完成: 新问题族 coverage 已记录.",
        }
    required = ["adoption_evidence"] if str(latest.get("selected_hit", "")).strip() else [
        "runbook",
        "benchmark_query",
        "adoption_evidence",
        "script_if_needed",
    ]
    return {
        "status": "pending",
        "required": required,
        "prompt": (
            "收尾闭环未完成: 已有 route 轨迹但未形成可验证闭环. "
            "命中可执行记忆时补 adoption evidence; 新问题族路径补 runbook + benchmark query + adoption evidence, 需要时补 script."
        ),
    }


def normalize_hit_reference(raw_path: str) -> tuple[str, str]:
    cleaned = raw_path.strip()
    if cleaned.startswith("project:"):
        return "project", cleaned.removeprefix("project:")
    if cleaned.startswith("home:"):
        return "home", cleaned.removeprefix("home:")
    return "project", cleaned


def normalize_corrections(raw: str) -> list[dict[str, str]]:
    corrections: list[dict[str, str]] = []
    for item in mt.normalize_list(raw):
        field, separator, transition = item.partition(":")
        old_value, arrow, new_value = transition.partition("->")
        if not separator or not arrow or not field.strip() or not old_value.strip() or not new_value.strip():
            raise ValueError("correction must use <field>:<old_value>-><new_value>")
        corrections.append(
            {
                "field": field.strip(),
                "old_value": old_value.strip(),
                "new_value": new_value.strip(),
                "raw": item.strip(),
            }
        )
    return corrections


def repo_relative_to_absolute(repo_root: Path, raw_path: str) -> Path:
    cleaned = raw_path.strip()
    if cleaned.startswith("memory/"):
        return (repo_root / ".codex" / "memory" / cleaned.removeprefix("memory/")).resolve()
    return (repo_root / cleaned).resolve()


def ensure_repo_paths_exist(repo_root: Path, paths: list[str], *, field_name: str) -> None:
    missing = [path for path in paths if not repo_relative_to_absolute(repo_root, path).exists()]
    if missing:
        raise ValueError(f"{field_name} must exist under repo_root: {', '.join(missing)}")


def compact_text(text: str, *, limit: int = PROMPT_EXCERPT_LIMIT) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def normalize_query_variant(text: str) -> str:
    return " ".join(str(text).split()).strip()


def asset_hint_from_path(raw_path: str) -> str:
    path = Path(raw_path)
    stem = path.stem.replace("-", " ").replace("_", " ").strip()
    parts = [part for part in [stem, path.parent.name.replace("-", " ").replace("_", " ").strip()] if part]
    return " ".join(dict.fromkeys(parts))


def query_signal_terms(query: str) -> list[str]:
    return rl.query_terms(query)


def phrase_rewrite_variants(task: str) -> list[str]:
    variants: list[str] = []
    lowered = task.lower()

    def push(candidate: str) -> None:
        normalized = normalize_query_variant(candidate)
        if normalized and normalized not in variants:
            variants.append(normalized)

    for phrase, rewrites in QUERY_PHRASE_REWRITES.items():
        phrase_lower = phrase.lower()
        if phrase not in task and phrase_lower not in lowered:
            continue
        for rewrite in rewrites:
            push(f"{task} {rewrite}")
            if phrase in task:
                push(task.replace(phrase, rewrite))
            elif phrase_lower in lowered:
                push(f"{task} {rewrite}")
    return variants


def related_history_matches(repo_root: Path, task: str) -> list[dict[str, Any]]:
    return rl.related_matches(repo_root, query=task, limit=HISTORY_MATCH_LIMIT)


def load_evolution_retrieval_hints(repo_root: Path, task: str) -> list[dict[str, Any]]:
    capsules_path = repo_root / ".codex" / "evolution" / "capsules.jsonl"
    if not capsules_path.exists():
        return []
    try:
        capsules = [
            json.loads(line)
            for line in capsules_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        return []
    payload = ep.suggest_memory_writeback(capsules)
    query_terms = {normalize_query_variant(term) for term in query_signal_terms(task) if normalize_query_variant(term)}
    matches: list[dict[str, Any]] = []
    for hint in payload.get("retrieval_hints", []):
        hint_terms = {normalize_query_variant(term) for term in hint.get("match_terms", []) if normalize_query_variant(term)}
        shared_terms = query_terms & hint_terms
        if query_terms and not shared_terms:
            continue
        if hint.get("retrieval_stage") == "shadowed" and len(shared_terms) < 2:
            continue
        matches.append(hint)
    return matches


def build_query_variants(repo_root: Path, task: str, checkpoint: dict[str, Any]) -> list[str]:
    variants: list[str] = []

    def push(candidate: str) -> None:
        normalized = normalize_query_variant(candidate)
        if normalized and normalized not in variants:
            variants.append(normalized)

    push(task)
    for item in list(checkpoint.get("key_facts", []))[:2]:
        push(f"{task} {item}")
    for item in list(checkpoint.get("current_invariant", []))[:2]:
        push(f"{task} {item}")
    for item in list(checkpoint.get("task_assets", []))[:2]:
        hint = asset_hint_from_path(item)
        if hint:
            push(f"{task} {hint}")
    for item in list(checkpoint.get("reused_assets", []))[:1]:
        hint = asset_hint_from_path(item)
        if hint:
            push(f"{task} {hint}")
    traces = checkpoint.get("retrieval_traces", [])
    latest = traces[-1] if traces and isinstance(traces[-1], dict) else {}
    latest_query = normalize_query_variant(latest.get("route_query", ""))
    if latest_query and latest_query != normalize_query_variant(task):
        push(latest_query)
    latest_selected = asset_hint_from_path(str(latest.get("selected_hit", "")).strip())
    if latest_selected:
        push(f"{task} {latest_selected}")
    for hint in load_evolution_retrieval_hints(repo_root, task):
        for candidate in hint.get("query_variants", []):
            push(candidate)
            push(f"{task} {candidate}")
    for candidate in phrase_rewrite_variants(task):
        push(candidate)
    for item in related_history_matches(repo_root, task):
        push(item["query"])
        target_hint = asset_hint_from_path(item["target_path"])
        if target_hint:
            push(f"{task} {target_hint}")
    return variants[:QUERY_VARIANT_LIMIT]


def hit_ref(hit: dict[str, Any]) -> str:
    return str(hit.get("ref", "")).strip() or f"{hit.get('source', 'project')}:{hit.get('path', '')}"


def build_hybrid_recall(
    *,
    repo_root: Path,
    home_root: Path,
    task: str,
    top_k: int,
    checkpoint: dict[str, Any],
    base_route_payload: dict[str, Any],
    extra_roots: list[Path] | None = None,
) -> dict[str, Any]:
    history_matches = related_history_matches(repo_root, task)
    query_variants = build_query_variants(repo_root, task, checkpoint)[:QUERY_VARIANT_LIMIT]
    variant_routes: list[dict[str, Any]] = []
    aggregated: dict[str, dict[str, Any]] = {}
    project_route_context = mt.get_route_context(repo_root)

    for index, query in enumerate(query_variants):
        if index == 0:
            payload = base_route_payload
        else:
            project_only_payload = mt.route_with_context(
                repo_root,
                query,
                top_k,
                route_context=project_route_context,
                record_event=False,
            )
            payload = {
                "merged_hits": list(project_only_payload.get("hits", [])),
                "execution_gate": build_execution_gate(
                    project_memory_hits=list(project_only_payload.get("memory_hits", [])),
                    project_hits=list(project_only_payload.get("hits", [])),
                    merged_hits=list(project_only_payload.get("hits", [])),
                    project_fallback_context=bool(project_only_payload.get("fallback_context", False)),
                    fallback_context=bool(project_only_payload.get("fallback_context", False)),
                ),
            }
        variant_routes.append(
            {
                "query": query,
                "execution_gate_state": payload["execution_gate"]["state"],
                "top_hit_path": payload["merged_hits"][0]["path"] if payload.get("merged_hits") else "",
            }
        )
        for rank, hit in enumerate(payload.get("merged_hits", [])[: max(top_k, 1)], start=1):
            ref = hit_ref(hit)
            entry = aggregated.get(ref)
            rank_bonus = max(top_k - rank, 0) * VARIANT_RANK_BONUS
            score_add = float(hit.get("score", 0.0)) + rank_bonus
            if entry is None:
                entry = {
                    "ref": ref,
                    "path": hit.get("path", ""),
                    "title": hit.get("title", ""),
                    "kind": hit.get("kind", ""),
                    "doc_type": hit.get("doc_type", ""),
                    "asset_type": hit.get("asset_type", ""),
                    "source": hit.get("source", ""),
                    "aggregate_score": score_add,
                    "hit_count": 1,
                    "matched_queries": [query],
                    "reasons": list(hit.get("reasons", []))[:4],
                }
                if entry["kind"] == "memory" and entry["doc_type"] == "runbook":
                    entry["aggregate_score"] += RUNBOOK_CANDIDATE_BONUS
                aggregated[ref] = entry
                continue
            entry["aggregate_score"] += score_add + REPEATED_HIT_BONUS
            if query not in entry["matched_queries"]:
                entry["matched_queries"].append(query)
            entry["hit_count"] += 1
            for reason in hit.get("reasons", [])[:2]:
                if reason not in entry["reasons"]:
                    entry["reasons"].append(reason)

    history_targets: dict[str, dict[str, Any]] = {}
    for item in history_matches:
        target_path = str(item.get("target_path", "")).strip()
        if not target_path:
            continue
        previous = history_targets.get(target_path)
        if previous is None or float(item.get("boost", item.get("history_score", 0.0))) > float(
            previous.get("boost", previous.get("history_score", 0.0))
        ):
            history_targets[target_path] = item
    for entry in aggregated.values():
        history = history_targets.get(str(entry.get("path", "")).strip())
        if history is None:
            continue
        boost = HISTORY_TARGET_BONUS + float(history.get("boost", history.get("history_score", 0.0)))
        entry["aggregate_score"] += boost
        history_reason = str(history.get("reason", "")).strip()
        if history_reason and not any(str(reason).startswith(history_reason) for reason in entry["reasons"]):
            entry["reasons"].append(history_reason)

    candidates = sorted(
        aggregated.values(),
        key=lambda item: (
            -float(item["aggregate_score"]),
            0 if item.get("kind") == "memory" and item.get("doc_type") == "runbook" else 1,
            item.get("path", ""),
        ),
    )[:HYBRID_RECALL_TOP_K]

    recommended = candidates[0] if candidates else None
    if recommended is None:
        recommended_mode = "none"
        recommended_action = "keep_backend_search"
    elif recommended.get("kind") == "memory" and recommended.get("doc_type") == "runbook":
        if base_route_payload["execution_gate"]["state"] == "hit" and base_route_payload["execution_gate"]["selected_path"] == recommended.get("path", ""):
            recommended_mode = "execute"
            recommended_action = "follow_execution_gate"
        else:
            recommended_mode = "executable_lead"
            recommended_action = "inspect_or_reroute"
    else:
        recommended_mode = "reference_lead"
        recommended_action = "inspect_candidate"

    prompt_lines = [
        "### [HYBRID RECALL]",
        f"- base_task: {task}",
        f"- query_variants: {', '.join(query_variants) if query_variants else '暂无'}",
        f"- recommended_mode: {recommended_mode}",
        f"- recommended_action: {recommended_action}",
        "- semantic_candidates:",
    ]
    if candidates:
        for item in candidates[:3]:
            prompt_lines.append(
                f"  - {item['path']} | mode="
                f"{'runbook' if item.get('kind') == 'memory' and item.get('doc_type') == 'runbook' else item.get('kind')} | "
                f"queries={len(item.get('matched_queries', []))} | score={float(item.get('aggregate_score', 0.0)):.2f}"
            )
    else:
        prompt_lines.append("  - 暂无")
    prompt_lines.append("- rule: 这些候选只作为 semantic recall 线索. 不覆盖 execution_gate.")

    return {
        "query_variants": query_variants,
        "variant_routes": variant_routes,
        "recall_candidates": [
            {
                **item,
                "aggregate_score": round(float(item["aggregate_score"]), 4),
            }
            for item in candidates
        ],
        "recommended_mode": recommended_mode,
        "recommended_action": recommended_action,
        "recommended_path": recommended.get("path", "") if recommended else "",
        "prompt_block": "\n".join(prompt_lines),
    }


def safe_text_excerpt(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    return compact_text(text)


def summarize_memory_hit(hit: dict[str, Any], *, repo_root: Path, home_root: Path) -> dict[str, Any]:
    source = str(hit.get("source", "project")).strip() or "project"
    base_root = repo_root if source == "project" else home_root
    candidate = repo_relative_to_absolute(base_root, str(hit.get("path", "")))
    excerpt = ""
    if candidate.exists():
        text = mt.read_text(candidate)
        _, body = mt.parse_frontmatter(text)
        excerpt = compact_text(body or text)
    return {
        "ref": hit.get("ref", ""),
        "path": hit.get("path", ""),
        "title": hit.get("title", ""),
        "doc_type": hit.get("doc_type", ""),
        "source": source,
        "score": hit.get("score", 0),
        "reasons": list(hit.get("reasons", []))[:3],
        "excerpt": excerpt,
    }


def summarize_asset_hit(hit: dict[str, Any], *, repo_root: Path, home_root: Path) -> dict[str, Any]:
    source = str(hit.get("source", "project")).strip() or "project"
    base_root = repo_root if source == "project" else home_root
    candidate = (base_root / str(hit.get("path", ""))).resolve()
    return {
        "ref": hit.get("ref", ""),
        "path": hit.get("path", ""),
        "title": hit.get("title", ""),
        "doc_type": hit.get("doc_type", ""),
        "asset_type": hit.get("asset_type", ""),
        "source": source,
        "score": hit.get("score", 0),
        "reasons": list(hit.get("reasons", []))[:3],
        "excerpt": safe_text_excerpt(candidate) if candidate.exists() else "",
    }


def bullet_block(title: str, items: list[str], *, empty_text: str) -> list[str]:
    lines = [f"- {title}:"]
    if not items:
        lines.append(f"  - {empty_text}")
        return lines
    lines.extend([f"  - {item}" for item in items])
    return lines


def build_working_memory_prompt(checkpoint: dict[str, Any]) -> str:
    lines = ["### [WORKING MEMORY]"]
    if not checkpoint.get("exists"):
        lines.append("- 暂无已记录 working memory.")
        return "\n".join(lines)

    lines.extend(bullet_block("key_facts", list(checkpoint.get("key_facts", [])), empty_text="暂无"))
    lines.extend(bullet_block("current_invariant", list(checkpoint.get("current_invariant", [])), empty_text="暂无"))
    lines.extend(bullet_block("verified_steps", list(checkpoint.get("verified_steps", [])), empty_text="暂无"))
    lines.extend(bullet_block("task_assets", list(checkpoint.get("task_assets", [])), empty_text="暂无"))
    lines.extend(bullet_block("reused_assets", list(checkpoint.get("reused_assets", [])), empty_text="暂无"))
    traces = checkpoint.get("retrieval_traces", [])
    latest = traces[-1] if traces and isinstance(traces[-1], dict) else {}
    if latest:
        lines.append("- latest_retrieval:")
        route_query = str(latest.get("route_query", "")).strip() or "暂无"
        selected_hit = str(latest.get("selected_hit", "")).strip() or "暂无"
        adopted_hit = str(latest.get("adopted_hit", "")).strip() or "暂无"
        surfaced_hits = list(latest.get("surfaced_hits", []))[:3]
        lines.append(f"  - route_query: {route_query}")
        if surfaced_hits:
            lines.append(f"  - surfaced_hits: {', '.join(surfaced_hits)}")
        lines.append(f"  - selected_hit: {selected_hit}")
        lines.append(f"  - adopted_hit: {adopted_hit}")
    return "\n".join(lines)


def build_long_term_promotion_prompt(promotions_payload: dict[str, Any]) -> str:
    lines = ["### [LONG-TERM PROMOTIONS]"]
    promotions = list(promotions_payload.get("promotions", []))
    if not promotions:
        lines.append("- 暂无已记录 long-term promotion.")
        return "\n".join(lines)
    for item in promotions[-3:]:
        title = str(item.get("title", "")).strip() or "未命名"
        doc_type = str(item.get("doc_type", "")).strip() or "unknown"
        summary = str(item.get("summary", "")).strip() or "暂无摘要"
        lines.append(f"- {title} [{doc_type}]: {summary}")
    return "\n".join(lines)


def build_agent_prompt(
    *,
    route_payload: dict[str, Any],
    working_prompt: str,
    long_term_prompt: str,
    memory_context: dict[str, Any],
    closeout_gate: dict[str, Any],
    hybrid_recall_prompt: str,
) -> str:
    lines = [
        "### [PROJECT MEMORY RECALL]",
        f"- task: {route_payload.get('query', '')}",
        f"- route_event_id: {route_payload.get('route_event_id', '') or 'n/a'}",
        f"- surfaced_hits_hash: {route_payload.get('surfaced_hits_hash', '') or 'n/a'}",
        f"- selected_path: {memory_context.get('selected_path', '') or 'n/a'}",
        "- primary_project_memory:",
    ]
    project_memory = memory_context.get("project_memory", [])
    if project_memory:
        for item in project_memory:
            lines.append(f"  - {item['path']}: {item['title'] or item['doc_type']}")
    else:
        lines.append("  - 暂无")

    if memory_context.get("project_assets"):
        lines.append("- project_assets:")
        for item in memory_context["project_assets"]:
            lines.append(f"  - {item['path']}: {item['title'] or item['asset_type']}")

    if memory_context.get("home_memory"):
        lines.append("- home_memory_overlay:")
        for item in memory_context["home_memory"]:
            lines.append(f"  - {item['path']}: {item['title'] or item['doc_type']}")

    lines.extend(
        [
            "### [EXECUTION GATE]",
            f"- state: {route_payload['execution_gate']['state']}",
            f"- prompt: {route_payload['execution_gate']['prompt']}",
            *[f"- required_closeout: {item}" for item in route_payload["execution_gate"].get("required_closeout", [])],
            hybrid_recall_prompt,
            working_prompt,
            long_term_prompt,
            "### [CLOSEOUT GATE]",
            f"- status: {closeout_gate.get('status', 'not_started')}",
            f"- prompt: {closeout_gate.get('prompt', '')}",
        ]
    )
    if route_payload.get("adoption_hint"):
        lines.append("### [ADOPTION HINT]")
        lines.append(route_payload["adoption_hint"])
    if route_payload.get("coverage_hint"):
        lines.append("### [COVERAGE HINT]")
        lines.append(route_payload["coverage_hint"])
    return "\n".join(lines)


def command_doctor(repo_root: Path, home_root: Path) -> dict[str, Any]:
    return {
        "tool": TOOL_NAME,
        "command_name": TOOL_NAME,
        "command_path": resolve_command_path(),
        "cwd": str(Path.cwd().resolve()),
        "repo_root": str(repo_root),
        "home_root": str(home_root),
        "project_memory_exists": project_memory_exists(repo_root),
        "home_memory_exists": home_memory_exists(home_root),
        "home_same_as_project": repo_root == home_root,
        "commands": ["d", "ov", "b", "g", "r", "i", "sx", "si", "f", "a", "q", "l4", "m", "k", "lp", "p", "u", "x", "s", "c", "n", "v"],
        "aliases": {
            "d": ["doctor"],
            "ov": ["overview"],
            "b": ["boot", "bootstrap"],
            "g": ["agent"],
            "r": ["route"],
            "i": ["inspect"],
            "sx": ["semantic-index"],
            "si": ["semantic-inspect"],
            "f": ["flush"],
            "a": ["asset", "assets", "sk", "skills"],
            "q": ["cap", "capability"],
            "l4": ["archive-session", "replay-session"],
            "m": ["maintain"],
            "k": ["checkpoint"],
            "lp": ["promote", "promotion"],
            "p": ["candidate", "propose"],
            "u": ["update"],
            "x": ["delete", "remove"],
            "s": ["sync", "sync-registry"],
            "c": ["check", "hygiene"],
            "n": ["new", "scaffold"],
            "v": ["verify"],
        },
        "default_route_mode": "project-first-home-overlay",
    }


def resolve_command_path() -> str:
    env_path = os.environ.get("CODEX_MEMO_COMMAND_PATH", "").strip()
    if env_path:
        return str(Path(env_path).expanduser().resolve())
    discovered = shutil.which(TOOL_NAME)
    if discovered:
        return str(Path(discovered).resolve())
    return str((Path.home() / ".local" / "bin" / TOOL_NAME).resolve())


def ensure_project_layer(repo_root: Path, command: str) -> None:
    if project_memory_exists(repo_root):
        return
    raise FileNotFoundError(
        f"Project memory layer not found for command '{command}': {repo_root / '.codex' / 'memory'}. "
        "Run 'codex-memo b' first."
    )


def command_overview(repo_root: Path, home_root: Path) -> dict[str, Any]:
    project = mt.command_overview(repo_root, max_must_read=4)
    payload: dict[str, Any] = {
        "repo_root": str(repo_root),
        "home_root": str(home_root),
        "project": project,
        "home_same_as_project": repo_root == home_root,
    }
    if home_is_distinct(repo_root, home_root):
        payload["home"] = mt.command_overview(home_root, max_must_read=4)
    else:
        payload["home"] = None
    return payload


def command_route(
    repo_root: Path,
    home_root: Path,
    task: str,
    top_k: int,
    *,
    extra_roots: list[Path] | None = None,
    record_event: bool = True,
) -> dict[str, Any]:
    lexical_top_k = max(top_k, LEXICAL_RECALL_TOP_N)
    project_payload = mt.command_route(repo_root, task=task, top_k=lexical_top_k, record_event=record_event)
    project_hits_full = summarize_hits(project_payload["hits"], source="project")
    project_memory_hits_full = summarize_hits(project_payload.get("memory_hits", []), source="project")
    project_asset_hits_full = summarize_hits(project_payload.get("asset_hits", []), source="project")
    home_hits: list[dict[str, Any]] = []
    home_memory_hits: list[dict[str, Any]] = []
    extra_hits: list[dict[str, Any]] = []
    home_fallback_context = False
    if home_is_distinct(repo_root, home_root):
        home_payload = mt.command_route(home_root, task=task, top_k=lexical_top_k, record_event=False)
        home_memory_hits = summarize_hits(home_payload.get("memory_hits", home_payload["hits"]), source="home")
        home_hits = home_memory_hits
        home_fallback_context = home_payload["fallback_context"]
    for extra_root in extra_roots or []:
        extra_payload = mt.command_route(extra_root, task=task, top_k=lexical_top_k, record_event=False)
        extra_source = f"extra:{extra_root.name}"
        extra_hits.extend(summarize_hits(extra_payload.get("memory_hits", extra_payload["hits"]), source=extra_source))
    merged_hits_full = merge_hits(project_hits_full, home_hits, top_k=lexical_top_k, extra_hits=extra_hits)
    fallback_context = project_payload["fallback_context"] and (home_fallback_context or not home_memory_hits)
    execution_gate = build_execution_gate(
        project_memory_hits=project_memory_hits_full,
        project_hits=project_hits_full,
        merged_hits=merged_hits_full,
        project_fallback_context=project_payload["fallback_context"],
        fallback_context=fallback_context,
    )
    semantic_candidates_payload = sidx.inspect_semantic_candidates(repo_root, task=task, top_k=SEMANTIC_RECALL_TOP_M)
    semantic_candidates = list(semantic_candidates_payload.get("candidates", []))
    merged_hits_full.extend(
        semantic_candidates_to_hits(
            semantic_candidates,
            existing_paths={str(item.get("path", "")).strip() for item in merged_hits_full},
        )
    )
    semantic_route = apply_semantic_rerank(
        repo_root=repo_root,
        task=task,
        lexical_hits=merged_hits_full,
        semantic_candidates=semantic_candidates,
        execution_gate=execution_gate,
    )
    selected_path = str(semantic_route.get("rerank_selected_path", "")).strip()
    if selected_path:
        selected_hit = next((item for item in merged_hits_full if item.get("path") == selected_path), None)
        if selected_hit is not None:
            rerank_state = str(semantic_route.get("rerank_selected_state", "")).strip() or execution_gate["state"]
            selected_ref = str(semantic_route.get("rerank_selected_ref", "")).strip() or hit_ref(selected_hit)
            required_closeout = ["adoption_evidence"] if rerank_state == "hit" else [
                "runbook",
                "benchmark_query",
                "adoption_evidence",
                "script_if_needed",
            ]
            execution_gate = {
                "state": rerank_state,
                "selected_ref": selected_ref,
                "selected_path": str(selected_hit.get("path", "")).strip(),
                "selected_title": str(selected_hit.get("title", "")).strip(),
                "selected_kind": str(selected_hit.get("kind", "")).strip(),
                "selected_source": str(selected_hit.get("source", "")).strip() or "project",
                "required_closeout": required_closeout,
                "prompt": (
                    f"已命中可执行记忆: {selected_hit.get('path', '')}. "
                    "本次按该记忆执行. 若偏离, 必须说明原因并在收尾补 adoption evidence."
                    if rerank_state == "hit"
                    else (
                        f"已命中参考项: {selected_hit.get('path', '')}. "
                        "该命中项可作为线索或参考, 但不计作可执行记忆. 收尾前必须补齐: runbook + benchmark query + adoption evidence, 需要时补 script."
                    )
                ),
            }
    route_event_id = project_payload.get("route_event_id", "")
    surfaced_hits_hash = project_payload.get("surfaced_hits_hash", "")
    adoption_hint = ""
    coverage_hint = ""
    if execution_gate["state"] == "hit" and route_event_id and surfaced_hits_hash:
        adoption_hint = (
            "If you used the executable hit, record adoption:\n"
            f"  codex-memo k --task \\<task> --route-query \\<query> --route-event-id {route_event_id} --surfaced-hits-hash {surfaced_hits_hash} "
            f"--selected-hit {execution_gate['selected_path']} --adopted-hit {execution_gate['selected_path']} --observed-actions \\<what> --evidence-paths \\<path1,path2>"
        )
    elif route_event_id and surfaced_hits_hash:
        coverage_hint = (
            "If this is a new reusable problem family, record coverage:\n"
            f"  codex-memo k --task \\<task> --route-query \\<query> --route-event-id {route_event_id} --surfaced-hits-hash {surfaced_hits_hash} "
            "--coverage-mode new_family --runbook-paths \\<runbook> --benchmark-queries \\<query1,query2> --coverage-evidence \\<path1,path2> --evidence-paths \\<path1,path2>"
        )

    project_hits = trim_hits(project_hits_full, limit=top_k)
    project_memory_hits = trim_hits(project_memory_hits_full, limit=top_k)
    project_asset_hits = trim_hits(project_asset_hits_full, limit=top_k)
    merged_hits = trim_hits(merged_hits_full, limit=max(top_k, 1))
    return {
        "query": task,
        "repo_root": str(repo_root),
        "home_root": str(home_root),
        "project_hits": project_hits,
        "project_memory_hits": project_memory_hits,
        "project_asset_hits": project_asset_hits,
        "home_hits": home_hits,
        "home_memory_hits": home_memory_hits,
        "extra_hits": extra_hits,
        "merged_hits": merged_hits,
        "project_fallback_context": project_payload["fallback_context"],
        "home_fallback_context": home_fallback_context,
        "fallback_context": fallback_context,
        "route_contract_version": 4,
        "route_event_id": route_event_id,
        "surfaced_hits_hash": surfaced_hits_hash,
        "adoption_hint": adoption_hint,
        "coverage_hint": coverage_hint,
        "lexical_reasons": semantic_route["lexical_reasons"],
        "semantic_reasons": semantic_route["semantic_reasons"],
        "rerank_reasons": semantic_route["rerank_reasons"],
        "gate_override_reason": semantic_route["gate_override_reason"],
        "semantic_mode": semantic_route["semantic_mode"],
        "semantic_model_used": semantic_route["semantic_model_used"],
        "semantic_cache_hit": semantic_route["semantic_cache_hit"],
        "rerank_candidates": semantic_route["rerank_candidates"],
        "rerank_skipped_reason": semantic_route["rerank_skipped_reason"],
        "semantic_trigger_reason": semantic_route["semantic_trigger_reason"],
        "execution_gate": execution_gate,
    }


def command_agent(repo_root: Path, home_root: Path, task: str, top_k: int, *, extra_roots: list[Path] | None = None) -> dict[str, Any]:
    route_payload = command_route(repo_root, home_root, task=task, top_k=top_k, extra_roots=extra_roots)
    checkpoint = rc.read_checkpoint(repo_root, task)
    promotions_payload = rc.read_promotions(repo_root, task)
    checkpoint["closeout_gate"] = build_closeout_gate(checkpoint)
    working_prompt = build_working_memory_prompt(checkpoint)
    long_term_prompt = build_long_term_promotion_prompt(promotions_payload)
    hybrid_recall = build_hybrid_recall(
        repo_root=repo_root,
        home_root=home_root,
        task=task,
        top_k=top_k,
        checkpoint=checkpoint,
        base_route_payload=route_payload,
        extra_roots=extra_roots,
    )
    memory_context = {
        "selected_path": route_payload["execution_gate"].get("selected_path", ""),
        "selected_ref": route_payload["execution_gate"].get("selected_ref", ""),
        "project_memory": [
            summarize_memory_hit(hit, repo_root=repo_root, home_root=home_root)
            for hit in route_payload.get("project_memory_hits", [])[:MEMORY_CONTEXT_LIMIT]
        ],
        "project_assets": [
            summarize_asset_hit(hit, repo_root=repo_root, home_root=home_root)
            for hit in route_payload.get("project_asset_hits", [])[:MEMORY_CONTEXT_LIMIT]
        ],
        "home_memory": [
            summarize_memory_hit(hit, repo_root=repo_root, home_root=home_root)
            for hit in route_payload.get("home_memory_hits", [])[:MEMORY_CONTEXT_LIMIT]
        ],
        "extra_memory": route_payload.get("extra_hits", [])[:MEMORY_CONTEXT_LIMIT],
    }
    return {
        "agent_context_version": AGENT_CONTEXT_VERSION,
        "task": task,
        "repo_root": str(repo_root),
        "home_root": str(home_root),
        "route": route_payload,
        "hybrid_recall": hybrid_recall,
        "working_memory": {
            "exists": checkpoint.get("exists", False),
            "key_facts": checkpoint.get("key_facts", []),
            "current_invariant": checkpoint.get("current_invariant", []),
            "verified_steps": checkpoint.get("verified_steps", []),
            "task_assets": checkpoint.get("task_assets", []),
            "reused_assets": checkpoint.get("reused_assets", []),
            "retrieval_traces": checkpoint.get("retrieval_traces", []),
            "closeout_gate": checkpoint["closeout_gate"],
            "prompt_block": working_prompt,
        },
        "long_term_memory": {
            "count": promotions_payload.get("count", 0),
            "promotions": promotions_payload.get("promotions", []),
            "prompt_block": long_term_prompt,
        },
        "memory_context": memory_context,
        "agent_prompt": build_agent_prompt(
            route_payload=route_payload,
            working_prompt=working_prompt,
            long_term_prompt=long_term_prompt,
            memory_context=memory_context,
            closeout_gate=checkpoint["closeout_gate"],
            hybrid_recall_prompt=hybrid_recall["prompt_block"],
        ),
    }


def resolve_note_path(raw_path: str, repo_root: Path, home_root: Path) -> tuple[Path, str]:
    source_hint, normalized_raw_path = normalize_hit_reference(raw_path)
    candidate = Path(normalized_raw_path)
    project_memory_root = mt.repo_memory_root(repo_root)
    home_memory_root = mt.repo_memory_root(home_root)
    allowed_roots: list[tuple[Path, str]] = [(project_memory_root, "project")]
    if home_is_distinct(repo_root, home_root):
        allowed_roots.append((home_memory_root, "home"))
    allowed_roots = [item for item in allowed_roots if item[1] == source_hint]

    def ensure_memory_note(path: Path) -> None:
        if path.suffix.lower() != ".md":
            raise FileNotFoundError(f"Path is not under project/home memory: {raw_path}")

    def strip_known_prefixes(path: Path) -> Path:
        parts = path.parts
        if len(parts) >= 2 and parts[0] == ".codex" and parts[1] == "memory":
            return Path(*parts[2:])
        if parts and parts[0] == "memory":
            return Path(*parts[1:])
        return path

    if candidate.is_absolute():
        resolved = candidate.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Memory note not found: {raw_path}")
        ensure_memory_note(resolved)
        for root, source in allowed_roots:
            if resolved.is_relative_to(root):
                return resolved, source
        raise FileNotFoundError(f"Memory note not under project/home memory: {raw_path}")

    relative_candidate = strip_known_prefixes(candidate)
    for root, source in allowed_roots:
        resolved = (root / relative_candidate).resolve()
        if resolved.exists() and resolved.is_relative_to(root):
            ensure_memory_note(resolved)
            return resolved, source

    existing_candidates = [(repo_root / candidate).resolve()]
    if home_is_distinct(repo_root, home_root):
        existing_candidates.append((home_root / candidate).resolve())
    for resolved in existing_candidates:
        if resolved.exists():
            raise FileNotFoundError(f"Path is not under project/home memory: {raw_path}")

    raise FileNotFoundError(f"Memory note not found: {raw_path}")


def inspect_note(candidate: Path, *, source: str, task: str, repo_root: Path, home_root: Path) -> dict[str, Any]:
    if source == "project":
        active_root = repo_root
    else:
        active_root = home_root
    memory_root = mt.repo_memory_root(active_root)
    origin_root = active_root

    text = mt.read_text(candidate)
    frontmatter, body = mt.parse_frontmatter(text)
    if candidate.is_relative_to(memory_root):
        rel_path = candidate.relative_to(memory_root).as_posix()
    else:
        rel_path = candidate.relative_to(origin_root).as_posix()

    note = mt.NoteRecord(path=candidate, rel_path=rel_path, frontmatter=frontmatter, body=body)
    excluded = mt.note_is_route_excluded(note)
    fallback_only = mt.note_is_fallback_only(note)
    eligible = mt.note_is_runtime_eligible(note)
    if excluded:
        reasons = ["excluded:file"]
        score = 0.0
    elif fallback_only:
        reasons = ["fallback_only:context"]
        score = 0.0
    elif frontmatter.get("status") != "active":
        reasons = [f"excluded:status={frontmatter.get('status')}"]
        score = 0.0
    else:
        notes = mt.scan_memory_notes(active_root)
        asset_payload = bai.read_asset_index(active_root) or bai.build_asset_index(active_root)
        assets = mt.scan_asset_records(active_root, asset_payload=asset_payload)
        idf_map = mt.build_query_idf(notes, assets, task)
        scored = mt.score_note_for_query(note, task, idf_map)
        reasons = scored["reasons"]
        score = scored["score"]

    return {
        "query": task,
        "source": source,
        "path": rel_path,
        "eligible": eligible,
        "fallback_only": fallback_only,
        "excluded": excluded,
        "score": score,
        "reasons": reasons,
    }


def command_boot(repo_root: Path) -> dict[str, Any]:
    module = load_bootstrap_module()
    return module.bootstrap_project_codex(repo_root)


def command_sync(repo_root: Path) -> dict[str, Any]:
    return mt.command_sync_registry(repo_root)


def command_check(repo_root: Path, stale_days: int) -> dict[str, Any]:
    return mt.command_hygiene(repo_root, stale_days=stale_days)


def build_governance_summary(repo_root: Path, *, asset_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = asset_payload or bai.build_asset_index(repo_root)
    notes = mt.scan_memory_notes(repo_root)
    canonical_notes = [
        note for note in notes
        if note.frontmatter.get("status") == "active" and note.frontmatter.get("canonical") is True
    ]
    thin_entries = [
        note for note in notes
        if note.frontmatter.get("status") == "active" and note.frontmatter.get("canonical") is False
    ]
    missing_aliases = [
        f"memory/{note.rel_path}"
        for note in canonical_notes
        if len(mt.normalize_list(note.frontmatter.get("aliases", []))) < 3
    ]
    missing_keywords = [
        f"memory/{note.rel_path}"
        for note in canonical_notes
        if len(mt.normalize_list(note.frontmatter.get("keywords", []))) < 3
    ]
    missing_triggers = [
        f"memory/{note.rel_path}"
        for note in canonical_notes
        if not mt.normalize_list(note.frontmatter.get("triggers", []))
    ]
    session_assets = payload.get("session_assets", [])
    active_sessions = [entry["path"] for entry in session_assets if "/.codex/sessions/" in f"/{entry.get('path', '')}"]
    archived_sessions = [entry["path"] for entry in session_assets if "/.codex/archived_sessions/" in f"/{entry.get('path', '')}"]
    recommended_actions: list[str] = []
    if missing_aliases:
        recommended_actions.append("fill_aliases")
    if missing_keywords:
        recommended_actions.append("fill_keywords")
    if missing_triggers:
        recommended_actions.append("fill_triggers")
    if archived_sessions:
        recommended_actions.append("review_archived_session_window")
    return {
        "canonical_notes": len(canonical_notes),
        "thin_entries": len(thin_entries),
        "counts_by_doc_type": {
            "runbook": sum(1 for note in canonical_notes if note.frontmatter.get("doc_type") == "runbook"),
            "decision": sum(1 for note in canonical_notes if note.frontmatter.get("doc_type") == "decision"),
            "pattern": sum(1 for note in canonical_notes if note.frontmatter.get("doc_type") == "pattern"),
            "postmortem": sum(1 for note in canonical_notes if note.frontmatter.get("doc_type") == "postmortem"),
        },
        "metadata_gaps": {
            "missing_aliases": missing_aliases,
            "missing_keywords": missing_keywords,
            "missing_triggers": missing_triggers,
        },
        "session_recall_window": {
            "active": len(active_sessions),
            "archived": len(archived_sessions),
            "total": len(session_assets),
        },
        "recommended_actions": recommended_actions,
    }


def command_new(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    verification_gate = require_memory_write_verification(
        repo_root,
        operation="create canonical memory",
        task=str(getattr(args, "task", "")).strip(),
        task_id=str(getattr(args, "task_id", "")).strip(),
        evidence_paths=mt.normalize_list(getattr(args, "evidence_paths", "")),
    )
    payload = mt.command_scaffold(
        repo_root=repo_root,
        doc_type=args.doc_type,
        slug=args.slug,
        title=args.title,
        tags=args.tags,
        triggers=args.triggers,
        keywords=args.keywords,
        when_to_read=args.when_to_read,
        canonical=args.canonical,
        aliases=args.aliases,
        force=args.force,
    )
    payload["verification_gate"] = verification_gate
    return payload


def command_asset(repo_root: Path) -> dict[str, Any]:
    output_path = bai.write_asset_index(repo_root)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    payload["output_path"] = str(output_path)
    return payload


def command_capability_search(repo_root: Path, *, task: str, top_k: int) -> dict[str, Any]:
    asset_payload = bai.read_asset_index(repo_root)
    if asset_payload is None:
        asset_payload = command_asset(repo_root)
    route_context = mt.get_route_context(repo_root)
    notes = [
        note
        for note in route_context.get("notes", [])
        if note.frontmatter.get("doc_type") in {"runbook", "pattern", "decision"} and mt.note_is_runtime_eligible(note)
    ]
    assets = [
        asset
        for asset in route_context.get("assets", [])
        if asset.asset_type in {"skill", "script", "executable"}
    ]
    insight_entries = list(asset_payload.get("insight_entries", []))

    results: list[dict[str, Any]] = []
    for note in notes:
        scored = mt.score_note_for_query(note, task)
        if float(scored.get("score", 0.0)) <= 0:
            continue
        note_path = str(scored.get("repo_path", "")).strip()
        if note_path.startswith(".codex/memory/"):
            note_path = "memory/" + note_path[len(".codex/memory/") :]
        results.append(
            {
                "capability_type": str(scored.get("doc_type", "")).strip(),
                "kind": "memory",
                "path": note_path,
                "title": str(scored.get("title", "")).strip(),
                "score": float(scored.get("score", 0.0)),
                "reasons": list(scored.get("reasons", [])),
            }
        )
    for asset in assets:
        scored = mt.score_asset_for_query(asset, task)
        if float(scored.get("score", 0.0)) <= 0:
            continue
        results.append(
            {
                "capability_type": str(scored.get("asset_type", "")).strip(),
                "kind": "asset",
                "path": str(scored.get("repo_path", "")).strip(),
                "title": str(scored.get("title", "")).strip(),
                "score": float(scored.get("score", 0.0)),
                "reasons": list(scored.get("reasons", [])),
            }
        )
    for entry in insight_entries:
        scored = mt.score_insight_for_query(entry, task)
        if float(scored.get("score", 0.0)) <= 0:
            continue
        results.append(
            {
                "capability_type": "insight",
                "kind": str(scored.get("kind", "")).strip() or "memory",
                "path": str(scored.get("pointer", "")).strip(),
                "title": str(entry.get("title", "")).strip(),
                "score": float(scored.get("score", 0.0)),
                "reasons": list(scored.get("reasons", [])),
                "source": str(scored.get("source", "")).strip(),
            }
        )
    results.sort(key=lambda item: (-float(item.get("score", 0.0)), str(item.get("capability_type", "")), str(item.get("path", ""))))
    trimmed = results[: max(top_k, 1)]
    counts_by_type: dict[str, int] = {}
    for item in trimmed:
        key = str(item.get("capability_type", "")).strip() or "unknown"
        counts_by_type[key] = counts_by_type.get(key, 0) + 1
    output_path = bai.asset_index_path(repo_root)
    return {
        "query": task,
        "repo_root": str(repo_root),
        "output_path": str(output_path),
        "capability_hits": trimmed,
        "counts_by_type": counts_by_type,
    }


def command_l4(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    if args.closeout or args.source_path.strip():
        if args.closeout and args.source_path.strip():
            raise ValueError("choose either --closeout or --source-path, not both")
        source_path = Path(args.source_path) if args.source_path.strip() else sa.latest_active_session_file(repo_root)
        if source_path is None:
            raise ValueError("no active session file found for closeout archive")
        payload = sa.archive_session(
            repo_root,
            source_path=source_path,
            task=args.task,
            reason="closeout" if args.closeout else "manual",
        )
        payload["mode"] = "archive"
        return payload

    if args.session_id.strip():
        session_path = sa.find_session_file(repo_root, args.session_id, include_active=True)
        if session_path is None:
            raise ValueError("session_id not found")
        payload = sa.replay_session(repo_root, session_path)
        payload["mode"] = "replay"
        payload["query"] = ""
        return payload

    if args.query.strip():
        assets = [
            entry
            for entry in sa.discover_session_assets(repo_root)
            if str(entry.get("asset_type", "")).strip() == "archived_session"
        ]
        ranked: list[dict[str, Any]] = []
        for entry in assets:
            rel_path = str(entry.get("path", "")).strip()
            if not rel_path:
                continue
            scored = mt.score_asset_for_query(
                mt.AssetRecord(
                    path=(repo_root / rel_path).resolve(),
                    rel_path=rel_path,
                    asset_type="archived_session",
                    name=str(entry.get("name", "")).strip(),
                    description=str(entry.get("description", "")).strip(),
                ),
                args.query,
            )
            if float(scored.get("score", 0.0)) <= 0:
                continue
            replay_payload = sa.replay_session(repo_root, repo_root / rel_path)
            ranked.append(
                {
                    "session_id": replay_payload["session_id"],
                    "path": replay_payload["path"],
                    "score": float(scored.get("score", 0.0)),
                    "reasons": list(scored.get("reasons", [])),
                    "snippets": replay_payload["snippets"],
                    "messages": replay_payload["messages"],
                    "archived": True,
                }
            )
        ranked.sort(key=lambda item: (-float(item.get("score", 0.0)), str(item.get("path", ""))))
        return {
            "mode": "replay",
            "query": args.query,
            "matches": ranked[: max(args.top_k, 1)],
        }

    raise ValueError("l4 requires one of: --closeout, --source-path, --session-id, or --query")


def command_semantic_index(repo_root: Path, *, force: bool = False) -> dict[str, Any]:
    payload = sidx.build_semantic_index(repo_root, force=force)
    payload["repo_root"] = str(repo_root)
    return payload


def command_semantic_inspect(repo_root: Path, *, task: str, top_k: int) -> dict[str, Any]:
    payload = sidx.inspect_semantic_candidates(repo_root, task=task, top_k=top_k)
    payload["repo_root"] = str(repo_root)
    return payload


def command_maintain(repo_root: Path, stale_days: int) -> dict[str, Any]:
    asset_payload = command_asset(repo_root)
    sync_payload = command_sync(repo_root)
    hygiene_payload = command_check(repo_root, stale_days=stale_days)
    return {
        "repo_root": str(repo_root),
        "asset_index": {
            "output_path": asset_payload["output_path"],
            "counts": asset_payload["counts"],
        },
        "sync": sync_payload,
        "hygiene": hygiene_payload,
        "governance_summary": build_governance_summary(repo_root, asset_payload=asset_payload),
    }


def checkpoint_write_evidence(checkpoint: dict[str, Any]) -> tuple[bool, list[str]]:
    evidence_paths: list[str] = []
    evidence_paths.extend(list(checkpoint.get("task_assets", [])))
    for trace in list(checkpoint.get("retrieval_traces", [])):
        if not isinstance(trace, dict):
            continue
        evidence_paths.extend(list(trace.get("evidence_paths", [])))
    ledger = dict(checkpoint.get("closeout_ledger", {}))
    evidence_paths.extend(list(ledger.get("coverage_evidence", [])))
    evidence_paths.extend(list(ledger.get("script_paths", [])))
    has_execution_evidence = bool(checkpoint.get("verified_steps")) or bool(evidence_paths)
    return has_execution_evidence, mt.normalize_list(evidence_paths)


def require_memory_write_verification(
    repo_root: Path,
    *,
    operation: str,
    task: str,
    task_id: str,
    evidence_paths: list[str],
) -> dict[str, Any]:
    normalized_input_paths = [rl.normalize_target_path(repo_root, item) for item in evidence_paths]
    if normalized_input_paths:
        ensure_repo_paths_exist(repo_root, normalized_input_paths, field_name="evidence_paths")
    sources: list[str] = []
    merged_evidence: list[str] = list(normalized_input_paths)
    checkpoint_summary: dict[str, Any] | None = None
    sidecar_summary: dict[str, Any] | None = None
    blockers: list[str] = []

    if task:
        checkpoint = rc.read_checkpoint(repo_root, task)
        if checkpoint.get("exists"):
            has_checkpoint_evidence, checkpoint_paths = checkpoint_write_evidence(checkpoint)
            checkpoint_summary = {
                "task": task,
                "verified_steps": list(checkpoint.get("verified_steps", [])),
                "evidence_paths": checkpoint_paths,
            }
            if has_checkpoint_evidence:
                sources.append("checkpoint")
                merged_evidence.extend(checkpoint_paths)
            else:
                blockers.append("working checkpoint has no verified_steps or evidence_paths")
        else:
            blockers.append("working checkpoint not found")

    if task_id:
        try:
            sidecar = vs.read_sidecar(repo_root, task_id)
        except FileNotFoundError:
            blockers.append("verifier sidecar not found")
        else:
            verify_context = dict(sidecar.get("verify_context", {}))
            sidecar_paths = [rl.normalize_target_path(repo_root, item) for item in list(verify_context.get("evidence_paths", []))]
            if sidecar_paths:
                ensure_repo_paths_exist(repo_root, sidecar_paths, field_name="verify_context.evidence_paths")
                sources.append("verifier_sidecar")
                merged_evidence.extend(sidecar_paths)
            else:
                blockers.append("verifier sidecar has no evidence_paths")
            sidecar_summary = {
                "task_id": task_id,
                "evidence_paths": sidecar_paths,
                "required_checks": list(verify_context.get("required_checks", [])),
            }

    merged_evidence = mt.normalize_list(merged_evidence)
    if not sources:
        if not task and not task_id:
            raise ValueError(f"{operation} requires --task with a verified checkpoint or --task-id with a verifier sidecar")
        blocker_text = "; ".join(blockers) if blockers else "verification evidence missing"
        raise ValueError(f"{operation} requires execution-backed verification before writing canonical memory: {blocker_text}")

    return {
        "status": "passed",
        "operation": operation,
        "sources": sources,
        "task": task,
        "task_id": task_id,
        "evidence_paths": merged_evidence,
        "checkpoint": checkpoint_summary,
        "verifier_sidecar": sidecar_summary,
    }


def command_checkpoint(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    key_facts = mt.normalize_list(args.key_facts)
    task_assets = mt.normalize_list(args.task_assets or args.related_assets)
    current_invariant = mt.normalize_list(args.current_invariant)
    verified_steps = mt.normalize_list(args.verified_steps)
    route_query = args.route_query.strip()
    route_event_id = args.route_event_id.strip()
    surfaced_hits_hash = args.surfaced_hits_hash.strip()
    surfaced_hits = [rl.normalize_target_path(repo_root, item) for item in mt.normalize_list(args.surfaced_hits)]
    selected_source, selected_hit_raw = normalize_hit_reference(args.selected_hit) if args.selected_hit.strip() else ("project", "")
    adopted_source, adopted_hit_raw = normalize_hit_reference(args.adopted_hit) if args.adopted_hit.strip() else ("project", "")
    selected_hit = rl.normalize_target_path(repo_root, selected_hit_raw) if selected_hit_raw else ""
    adopted_hit = rl.normalize_target_path(repo_root, adopted_hit_raw) if adopted_hit_raw else ""
    observed_actions = mt.normalize_list(args.observed_actions)
    evidence_paths = [rl.normalize_target_path(repo_root, item) for item in mt.normalize_list(args.evidence_paths)]
    coverage_mode = args.coverage_mode.strip()
    runbook_paths = [rl.normalize_target_path(repo_root, item) for item in mt.normalize_list(args.runbook_paths)]
    benchmark_queries = mt.normalize_list(args.benchmark_queries)
    script_paths = [rl.normalize_target_path(repo_root, item) for item in mt.normalize_list(args.script_paths)]
    coverage_evidence = [rl.normalize_target_path(repo_root, item) for item in mt.normalize_list(args.coverage_evidence)]
    corrections = normalize_corrections(args.correction)

    if route_query or selected_hit or adopted_hit or observed_actions or evidence_paths or coverage_mode or runbook_paths or benchmark_queries or script_paths or coverage_evidence or corrections:
        if not route_query:
            raise ValueError("route_query is required when recording retrieval adoption evidence")
        if not route_event_id:
            raise ValueError("route_event_id is required when recording retrieval evidence")
        event = rl.latest_route_event(repo_root, event_id=route_event_id)
        if event is None:
            raise ValueError("route_event_id not found")
        if event.get("normalized_query") != rl.normalize_query(route_query):
            raise ValueError("route_event_id does not match route_query")
        event_hits = [rl.normalize_target_path(repo_root, item) for item in rl.event_hits(event)]
        event_hits_hash = str(event.get("hits_hash", "")).strip() or rl.surfaced_hits_hash(event_hits)
        if surfaced_hits_hash and surfaced_hits_hash != event_hits_hash:
            raise ValueError("surfaced_hits_hash does not match route_event")
        surfaced_hits_hash = event_hits_hash
        if surfaced_hits:
            if surfaced_hits != event_hits:
                raise ValueError("surfaced_hits must exactly match the recorded route event")
        else:
            surfaced_hits = event_hits
        if selected_source == "home" or adopted_source == "home":
            raise ValueError("selected_hit and adopted_hit must come from project route hits")
        if (selected_hit or adopted_hit) and not surfaced_hits:
            raise ValueError("No surfaced hits available for this route_query; run `codex-memo r` first or pass --surfaced-hits")
        if selected_hit and selected_hit not in surfaced_hits:
            raise ValueError("selected_hit must come from surfaced hits")
        if adopted_hit and adopted_hit not in surfaced_hits:
            raise ValueError("adopted_hit must come from surfaced hits")
        if adopted_hit and not selected_hit:
            raise ValueError("selected_hit is required when recording adopted_hit")
        if adopted_hit and not observed_actions:
            raise ValueError("adopted_hit requires observed_actions")
        if adopted_hit and not evidence_paths:
            raise ValueError("adopted_hit requires evidence_paths")
        if evidence_paths:
            ensure_repo_paths_exist(repo_root, evidence_paths, field_name="evidence_paths")
        if coverage_mode and coverage_mode != "new_family":
            raise ValueError("coverage_mode must be 'new_family'")
        if coverage_mode == "new_family":
            if selected_hit or adopted_hit:
                raise ValueError("new_family coverage cannot also record selected_hit/adopted_hit")
            if not runbook_paths or not benchmark_queries or not coverage_evidence:
                raise ValueError("new_family coverage requires runbook_paths, benchmark_queries, and coverage_evidence")
            ensure_repo_paths_exist(repo_root, runbook_paths, field_name="runbook_paths")
            ensure_repo_paths_exist(repo_root, coverage_evidence, field_name="coverage_evidence")
        if script_paths:
            ensure_repo_paths_exist(repo_root, script_paths, field_name="script_paths")

    if key_facts or task_assets or current_invariant or verified_steps or route_query:
        payload = rc.upsert_checkpoint(
            repo_root,
            task=args.task,
            key_facts=key_facts,
            task_assets=task_assets,
            reused_assets=[],
            current_invariant=current_invariant,
            verified_steps=verified_steps,
            route_query=route_query,
            route_event_id=route_event_id,
            surfaced_hits_hash=surfaced_hits_hash,
            surfaced_hits=surfaced_hits,
            selected_hit=selected_hit,
            adopted_hit=adopted_hit,
            observed_actions=observed_actions,
            evidence_paths=evidence_paths,
            coverage_mode=coverage_mode,
            runbook_paths=runbook_paths,
            benchmark_queries=benchmark_queries,
            script_paths=script_paths,
            coverage_evidence=coverage_evidence,
            corrections=corrections,
        )
        if adopted_hit:
            payload["adoption_learning"] = rl.record_success(
                repo_root,
                query=route_query,
                target_paths=[adopted_hit],
                source="adoption",
                event_key=f"{route_event_id}:{adopted_hit}",
            )
    else:
        payload = rc.read_checkpoint(repo_root, args.task)
    payload["checkpoint_path"] = str(rc.checkpoint_path(repo_root).relative_to(repo_root))
    payload["closeout_gate"] = build_closeout_gate(payload)
    return payload


def command_promotion(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    evidence_paths = [rl.normalize_target_path(repo_root, item) for item in mt.normalize_list(args.evidence_paths)]
    if args.promotion_id.strip():
        payload = rc.read_promotion(repo_root, task=args.task, promotion_id=args.promotion_id)
    elif any([args.title.strip(), args.summary.strip(), args.doc_type.strip(), evidence_paths]):
        if not args.title.strip() or not args.summary.strip() or not args.doc_type.strip():
            raise ValueError("title, summary, and doc_type are required when creating a promotion")
        if args.doc_type not in PROMOTION_DOC_TYPES:
            raise ValueError(f"doc_type must be one of: {', '.join(PROMOTION_DOC_TYPES)}")
        ensure_repo_paths_exist(repo_root, evidence_paths, field_name="evidence_paths")
        payload = rc.create_promotion(
            repo_root,
            task=args.task,
            title=args.title,
            summary=args.summary,
            doc_type=args.doc_type,
            evidence_paths=evidence_paths,
        )
    else:
        payload = rc.read_promotions(repo_root, args.task)
    payload["checkpoint_path"] = str(rc.checkpoint_path(repo_root).relative_to(repo_root))
    return payload


def command_candidate(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    source_paths = mt.normalize_list(args.source_paths)
    related_assets = mt.normalize_list(args.related_assets)
    candidate = pc.create_candidate(
        repo_root,
        task_summary=args.task_summary,
        candidate_type=args.candidate_type,
        title=args.title,
        summary=args.summary,
        source_paths=source_paths,
        related_assets=related_assets,
        event_ids=mt.normalize_list(args.event_ids),
        capsule_id=args.capsule_id,
        validation_mode=args.validation_mode,
        tests_passed=None if args.tests_passed is None else args.tests_passed == "true",
        user_confirmed=None if args.user_confirmed is None else args.user_confirmed == "true",
    )
    return {
        "candidate": candidate,
        "candidate_path": str(pc.candidates_path(repo_root).relative_to(repo_root)),
        "learning": None,
    }


def command_update(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    verification_gate = require_memory_write_verification(
        repo_root,
        operation="update canonical memory",
        task=str(getattr(args, "task", "")).strip(),
        task_id=str(getattr(args, "task_id", "")).strip(),
        evidence_paths=mt.normalize_list(getattr(args, "evidence_paths", "")),
    )
    payload = mt.command_update(
        repo_root,
        path=args.path,
        title=args.title,
        tags=args.tags,
        triggers=args.triggers,
        keywords=args.keywords,
        when_to_read=args.when_to_read,
        aliases=args.aliases,
        confidence=args.confidence,
        status=args.status,
        canonical=args.canonical,
        body_append=args.body_append,
    )
    payload["verification_gate"] = verification_gate
    payload["sync_registry"] = command_sync(repo_root)
    payload["asset_index"] = {
        "output_path": command_asset(repo_root)["output_path"],
    }
    return payload


def command_delete(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    payload = mt.command_delete(
        repo_root,
        path=args.path,
    )
    payload["semantic_index"] = {
        "removed": sidx.drop_semantic_note(repo_root, path=payload["route_path"]),
        "storage_backend": "sqlite",
    }
    payload["sync_registry"] = command_sync(repo_root)
    payload["asset_index"] = {
        "output_path": command_asset(repo_root)["output_path"],
    }
    return payload


def command_verify(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    deliverables = mt.normalize_list(args.deliverables)
    required_checks = mt.normalize_list(args.required_checks)
    evidence_paths = mt.normalize_list(args.evidence_paths)
    if args.task_summary.strip() or deliverables or required_checks or evidence_paths:
        return vs.upsert_sidecar(
            repo_root,
            task_id=args.task_id,
            task_summary=args.task_summary,
            deliverables=deliverables,
            required_checks=required_checks,
            evidence_paths=evidence_paths,
        )
    try:
        return vs.read_sidecar(repo_root, args.task_id)
    except FileNotFoundError as exc:
        raise ValueError("task_summary is required when creating a verifier sidecar") from exc


def normalize_command(command: str) -> str:
    aliases = {
        "doctor": "d",
        "overview": "ov",
        "boot": "b",
        "bootstrap": "b",
        "agent": "g",
        "route": "r",
        "inspect": "i",
        "semantic-index": "sx",
        "semantic-inspect": "si",
        "flush": "f",
        "asset": "a",
        "assets": "a",
        "sk": "a",
        "skills": "a",
        "maintain": "m",
        "cap": "q",
        "capability": "q",
        "l4": "l4",
        "archive-session": "l4",
        "replay-session": "l4",
        "checkpoint": "k",
        "promote": "lp",
        "promotion": "lp",
        "candidate": "p",
        "propose": "p",
        "update": "u",
        "delete": "x",
        "remove": "x",
        "sync": "s",
        "sync-registry": "s",
        "check": "c",
        "hygiene": "c",
        "new": "n",
        "scaffold": "n",
        "verify": "v",
    }
    return aliases.get(command, command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-memo")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("d", aliases=["doctor"], help="Report repo/home memory roots and availability.")
    sub.add_parser("ov", aliases=["overview"], help="Return project overview plus home overlay overview.")

    boot = sub.add_parser("b", aliases=["boot", "bootstrap"], help="Bootstrap project memory layer and AGENTS blocks.")
    boot.add_argument("--force", action="store_true", help="Reserved for forward compatibility.")

    agent = sub.add_parser("g", aliases=["agent"], help="Build GPT-5.4 agent loop context from route + working memory.")
    agent.add_argument("--task", required=True)
    agent.add_argument("--top-k", type=positive_int, default=3)
    agent.add_argument("--extra-roots", default="")

    route = sub.add_parser("r", aliases=["route"], help="Route a task across project memory and home memory.")
    route.add_argument("--task", required=True)
    route.add_argument("--top-k", type=positive_int, default=3)
    route.add_argument("--extra-roots", default="")

    inspect = sub.add_parser("i", aliases=["inspect"], help="Inspect how one note matches a task summary.")
    inspect.add_argument("--task", required=True)
    inspect.add_argument("--path", required=True)

    semantic_index = sub.add_parser("sx", aliases=["semantic-index"], help="Build or refresh semantic retrieval cache.")
    semantic_index.add_argument("--force", action="store_true")

    semantic_inspect = sub.add_parser("si", aliases=["semantic-inspect"], help="Inspect semantic candidates from cached semantic index.")
    semantic_inspect.add_argument("--task", required=True)
    semantic_inspect.add_argument("--top-k", type=positive_int, default=5)

    flush = sub.add_parser("f", aliases=["flush"], help="Flush project memory only.")
    flush.add_argument("--doc-type", choices=sorted(mt.TEMPLATE_DIRS))
    flush.add_argument("--slug")
    flush.add_argument("--title")
    flush.add_argument("--tags", default="")
    flush.add_argument("--triggers", default="")
    flush.add_argument("--keywords", default="")
    flush.add_argument("--when-to-read", default="")
    flush.add_argument("--aliases", default="", help="Semicolon-separated aliases for the note")
    flush.add_argument("--canonical", choices=["true", "false"], default=None)
    flush.add_argument("--task", default="")
    flush.add_argument("--task-id", default="")
    flush.add_argument("--evidence-paths", default="")
    flush.add_argument("--stale-days", type=int, default=45)
    flush.add_argument("--force", action="store_true")

    sub.add_parser("a", aliases=["asset", "assets", "sk", "skills"], help="Build the local asset index JSON.")

    capability = sub.add_parser("q", aliases=["cap", "capability"], help="Search local capabilities across skills, scripts, runbooks, executables, and insights.")
    capability.add_argument("--task", required=True)
    capability.add_argument("--top-k", type=positive_int, default=5)

    l4 = sub.add_parser("l4", aliases=["archive-session", "replay-session"], help="Archive raw sessions into L4 or replay archived sessions on demand.")
    l4.add_argument("--task", default="")
    l4.add_argument("--closeout", action="store_true")
    l4.add_argument("--source-path", default="")
    l4.add_argument("--session-id", default="")
    l4.add_argument("--query", default="")
    l4.add_argument("--top-k", type=positive_int, default=3)

    maintain = sub.add_parser("m", aliases=["maintain"], help="Run the default governance maintenance loop.")
    maintain.add_argument("--stale-days", type=int, default=45)

    checkpoint = sub.add_parser("k", aliases=["checkpoint"], help="Read or update the runtime checkpoint for one task.")
    checkpoint.add_argument("--task", required=True)
    checkpoint.add_argument("--key-facts", default="")
    checkpoint.add_argument("--task-assets", default="")
    checkpoint.add_argument("--related-assets", default="")
    checkpoint.add_argument("--current-invariant", default="")
    checkpoint.add_argument("--verified-steps", default="")
    checkpoint.add_argument("--route-query", default="")
    checkpoint.add_argument("--route-event-id", default="")
    checkpoint.add_argument("--surfaced-hits-hash", default="")
    checkpoint.add_argument("--surfaced-hits", default="")
    checkpoint.add_argument("--selected-hit", default="")
    checkpoint.add_argument("--adopted-hit", default="")
    checkpoint.add_argument("--observed-actions", default="")
    checkpoint.add_argument("--evidence-paths", default="")
    checkpoint.add_argument("--coverage-mode", default="")
    checkpoint.add_argument("--runbook-paths", default="")
    checkpoint.add_argument("--benchmark-queries", default="")
    checkpoint.add_argument("--script-paths", default="")
    checkpoint.add_argument("--coverage-evidence", default="")
    checkpoint.add_argument("--correction", default="")

    promotion = sub.add_parser("lp", aliases=["promote", "promotion"], help="Read or create long-term promotions derived from one working checkpoint.")
    promotion.add_argument("--task", required=True)
    promotion.add_argument("--promotion-id", default="")
    promotion.add_argument("--title", default="")
    promotion.add_argument("--summary", default="")
    promotion.add_argument("--doc-type", choices=sorted(PROMOTION_DOC_TYPES), default="")
    promotion.add_argument("--evidence-paths", default="")

    candidate = sub.add_parser("p", aliases=["candidate", "propose"], help="Create a procedural memory candidate without touching canonical memory.")
    candidate.add_argument("--task-summary", required=True)
    candidate.add_argument("--type", dest="candidate_type", choices=sorted(pc.ALLOWED_TYPES), required=True)
    candidate.add_argument("--title", required=True)
    candidate.add_argument("--summary", required=True)
    candidate.add_argument("--source-paths", default="")
    candidate.add_argument("--related-assets", default="")
    candidate.add_argument("--event-ids", default="")
    candidate.add_argument("--capsule-id", default="")
    candidate.add_argument("--validation-mode", default="")
    candidate.add_argument("--tests-passed", choices=["true", "false"], default=None)
    candidate.add_argument("--user-confirmed", choices=["true", "false"], default=None)

    update = sub.add_parser("u", aliases=["update"], help="Update one canonical memory note and refresh registry plus asset index.")
    update.add_argument("--path", required=True)
    update.add_argument("--title", default=None)
    update.add_argument("--tags", default=None)
    update.add_argument("--triggers", default=None)
    update.add_argument("--keywords", default=None)
    update.add_argument("--when-to-read", default=None)
    update.add_argument("--aliases", default=None)
    update.add_argument("--confidence", default=None)
    update.add_argument("--status", default=None)
    update.add_argument("--canonical", choices=["true", "false"], default=None)
    update.add_argument("--body-append", default=None)
    update.add_argument("--task", default="")
    update.add_argument("--task-id", default="")
    update.add_argument("--evidence-paths", default="")

    delete = sub.add_parser("x", aliases=["delete", "remove"], help="Delete one canonical memory note and refresh registry plus asset index.")
    delete.add_argument("--path", required=True)

    sync = sub.add_parser("s", aliases=["sync", "sync-registry"], help="Rebuild the project memory registry.")
    sync.add_argument("--force", action="store_true", help="Reserved for forward compatibility.")

    check = sub.add_parser("c", aliases=["check", "hygiene"], help="Run memory hygiene checks for the project.")
    check.add_argument("--stale-days", type=int, default=45)

    new = sub.add_parser("n", aliases=["new", "scaffold"], help="Create a new memory note from the matching template.")
    new.add_argument("--type", dest="doc_type", choices=sorted(mt.TEMPLATE_DIRS), required=True)
    new.add_argument("--slug", required=True)
    new.add_argument("--title", required=True)
    new.add_argument("--tags", default="")
    new.add_argument("--triggers", default="")
    new.add_argument("--keywords", default="")
    new.add_argument("--when-to-read", default="")
    new.add_argument("--aliases", default="", help="Semicolon-separated aliases for the note")
    new.add_argument("--canonical", choices=["true", "false"], default=None)
    new.add_argument("--task", default="")
    new.add_argument("--task-id", default="")
    new.add_argument("--evidence-paths", default="")
    new.add_argument("--force", action="store_true")

    verify = sub.add_parser("v", aliases=["verify"], help="Read or scaffold the task-scoped verifier sidecar under .codex/tasks/<task-id>/verify/.")
    verify.add_argument("--task-id", required=True)
    verify.add_argument("--task-summary", default="")
    verify.add_argument("--deliverables", default="")
    verify.add_argument("--required-checks", default="")
    verify.add_argument("--evidence-paths", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.command = normalize_command(args.command)
    repo_root = infer_repo_root(Path.cwd())
    home_root = resolve_home_root()
    extra_roots = resolve_extra_roots(repo_root, home_root, getattr(args, "extra_roots", ""))

    try:
        if args.command == "d":
            emit_json(command_doctor(repo_root, home_root))
            return 0

        if args.command != "b":
            ensure_project_layer(repo_root, args.command)

        if args.command == "ov":
            emit_json(command_overview(repo_root, home_root))
            return 0

        if args.command == "b":
            emit_json(command_boot(repo_root))
            return 0

        if args.command == "g":
            emit_json(
                command_agent(
                    repo_root,
                    home_root,
                    task=args.task,
                    top_k=args.top_k,
                    extra_roots=extra_roots,
                )
            )
            return 0

        if args.command == "r":
            emit_json(
                command_route(
                    repo_root,
                    home_root,
                    task=args.task,
                    top_k=args.top_k,
                    extra_roots=extra_roots,
                )
            )
            return 0

        if args.command == "i":
            candidate, source = resolve_note_path(args.path, repo_root, home_root)
            emit_json(inspect_note(candidate, source=source, task=args.task, repo_root=repo_root, home_root=home_root))
            return 0

        if args.command == "sx":
            emit_json(command_semantic_index(repo_root, force=getattr(args, "force", False)))
            return 0

        if args.command == "si":
            emit_json(command_semantic_inspect(repo_root, task=args.task, top_k=args.top_k))
            return 0

        if args.command == "f":
            verification_gate = None
            if args.doc_type or args.slug or args.title:
                verification_gate = require_memory_write_verification(
                    repo_root,
                    operation="flush canonical memory",
                    task=str(getattr(args, "task", "")).strip(),
                    task_id=str(getattr(args, "task_id", "")).strip(),
                    evidence_paths=mt.normalize_list(getattr(args, "evidence_paths", "")),
                )
            payload = mt.command_flush(args, repo_root)
            if verification_gate is not None:
                payload["verification_gate"] = verification_gate
            if (payload.get("scaffold") or {}).get("created"):
                payload["asset_index"] = {
                    "output_path": command_asset(repo_root)["output_path"],
                }
            emit_json(payload)
            return 0 if payload["hygiene"]["issue_count"] == 0 else 1

        if args.command == "a":
            emit_json(command_asset(repo_root))
            return 0

        if args.command == "q":
            emit_json(command_capability_search(repo_root, task=args.task, top_k=args.top_k))
            return 0

        if args.command == "l4":
            emit_json(command_l4(args, repo_root))
            return 0

        if args.command == "m":
            payload = command_maintain(repo_root, stale_days=args.stale_days)
            emit_json(payload)
            return 0 if payload["hygiene"]["issue_count"] == 0 else 1

        if args.command == "k":
            payload = command_checkpoint(args, repo_root)
            if args.coverage_mode.strip() == "new_family" or mt.normalize_list(args.runbook_paths):
                payload["sync_registry"] = command_sync(repo_root)
            emit_json(payload)
            return 0

        if args.command == "lp":
            emit_json(command_promotion(args, repo_root))
            return 0

        if args.command == "p":
            emit_json(command_candidate(args, repo_root))
            return 0

        if args.command == "u":
            emit_json(command_update(args, repo_root))
            return 0

        if args.command == "x":
            emit_json(command_delete(args, repo_root))
            return 0

        if args.command == "s":
            emit_json(command_sync(repo_root))
            return 0

        if args.command == "c":
            payload = command_check(repo_root, stale_days=args.stale_days)
            emit_json(payload)
            return 0 if payload["issue_count"] == 0 else 1

        if args.command == "n":
            emit_json(command_new(args, repo_root))
            return 0

        if args.command == "v":
            emit_json(command_verify(args, repo_root))
            return 0
    except Exception as exc:
        return fail(args.command, exc)

    return 1


if __name__ == "__main__":
    sys.exit(main())
