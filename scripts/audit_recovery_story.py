"""Read-only acceptance check for a saved CitationAgent recovery.

Usage: python scripts/audit_recovery_story.py outputs/review_<id> \
       outputs/delivery_recovery/review_<id>
This checks recorded state and artifacts; it does not prove process-level
automatic resume or replace authenticated end-to-end testing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def audit(source: Path, recovery: Path, *, root: Path) -> dict:
    source, recovery, root = source.resolve(), recovery.resolve(), root.resolve()
    if not source.is_relative_to(root / 'outputs') or not recovery.is_relative_to(root / 'outputs' / 'delivery_recovery'):
        raise ValueError('Both artifacts must be inside this repository outputs tree')

    def read(folder: Path, name: str) -> dict:
        return json.loads((folder / name).read_text(encoding='utf-8'))

    original_run = read(source, 'run.json')
    original_citations = read(source, 'citation-review.json')
    state = read(recovery, 'recovery.json')
    recovered_citations = read(recovery, 'citation-review.json')
    pdf_name = state.get('paths', {}).get('latex_pdf')
    pdf = (root / pdf_name).resolve() if isinstance(pdf_name, str) else None
    checks = {
        'original_failed': original_run.get('status') == 'failed',
        'original_citation_gap': original_citations.get('status') == 'incomplete' and bool(original_citations.get('gaps')),
        'source_matches': state.get('source_review') == str(source),
        'resumed_from_citation': state.get('mode') == 'saved_citation_checkpoint' and state.get('resumed_from') == 'citation_agent',
        'recovery_completed': state.get('status') == 'completed',
        'recovery_citations_complete': recovered_citations.get('status') == 'completed' and not recovered_citations.get('gaps'),
        'pdf_exists': pdf is not None and pdf.is_relative_to(recovery) and pdf.is_file(),
        'not_full_end_to_end': state.get('authenticated_end_to_end') is False,
    }
    return {
        'accepted': all(checks.values()), 'checks': checks,
        'original_gaps': len(original_citations.get('gaps', [])),
        'recovered_gaps': len(recovered_citations.get('gaps', [])),
        'recovery_model_calls': state.get('model_calls'),
        'claim_boundary': 'Saved-artifact citation recovery, not automatic agent-loop resume or a new end-to-end run.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('recovery', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = audit(args.source, args.recovery, root=root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
