#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
LIB_DIR = SCRIPT_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import memory_tool as mt
import codex_memo
import reuse_learning as rl
import runtime_checkpoint as rc


BUNDLED_FIXTURE_MEMORY_ROOT = Path("examples/benchmark-fixture/memory")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Codex memory retrieval.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--cases", required=True)
    return parser.parse_args()


def _match_hit(hit: dict[str, Any], matcher: dict[str, Any]) -> bool:
    for key, expected in matcher.items():
        if key == "path_contains":
            if str(expected) not in str(hit.get("path", "")):
                return False
        elif key == "title_contains":
            if str(expected) not in str(hit.get("title", "")):
                return False
        else:
            if hit.get(key) != expected:
                return False
    return True


def _is_case_hit(hits: list[dict[str, Any]], case: dict[str, Any], *, top_n: int) -> bool:
    for hit in hits[:top_n]:
        for matcher in case.get("expected_any", []):
            if _match_hit(hit, matcher):
                return True
    return False


def _legacy_route(repo_root: Path, query: str, top_k: int) -> dict[str, Any]:
    notes = mt.scan_memory_notes(repo_root)
    assets = [asset for asset in mt.scan_asset_records(repo_root) if asset.asset_type != "session"]
    ranked_notes: list[dict[str, Any]] = []
    ranked_assets: list[dict[str, Any]] = []
    for note in notes:
        if not mt.note_is_runtime_eligible(note):
            continue
        result = mt.score_note_for_query(note, query)
        if result["score"] > 0:
            ranked_notes.append(result)
    for asset in assets:
        result = mt.score_asset_for_query(asset, query)
        if result["score"] > 0:
            ranked_assets.append(result)
    ranked_notes.sort(key=lambda item: (-item["score"], item["path"]))
    ranked_assets.sort(key=lambda item: (-item["score"], item["path"]))
    ranked = ranked_notes + ranked_assets
    ranked.sort(key=lambda item: (-item["score"], item["path"]))
    hits = ranked[: max(top_k, 1)]
    min_score_threshold = mt.route_min_score_threshold(query)
    fallback_context = False
    if not hits:
        fallback_context = True
    elif hits[0]["score"] < min_score_threshold:
        fallback_context = True
    elif len(hits) > 1 and hits[0]["score"] > 0 and (hits[1]["score"] / hits[0]["score"]) >= mt.AMBIGUITY_RATIO:
        fallback_context = True
    return {
        "hits": [
            {
                "path": item["repo_path"],
                "title": item["title"],
                "kind": item["kind"],
                "asset_type": item.get("asset_type"),
                "score": item["score"],
            }
            for item in hits
        ],
        "fallback_context": fallback_context,
    }


def _enhanced_route(repo_root: Path, query: str, top_k: int) -> dict[str, Any]:
    payload = codex_memo.command_route(repo_root, repo_root, task=query, top_k=top_k, record_event=False)
    return {
        "hits": payload["merged_hits"],
        "fallback_context": payload["fallback_context"],
        "execution_gate": payload["execution_gate"],
        "semantic_mode": payload.get("semantic_mode", "unknown"),
    }


def _baseline_route(repo_root: Path, query: str, top_k: int) -> dict[str, Any]:
    payload = mt.command_route(repo_root, task=query, top_k=top_k, use_insight=False, record_event=False)
    return {
        "hits": payload["hits"],
        "fallback_context": payload["fallback_context"],
    }


def _route_without_learning(repo_root: Path, query: str, top_k: int) -> dict[str, Any]:
    payload = mt.command_route(repo_root, task=query, top_k=top_k, use_insight=True, use_learning=False, record_event=False)
    return {
        "hits": payload["hits"],
        "fallback_context": payload["fallback_context"],
    }


def _seed_note(path: Path, frontmatter: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.strip() + "\n---\n\n" + body.strip() + "\n", encoding="utf-8")


