from __future__ import annotations

import json
import os
import re
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

import query_intel as qi


PROMPT_VERSION = 1
RERANK_PROMPT_VERSION = 1


class LocalEmbeddingClient:
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    _MODEL_CACHE: dict[str, Any] = {}

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = (model_name or self.DEFAULT_MODEL).strip() or self.DEFAULT_MODEL
        self.available = False
        self.mode = "unavailable"
        self._np: Any | None = None
        self._model: Any | None = None
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except Exception:
            return
        self._np = np
        try:
            model = self._MODEL_CACHE.get(self.model_name)
            if model is None:
                model = SentenceTransformer(self.model_name)
                self._MODEL_CACHE[self.model_name] = model
        except Exception:
            return
        self._model = model
        self.available = True
        self.mode = "local_embedding"

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.available or not texts:
            return []
        vectors = self._model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        if hasattr(vectors, "tolist"):
            vectors = vectors.tolist()
        normalized: list[list[float]] = []
        for row in vectors:
            normalized.append([float(value) for value in row])
        return normalized

    def score_candidates(self, query: str, candidate_vectors: list[list[float]]) -> list[float]:
        if not self.available or not candidate_vectors:
            return []
        query_vectors = self.encode_texts([query])
        if not query_vectors:
            return []
        matrix = self._np.asarray(candidate_vectors, dtype=float)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        query_vector = self._np.asarray(query_vectors[0], dtype=float)
        scores = matrix @ query_vector
        return [float(value) for value in scores.tolist()]


def _extract_output_text(payload: dict[str, Any]) -> str:
    outputs = payload.get("output", [])
    for item in outputs:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                return str(content.get("text", "")).strip()
    return ""


