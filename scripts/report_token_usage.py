"""Summarize model usage events without reading or printing task contents.

Usage: python scripts/report_token_usage.py outputs/acceptance_xxx/events.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _cache_read(usage):
    details = usage.get('input_token_details') or {}
    prompt_details = usage.get('prompt_tokens_details') or {}
    for value in (usage.get('cache_read_input_tokens'), usage.get('prompt_cache_hit_tokens'),
                  details.get('cache_read'), prompt_details.get('cached_tokens')):
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _input_tokens(usage):
    # Raw Claude usage counts tokens after the last cache breakpoint separately.
    if 'cache_read_input_tokens' in usage or 'cache_creation_input_tokens' in usage:
        return (int(usage.get('input_tokens', 0)) + int(usage.get('cache_read_input_tokens', 0))
                + int(usage.get('cache_creation_input_tokens', 0)))
    return int(usage.get('input_tokens', usage.get('prompt_tokens', 0)))


def summarize(events):
    stages = defaultdict(lambda: {'attempts': 0, 'measured_calls': 0, 'missing_usage': 0,
                                  'input_tokens': 0, 'output_tokens': 0,
                                  'cache_read_tokens': 0, 'cache_measured_calls': 0,
                                  'latency_ms': 0, 'latency_measured_calls': 0})
    for event in events:
        event = event.get('payload', event)
        if event.get('type') != 'usage':
            continue
        row = stages[event.get('stage') or 'unclassified']
        row['attempts'] += 1
        usage = event.get('usage')
        if not isinstance(usage, dict) or not usage:
            row['missing_usage'] += 1
        else:
            row['measured_calls'] += 1
            row['input_tokens'] += _input_tokens(usage)
            row['output_tokens'] += int(usage.get('output_tokens', usage.get('completion_tokens', 0)))
            read = _cache_read(usage)
            if read is not None:
                row['cache_read_tokens'] += read
                row['cache_measured_calls'] += 1
        latency = event.get('latency_ms')
        if isinstance(latency, (int, float)):
            row['latency_ms'] += latency
            row['latency_measured_calls'] += 1
    by_stage = dict(sorted(stages.items()))
    totals = {key: sum(row[key] for row in by_stage.values()) for key in next(iter(by_stage.values()), {})}
    totals['cache_read_ratio'] = (round(totals['cache_read_tokens'] / totals['input_tokens'], 4)
                                  if totals.get('input_tokens') and
                                  totals.get('cache_measured_calls') == totals.get('measured_calls') else None)
    for row in by_stage.values():
        row['cache_read_ratio'] = (round(row['cache_read_tokens'] / row['input_tokens'], 4)
                                   if row['input_tokens'] and row['cache_measured_calls'] == row['measured_calls']
                                   else None)
    return {'total': totals, 'by_stage': by_stage,
            'note': 'Logical input tokens include cache reads. A null cache ratio means cache metadata is incomplete; this is not a price estimate.'}


def read_events(path):
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events', type=Path, help='Run events.jsonl or other usage event JSONL')
    args = parser.parse_args()
    print(json.dumps(summarize(read_events(args.events)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