def _seed_learning_fixture(root: Path) -> None:
    memory_root = root / ".codex" / "memory"
    for relative in ["runbooks", "postmortems", "decisions", "patterns"]:
        (memory_root / relative).mkdir(parents=True, exist_ok=True)
    _seed_note(
        memory_root / "context.md",
        textwrap.dedent(
            """\
            ---
            doc_id: context-repository-baseline
            doc_type: context
            title: Fixture Context
            status: active
            scope: repo
            repo_type: repo-memory
            project_summary: 这个仓库负责聊天记录恢复与 verifier sidecar 治理.
            tags: [repo, context]
            entrypoints:
              - main.py
            common_tasks:
              - 聊天记录恢复
            triggers:
              - before work
            keywords:
              - context
            canonical: true
            related: []
            supersedes: []
            last_verified: 2026-04-20
            confidence: high
            update_policy: merge
            must_read:
              - runbooks/thread-recovery.md
            when_to_read:
              - before work
            """
        ),
        "# Context",
    )
    _seed_note(
        memory_root / "runbooks" / "thread-recovery.md",
        textwrap.dedent(
            """\
            ---
            doc_id: runbook-thread-recovery
            doc_type: runbook
            title: 线程恢复流程
            status: active
            scope: repo
            tags: [codex, threads, recovery]
            triggers:
              - 线程列表恢复
            keywords:
              - thread recovery
            canonical: true
            related: []
            supersedes: []
            last_verified: 2026-04-20
            confidence: high
            update_policy: merge
            when_to_read:
              - 排查线程丢失时
            """
        ),
        "按 thread id 反查历史会话记录, 恢复线程显示.",
    )


def _learning_replay() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        _seed_learning_fixture(repo_root)
        query = "找回之前聊天记录"
        before = mt.command_route(repo_root, task=query, top_k=3, record_event=False)
        rl.record_success(
            repo_root,
            query=query,
            target_paths=["memory/runbooks/thread-recovery.md"],
            source="benchmark",
        )
        after = mt.command_route(repo_root, task=query, top_k=3, record_event=False)
        return {
            "query": query,
            "before": {
                "top_hit": before["hits"][0] if before["hits"] else None,
                "fallback_context": before["fallback_context"],
            },
            "after": {
                "top_hit": after["hits"][0] if after["hits"] else None,
                "fallback_context": after["fallback_context"],
            },
        }


def _insight_replay() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        _seed_learning_fixture(repo_root)
        query = "找回之前聊天记录"
        before = mt.command_route(repo_root, task=query, top_k=3, use_insight=False, record_event=False)
        after = mt.command_route(repo_root, task=query, top_k=3, use_insight=True, record_event=False)
        return {
            "query": query,
            "before": {
                "top_hit": before["hits"][0] if before["hits"] else None,
                "fallback_context": before["fallback_context"],
            },
            "after": {
                "top_hit": after["hits"][0] if after["hits"] else None,
                "fallback_context": after["fallback_context"],
            },
        }


def _adoption_replay() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        _seed_learning_fixture(repo_root)
        query = "找回之前聊天记录"
        before = mt.command_route(repo_root, task=query, top_k=3, use_insight=True, record_event=False)
        top_hit = before["hits"][0]["path"] if before["hits"] else ""
        rc.upsert_checkpoint(
            repo_root,
            task="thread recovery adoption",
            key_facts=["thread recovery reused"],
            task_assets=[],
            reused_assets=[],
            current_invariant=["follow the recovered thread path"],
            verified_steps=["route inspected"],
            route_query=query,
            route_event_id="benchmark-adoption",
            surfaced_hits_hash="benchmark-adoption",
            surfaced_hits=[hit["path"] for hit in before["hits"]],
            selected_hit=top_hit,
            adopted_hit=top_hit,
            observed_actions=["使用 thread id 反查历史会话", "沿用 thread recovery runbook"],
            evidence_paths=[top_hit],
        )
        rl.record_success(
            repo_root,
            query=query,
            target_paths=[top_hit],
            source="adoption",
        )
        checkpoint = rc.read_checkpoint(repo_root, "thread recovery adoption")
        after = mt.command_route(repo_root, task=query, top_k=3, use_insight=True, record_event=False)
        return {
            "query": query,
            "checkpoint": {
                "retrieval_traces": checkpoint.get("retrieval_traces", []),
            },
            "before": {
                "top_hit": before["hits"][0] if before["hits"] else None,
                "fallback_context": before["fallback_context"],
            },
            "after": {
                "top_hit": after["hits"][0] if after["hits"] else None,
                "fallback_context": after["fallback_context"],
            },
        }


def _new_mode_stats() -> dict[str, Any]:
    return {
        "case_count": 0,
        "top1_hits": 0,
        "topk_hits": 0,
        "fallback_count": 0,
        "selected_top1_hits": 0,
        "semantic_mode_counts": {"local": 0, "skipped": 0, "other": 0},
        "latency_samples": [],
    }


