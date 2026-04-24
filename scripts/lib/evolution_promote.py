from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import sys

LIB_DIR = Path(__file__).resolve().parent
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import evolution_schema as schema
import evolution_signals as signals_mod

PROMOTION_WINDOW_DAYS = 14
RETIRE_FAILURE_WINDOW = 5
RETIRE_FAILURE_THRESHOLD = 2
SHADOW_SUCCESS_THRESHOLD = 1


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def _capsule_id(cluster_key: str) -> str:
    return 'cap_' + cluster_key.replace('|', '_')


def _capsule_query_variants(signal_signature: str) -> list[str]:
    variants: list[str] = []
    for raw_part in signal_signature.split('|'):
        normalized = raw_part.replace('_', ' ').strip()
        if normalized and normalized not in variants:
            variants.append(normalized)
        for token in normalized.split():
            if token and token not in variants:
                variants.append(token)
    return variants


def _strong_verification(event: dict[str, Any]) -> bool:
    evidence = event.get('evidence', {})
    return bool(
        evidence.get('tests_passed')
        or evidence.get('user_confirmed')
        or evidence.get('validation_mode') in {'shell', 'mcp'}
    )


def review_promotions(
    events: list[dict[str, Any]],
    promotion_state: dict[str, Any] | None,
    existing_capsules: list[dict[str, Any]] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    promotion_state = schema.validate_promotion_state(promotion_state or {'version': 1, 'clusters': {}})
    existing_capsules = [schema.validate_capsule(item) for item in (existing_capsules or [])]
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    window_start = now - timedelta(days=PROMOTION_WINDOW_DAYS)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_event in events:
        event = schema.validate_event(raw_event)
        cluster_key = signals_mod.make_signal_signature(event['signals']) + '|' + (event.get('strategy_gene_id') or 'gene_ad_hoc')
        grouped[cluster_key].append(event)

    existing_by_key = {f"{capsule['signal_signature']}|{capsule['source_gene_id']}": capsule for capsule in existing_capsules}
    next_capsules: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    clusters: dict[str, dict[str, Any]] = {}

    for cluster_key, cluster_events in sorted(grouped.items()):
        cluster_events.sort(key=lambda item: _parse_datetime(item['created_at']))
        recent_events = [event for event in cluster_events if _parse_datetime(event['created_at']) >= window_start]
        recent_tail = recent_events[-RETIRE_FAILURE_WINDOW:]
        success_count = sum(1 for event in recent_events if event['status'] == 'success')
        failure_count = sum(1 for event in recent_events if event['status'] == 'failed')
        partial_count = sum(1 for event in recent_events if event['status'] == 'partial')
        distinct_sessions = len({event.get('session_fingerprint') or event['task_fingerprint'] for event in recent_events})
        recent_failure_tail_count = sum(1 for event in recent_tail if event['status'] == 'failed')
        strong_verification = any(_strong_verification(event) and event['status'] == 'success' for event in recent_events)
        signal_signature, source_gene_id = cluster_key.rsplit('|', 1)
        existing = existing_by_key.get(cluster_key)

        if recent_failure_tail_count >= RETIRE_FAILURE_THRESHOLD and existing and existing['status'] in {'active', 'shadowed'}:
            status = 'retired'
        elif success_count >= 3 and distinct_sessions >= 2 and failure_count == 0 and strong_verification:
            status = 'active'
        elif success_count >= SHADOW_SUCCESS_THRESHOLD and failure_count == 0 and strong_verification:
            status = 'shadowed'
        else:
            status = 'candidate'

        rule = existing['rule'] if existing else f'Apply repeatable workflow for {signal_signature} before long-term write-back.'
        capsule = schema.validate_capsule(
            {
                'id': existing['id'] if existing else _capsule_id(cluster_key),
                'source_gene_id': source_gene_id,
                'signal_signature': signal_signature,
                'rule': rule,
                'promotion_evidence': {
                    'success_count': success_count,
                    'failure_count': failure_count,
                    'distinct_sessions': distinct_sessions,
                },
                'status': status,
                'created_at': existing['created_at'] if existing else cluster_events[0]['created_at'],
                'last_verified': now.date().isoformat(),
            }
        )
        previous_status = existing['status'] if existing else None
        if previous_status != capsule['status']:
            changes.append({'capsule_id': capsule['id'], 'from': previous_status, 'to': capsule['status']})
        next_capsules.append(capsule)
        clusters[cluster_key] = {
            'success_count': success_count,
            'failure_count': failure_count,
            'partial_count': partial_count,
            'distinct_sessions': distinct_sessions,
            'last_event_id': cluster_events[-1]['id'],
            'capsule_id': capsule['id'],
            'status': 'promoted' if capsule['status'] == 'active' else capsule['status'],
        }

    for existing in existing_capsules:
        cluster_key = f"{existing['signal_signature']}|{existing['source_gene_id']}"
        if cluster_key not in grouped:
            next_capsules.append(existing)
            clusters[cluster_key] = promotion_state['clusters'].get(cluster_key, {
                'success_count': existing['promotion_evidence']['success_count'],
                'failure_count': existing['promotion_evidence']['failure_count'],
                'partial_count': 0,
                'distinct_sessions': existing['promotion_evidence']['distinct_sessions'],
                'capsule_id': existing['id'],
                'status': existing['status'],
            })

    return {
        'promotion_state': schema.validate_promotion_state({'version': promotion_state['version'], 'clusters': clusters}),
        'capsules': next_capsules,
        'changes': changes,
    }


def suggest_memory_writeback(capsules: list[dict[str, Any]]) -> dict[str, Any]:
    suggestions = []
    retrieval_hints = []
    for capsule in capsules:
        capsule = schema.validate_capsule(capsule)
        signal_terms = _capsule_query_variants(capsule['signal_signature'])
        if capsule['status'] == 'active':
            slug = capsule['id'].removeprefix('cap_')
            suggestions.append(
                {
                    'capsule_id': capsule['id'],
                    'doc_type': 'runbook',
                    'slug': slug,
                    'title': capsule['rule'][:80],
                    'signal_signature': capsule['signal_signature'],
                    'source_gene_id': capsule['source_gene_id'],
                    'requires_memory_tool': True,
                }
            )
        if capsule['status'] not in {'active', 'shadowed'}:
            continue
        base_boost = (
            min(capsule['promotion_evidence']['success_count'], 5) * 0.12
            + min(capsule['promotion_evidence']['distinct_sessions'], 3) * 0.08
        )
        retrieval_stage = 'active' if capsule['status'] == 'active' else 'shadowed'
        if retrieval_stage == 'shadowed':
            base_boost = min(base_boost, 0.28)
        retrieval_hints.append(
            {
                'capsule_id': capsule['id'],
                'signal_signature': capsule['signal_signature'],
                'match_terms': signal_terms,
                'query_variants': [item for item in signal_terms if ' ' in item] or signal_terms[:2],
                'ranking_boost': round(base_boost, 4),
                'retrieval_stage': retrieval_stage,
            }
        )
    return {'suggestions': suggestions, 'retrieval_hints': retrieval_hints}


def retire_stale(capsules: list[dict[str, Any]], now: datetime | None = None, days: int = 30) -> list[dict[str, Any]]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now - timedelta(days=days)
    updated = []
    for raw_capsule in capsules:
        capsule = schema.validate_capsule(raw_capsule)
        if capsule['status'] == 'candidate' and _parse_datetime(capsule['created_at']) < cutoff:
            capsule['status'] = 'retired'
            capsule['last_verified'] = now.date().isoformat()
        updated.append(schema.validate_capsule(capsule))
    return updated
