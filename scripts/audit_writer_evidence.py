"""Count exact passage duplication in a saved Run without printing source text.

Usage: python scripts/audit_writer_evidence.py outputs/review_<id>/evidence.json
This is a context-size diagnostic, not a measured model-token saving.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asteria_researcher.agentic.evidence_view import unique_writer_evidence


def summarize(groups):
    compact = unique_writer_evidence(groups)
    original_count = sum(len(group.get('passages', [])) for group in groups)
    compact_count = sum(len(group.get('passages', [])) for group in compact)
    original_chars = len(json.dumps(groups, ensure_ascii=False))
    compact_chars = len(json.dumps(compact, ensure_ascii=False))
    return {'original_passages': original_count, 'unique_passages': compact_count,
            'duplicate_passages': original_count - compact_count,
            'original_context_chars': original_chars, 'compact_context_chars': compact_chars,
            'context_char_reduction_ratio': round(1 - compact_chars / original_chars, 4) if original_chars else 0,
            'note': 'Potential Writer evidence-context reduction only; not a provider token or cost measurement.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    groups = json.loads(args.evidence.read_text(encoding='utf-8'))
    if not isinstance(groups, list):
        parser.error('Evidence must be a list of passage groups')
    print(json.dumps(summarize(groups), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