def _record_mode_stats(stats: dict[str, Any], route: dict[str, Any], case: dict[str, Any], *, top_k: int, latency_ms: float) -> dict[str, Any]:
    semantic_mode = str(route.get("semantic_mode", "unknown")).strip() or "unknown"
    top1_hit = _is_case_hit(route["hits"], case, top_n=1)
    topk_hit = _is_case_hit(route["hits"], case, top_n=top_k)
    selected_top1_hit = str(route.get("execution_gate", {}).get("selected_path", "")).strip() == str(case.get("expected_top1", "")).strip()
    stats["case_count"] += 1
    stats["top1_hits"] += int(top1_hit)
    stats["topk_hits"] += int(topk_hit)
    stats["fallback_count"] += int(bool(route["fallback_context"]))
    stats["selected_top1_hits"] += int(selected_top1_hit)
    stats["semantic_mode_counts"][semantic_mode if semantic_mode in stats["semantic_mode_counts"] else "other"] += 1
    stats["latency_samples"].append(latency_ms)
    return {
        "top1_hit": top1_hit,
        "topk_hit": topk_hit,
        "selected_top1_hit": selected_top1_hit,
        "semantic_mode": semantic_mode,
    }


def _latency_summary(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"p50": 0, "max": 0}
    ordered = sorted(samples)
    return {
        "p50": ordered[len(ordered) // 2],
        "max": max(ordered),
    }


def _finalize_mode_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_count": stats["case_count"],
        "top1_hits": stats["top1_hits"],
        "topk_hits": stats["topk_hits"],
        "fallback_count": stats["fallback_count"],
        "selected_top1_hits": stats["selected_top1_hits"],
        "semantic_mode_counts": stats["semantic_mode_counts"],
        "latency_ms": _latency_summary(list(stats["latency_samples"])),
    }