def _extract_json_block(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    return []


class SemanticLLMClient:
    def __init__(self, repo_root: Path, *, force_fake: bool = False) -> None:
        self.repo_root = repo_root.resolve()
        self.fake_mode = force_fake or os.environ.get("CODEX_MEMO_SEMANTIC_FAKE", "").strip() == "1"
        self.model = ""
        self.base_url = ""
        self.api_key = ""
        self.mode = "fake" if self.fake_mode else "online"
        if not self.fake_mode:
            self._load_runtime_config()

    def _load_runtime_config(self) -> None:
        config_path = self.repo_root / ".codex" / "config.toml"
        auth_path = self.repo_root / ".codex" / "auth.json"
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        self.model = str(config.get("model", "")).strip()
        self.base_url = str(config["model_providers"]["OpenAI"]["base_url"]).rstrip("/")
        self.api_key = str(auth["OPENAI_API_KEY"]).strip()
        if not self.model or not self.base_url or not self.api_key:
            raise ValueError("semantic client config is incomplete")

    def _fake_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title", "")).strip()
        aliases = _coerce_list(payload.get("aliases"))
        keywords = _coerce_list(payload.get("keywords"))
        triggers = _coerce_list(payload.get("triggers"))
        excerpt = str(payload.get("excerpt", "")).strip()
        base_terms = qi.flatten_query_terms(" ".join([title, *aliases, *keywords, *triggers, excerpt]), limit=12)
        paraphrases = aliases[:4] or keywords[:4] or base_terms[:4]
        problem_signals = triggers[:4] or keywords[:4] or base_terms[:4]
        return {
            "intent": title or payload.get("path", ""),
            "problem_signals": problem_signals,
            "paraphrases": paraphrases,
            "when_to_use": triggers[:4] or [title] if title else [],
            "when_not_to_use": ["unrelated generic query", "raw task-doc lookup"],
            "related_queries": list(dict.fromkeys([*aliases[:3], *keywords[:3], *base_terms[:4]]))[:6],
            "action_summary": excerpt[:240] or title,
            "confidence": "fake",
            "evidence_spans": [title] if title else [],
            "source_excerpt_refs": ["title", "excerpt"],
        }

    def _online_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        instruction = (
            "You are indexing a project memory note for semantic retrieval. "
            "Return one JSON object only. Do not include markdown. "
            "Use only the provided note data. Do not invent facts beyond the note. "
            "Fields: intent, problem_signals, paraphrases, when_to_use, when_not_to_use, "
            "related_queries, action_summary, confidence, evidence_spans, source_excerpt_refs."
        )
        user_input = json.dumps(payload, ensure_ascii=False)
        request_payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": instruction}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_input}],
                },
            ],
            "text": {"format": {"type": "text"}},
            "store": False,
        }
        request = urllib.request.Request(
            self.base_url + "/responses",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        text = _extract_output_text(response_payload)
        return _extract_json_block(text)

    @staticmethod
    def local_rerank(payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query", "")).strip()
        query_terms = qi.flatten_query_terms(query, limit=16)
        ranked: list[dict[str, Any]] = []
        for candidate in payload.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            path = str(candidate.get("path", "")).strip()
            if not path:
                continue
            title = str(candidate.get("title", "")).strip()
            intent = str(candidate.get("intent", "")).strip()
            action_summary = str(candidate.get("action_summary", "")).strip()
            semantic_text = " ".join(
                [
                    title,
                    intent,
                    action_summary,
                    " ".join(_coerce_list(candidate.get("semantic_reasons"))),
                    " ".join(_coerce_list(candidate.get("lexical_reasons"))),
                ]
            )
            semantic_terms = qi.flatten_query_terms(semantic_text, limit=20)
            metrics = qi.overlap_metrics(query_terms, semantic_terms)
            score = float(candidate.get("lexical_score", 0.0)) * 0.08 + float(candidate.get("semantic_score", 0.0))
            reasons: list[str] = []
            if metrics["overlap"] > 0:
                score += metrics["overlap"] * 2.4
                reasons.append(f"semantic_overlap:{','.join(metrics['shared_terms'][:4])}")
            if candidate.get("kind") == "memory" and candidate.get("doc_type") == "runbook":
                score += 0.9
                reasons.append("prefer_canonical_runbook")
            asset_type = str(candidate.get("asset_type", "")).strip()
            if asset_type == "task-doc":
                score -= 1.0
                reasons.append("deprioritize_task_doc")
            elif asset_type in {"session", "archived_session"}:
                score -= 1.2
                reasons.append("deprioritize_session_asset")
            if float(candidate.get("semantic_score", 0.0)) > 0:
                reasons.append(f"semantic_cache:{float(candidate.get('semantic_score', 0.0)):.2f}")
            if float(candidate.get("lexical_score", 0.0)) > 0:
                reasons.append(f"lexical:{float(candidate.get('lexical_score', 0.0)):.2f}")
            ranked.append(
                {
                    "path": path,
                    "score": round(score, 4),
                    "reasons": reasons,
                }
            )
        ranked.sort(key=lambda item: (-float(item["score"]), item["path"]))
        selected = ranked[0] if ranked else {"path": ""}
        return {
            "model": "local-semantic-rerank",
            "prompt_version": RERANK_PROMPT_VERSION,
            "selected_path": str(selected.get("path", "")).strip(),
            "rerank_reasons": list(selected.get("reasons", [])),
            "gate_override_reason": "semantic rerank selected the strongest semantic runbook candidate",
            "candidate_reasons": ranked,
        }

    def fallback_rerank(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.local_rerank(payload)

    def generate_index_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fake_mode:
            generated = self._fake_generate(payload)
            model_name = "fake-semantic-client"
        else:
            generated = self._online_generate(payload)
            model_name = self.model
        return {
            "model": model_name,
            "prompt_version": PROMPT_VERSION,
            "intent": str(generated.get("intent", "")).strip(),
            "problem_signals": _coerce_list(generated.get("problem_signals")),
            "paraphrases": _coerce_list(generated.get("paraphrases")),
            "when_to_use": _coerce_list(generated.get("when_to_use")),
            "when_not_to_use": _coerce_list(generated.get("when_not_to_use")),
            "related_queries": _coerce_list(generated.get("related_queries")),
            "action_summary": str(generated.get("action_summary", "")).strip(),
            "confidence": str(generated.get("confidence", "")).strip() or ("fake" if self.fake_mode else "model"),
            "evidence_spans": _coerce_list(generated.get("evidence_spans")),
            "source_excerpt_refs": _coerce_list(generated.get("source_excerpt_refs")),
        }

    def rerank_route(self, payload: dict[str, Any]) -> dict[str, Any]:
        generated = self._fake_rerank(payload)
        candidate_reasons = generated.get("candidate_reasons", [])
        normalized_candidates: list[dict[str, Any]] = []
        if isinstance(candidate_reasons, list):
            for item in candidate_reasons:
                if not isinstance(item, dict):
                    continue
                normalized_candidates.append(
                    {
                        "path": str(item.get("path", "")).strip(),
                        "score": float(item.get("score", 0.0)),
                        "reasons": _coerce_list(item.get("reasons")),
                    }
                )
        return {
            "model": "fake-semantic-client",
            "prompt_version": RERANK_PROMPT_VERSION,
            "selected_path": str(generated.get("selected_path", "")).strip(),
            "rerank_reasons": _coerce_list(generated.get("rerank_reasons")),
            "gate_override_reason": str(generated.get("gate_override_reason", "")).strip(),
            "candidate_reasons": normalized_candidates,
        }
