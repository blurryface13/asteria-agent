import json

from asteria_researcher.agentic.evidence_view import choose_writer_evidence, unique_writer_evidence
from scripts.audit_writer_evidence import summarize


def test_writer_view_keeps_unique_passages_and_all_reader_contexts():
    shared = {'source': 'https://example.org/paper', 'page': 3, 'source_type': 'paper',
              'text': 'The reported gain applies only to dataset A.'}
    second = {**shared, 'page': 4, 'text': 'Dataset B has a different baseline.'}
    groups = [
        {'agent': 'methods', 'query': 'Method and dataset', 'passages': [shared]},
        {'agent': 'evaluation', 'query': 'Limits and comparison', 'passages': [shared, second]},
    ]
    original = json.dumps(groups, sort_keys=True)
    result = unique_writer_evidence(groups)
    assert json.dumps(groups, sort_keys=True) == original
    assert sum(len(group['passages']) for group in result) == 2
    assert result[0]['passages'][0]['text'] == shared['text']
    assert result[0]['passages'][0]['also_seen_by'] == [
        {'agent': 'evaluation', 'query': 'Limits and comparison'}]
    assert result[1]['passages'][0] == second


def test_writer_view_only_deduplicates_exact_passages():
    base = {'source': 'paper', 'page': 1, 'text': 'Effect measured at 1%.'}
    changed = {**base, 'text': 'Effect measured at 2%.'}
    groups = [{'agent': 'a', 'query': 'a', 'passages': [base, changed]},
              {'agent': 'b', 'query': 'b', 'passages': [base]}]
    result = unique_writer_evidence(groups)
    assert [p['text'] for group in result for p in group['passages']] == [
        base['text'], changed['text']]
    audit = summarize(groups)
    assert audit['original_passages'] == 3
    assert audit['unique_passages'] == 2
    assert audit['duplicate_passages'] == 1
    assert audit['compact_context_chars'] < audit['original_context_chars']


def test_writer_view_stays_baseline_when_attribution_overhead_exceeds_savings():
    tiny = [{'source': 's', 'page': i, 'text': 'x'} for i in range(20)]
    groups = [{'agent': 'a', 'query': 'a', 'passages': tiny},
              {'agent': 'b', 'query': 'b' * 120, 'passages': tiny}]
    view, mode, original_chars, sent_chars = choose_writer_evidence(groups, enabled=True)
    assert view == groups
    assert mode == 'baseline'
    assert sent_chars == original_chars