@contextmanager
def resolved_benchmark_repo_root(repo_root: Path) -> Any:
    if (repo_root / ".codex" / "memory").exists():
        yield {
            "effective_repo_root": repo_root,
            "fixture_used": False,
        }
        return

    fixture_memory_root = repo_root / BUNDLED_FIXTURE_MEMORY_ROOT
    if not fixture_memory_root.exists():
        yield {
            "effective_repo_root": repo_root,
            "fixture_used": False,
        }
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        effective_repo_root = Path(tmpdir) / "repo"
        target_memory_root = effective_repo_root / ".codex" / "memory"
        shutil.copytree(fixture_memory_root, target_memory_root)
        yield {
            "effective_repo_root": effective_repo_root,
            "fixture_used": True,
        }


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    raw_cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = raw_cases.get("cases", raw_cases)
    original_fake = os.environ.get("CODEX_MEMO_SEMANTIC_FAKE")
    os.environ["CODEX_MEMO_SEMANTIC_FAKE"] = "1"
    results: list[dict[str, Any]] = []
    legacy_top1 = 0
    legacy_top3 = 0
    baseline_top1 = 0
    baseline_top3 = 0
    legacy_fallback = 0
    baseline_fallback = 0
    learning_probe_improved = 0
    learning_probe_total = 0
    mode_breakdown = {
        "full": _new_mode_stats(),
    }

    effective_repo_root = repo_root
    fixture_used = False
    try:
        with resolved_benchmark_repo_root(repo_root) as resolved:
            effective_repo_root = Path(resolved["effective_repo_root"]).resolve()
            fixture_used = bool(resolved["fixture_used"])
            for case in cases:
                top_k = int(case.get("top_k", 3))
                legacy = _legacy_route(effective_repo_root, case["query"], top_k)
                baseline = _baseline_route(effective_repo_root, case["query"], top_k)
                started = time.perf_counter()
                enhanced = _enhanced_route(effective_repo_root, case["query"], top_k)
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                semantic_mode = str(enhanced.get("semantic_mode", "unknown")).strip() or "unknown"
                learning_probe = None
                if case.get("compare_learning"):
                    learning_probe_total += 1
                    without_learning = _route_without_learning(effective_repo_root, case["query"], top_k)
                    with_learning = _enhanced_route(effective_repo_root, case["query"], top_k)
                    before_path = str(without_learning["hits"][0]["path"]) if without_learning["hits"] else ""
                    after_path = str(with_learning["hits"][0]["path"]) if with_learning["hits"] else ""
                    before_score = float(without_learning["hits"][0]["score"]) if without_learning["hits"] else 0.0
                    after_score = float(with_learning["hits"][0]["score"]) if with_learning["hits"] else 0.0
                    with_learning_hit = _is_case_hit(with_learning["hits"], case, top_n=top_k)
                    same_top_hit = before_path == after_path and bool(before_path)
                    improved = with_learning_hit and same_top_hit and (
                        after_score > before_score
                        or (bool(without_learning["fallback_context"]) and not bool(with_learning["fallback_context"]))
                    )
                    learning_probe_improved += int(improved)
                    learning_probe = {
                        "improved": improved,
                        "same_top_hit": same_top_hit,
                        "without_learning": {
                            "top_hit": without_learning["hits"][0] if without_learning["hits"] else None,
                            "fallback_context": without_learning["fallback_context"],
                        },
                        "with_learning": {
                            "top_hit": with_learning["hits"][0] if with_learning["hits"] else None,
                            "fallback_context": with_learning["fallback_context"],
                        },
                    }
                legacy_top1_hit = _is_case_hit(legacy["hits"], case, top_n=1)
                legacy_top3_hit = _is_case_hit(legacy["hits"], case, top_n=top_k)
                baseline_top1_hit = _is_case_hit(baseline["hits"], case, top_n=1)
                baseline_top3_hit = _is_case_hit(baseline["hits"], case, top_n=top_k)
                enhanced_top1_hit = _is_case_hit(enhanced["hits"], case, top_n=1)
                enhanced_top3_hit = _is_case_hit(enhanced["hits"], case, top_n=top_k)
                legacy_top1 += int(legacy_top1_hit)
                legacy_top3 += int(legacy_top3_hit)
                baseline_top1 += int(baseline_top1_hit)
                baseline_top3 += int(baseline_top3_hit)
                legacy_fallback += int(bool(legacy["fallback_context"]))
                baseline_fallback += int(bool(baseline["fallback_context"]))
                selected_top1_hit = str(enhanced.get("execution_gate", {}).get("selected_path", "")).strip() == str(case.get("expected_top1", "")).strip()
                _record_mode_stats(mode_breakdown["full"], enhanced, case, top_k=top_k, latency_ms=elapsed_ms)
                results.append(
                    {
                        "id": case["id"],
                        "query": case["query"],
                        "expected_top1": case.get("expected_top1", ""),
                        "selected_top1_hit": selected_top1_hit,
                        "latency_ms": elapsed_ms,
                        "legacy": {
                            "top1_hit": legacy_top1_hit,
                            "topk_hit": legacy_top3_hit,
                            "fallback_context": legacy["fallback_context"],
                            "hits": legacy["hits"],
                        },
                        "baseline_enhanced": {
                            "top1_hit": baseline_top1_hit,
                            "topk_hit": baseline_top3_hit,
                            "fallback_context": baseline["fallback_context"],
                            "hits": baseline["hits"],
                        },
                        "enhanced": {
                            "top1_hit": enhanced_top1_hit,
                            "topk_hit": enhanced_top3_hit,
                            "fallback_context": enhanced["fallback_context"],
                            "semantic_mode": semantic_mode,
                            "selected_path": enhanced.get("execution_gate", {}).get("selected_path", ""),
                            "hits": enhanced["hits"],
                        },
                        **({"learning_probe": learning_probe} if learning_probe is not None else {}),
                    }
                )
    finally:
        if original_fake is None:
            os.environ.pop("CODEX_MEMO_SEMANTIC_FAKE", None)
        else:
            os.environ["CODEX_MEMO_SEMANTIC_FAKE"] = original_fake

    finalized_mode_breakdown = {
        "full": _finalize_mode_stats(mode_breakdown["full"]),
    }
    full_summary = finalized_mode_breakdown["full"]
    payload = {
        "repo_root": str(repo_root),
        "effective_repo_root": str(effective_repo_root),
        "benchmark_fixture_used": fixture_used,
        "case_count": len(cases),
        "cases": results,
        "summary": {
            "legacy_top1_hits": legacy_top1,
            "legacy_topk_hits": legacy_top3,
            "legacy_fallback_count": legacy_fallback,
            "baseline_enhanced_top1_hits": baseline_top1,
            "baseline_enhanced_topk_hits": baseline_top3,
            "baseline_enhanced_fallback_count": baseline_fallback,
            "enhanced_top1_hits": full_summary["top1_hits"],
            "enhanced_topk_hits": full_summary["topk_hits"],
            "enhanced_fallback_count": full_summary["fallback_count"],
            "selected_top1_hits": full_summary["selected_top1_hits"],
            "semantic_mode_counts": full_summary["semantic_mode_counts"],
            "latency_ms": full_summary["latency_ms"],
            "mode_breakdown": finalized_mode_breakdown,
            "learning_probe_improved": learning_probe_improved,
            "learning_probe_total": learning_probe_total,
        },
        "insight_replay": _insight_replay(),
        "learning_replay": _learning_replay(),
        "adoption_replay": _adoption_replay(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if full_summary["selected_top1_hits"] < len(cases):
        return 1
    semantic_required_cases = [
        case for case in results if str(next((item.get("mode", "") for item in cases if item["id"] == case["id"]), "")).strip() == "semantic_required"
    ]
    if any(case["enhanced"]["semantic_mode"] == "skipped" for case in semantic_required_cases):
        return 1
    if learning_probe_total and learning_probe_improved < learning_probe_total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
