"""Lossless passage de-duplication for a Writer's model context.

The authoritative evidence ledger is never modified. Repeated text is sent
once, with all reading contexts attached to its first occurrence.
"""
from __future__ import annotations

import json


def unique_writer_evidence(groups):
    seen = {}
    view = []
    for group in groups:
        provenance = {key: value for key, value in group.items() if key != 'passages'}
        passages = []
        for passage in group.get('passages', []):
            key = json.dumps(passage, sort_keys=True, ensure_ascii=False)
            if key in seen:
                readers = seen[key].setdefault('also_seen_by', [])
                if provenance not in readers:
                    readers.append(provenance)
                continue
            copy = dict(passage)
            seen[key] = copy
            passages.append(copy)
        if passages or not group.get('passages'):
            view.append({**provenance, 'passages': passages})
    return view


def choose_writer_evidence(groups, *, enabled):
    original_chars = len(json.dumps(groups, ensure_ascii=False))
    if not enabled:
        return groups, 'baseline', original_chars, original_chars
    candidate = unique_writer_evidence(groups)
    candidate_chars = len(json.dumps(candidate, ensure_ascii=False))
    if candidate_chars >= original_chars:
        return groups, 'baseline', original_chars, original_chars
    return candidate, 'exact_dedup', original_chars, candidate_chars
