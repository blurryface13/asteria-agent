import copy

import pytest

from backend.runs.store import storage_safe_event


def test_raw_evidence_preserved_and_only_nul_values_normalized():
    payload = {'type': 'tool_event', 'tool': 'finish', 'result': {
        'evidence': [{'page': 3, 'text': '中文\x00evidence\nβ\tvalue\x00'}],
        'literal_escape': r'\u0000', 'ok': True, 'score': .8}}
    original = copy.deepcopy(payload)
    result = storage_safe_event(payload)
    assert payload == original
    assert result['result']['evidence'][0]['text'] == '中文�evidence\nβ\tvalue�'
    assert len(result['result']['evidence'][0]['text']) == len(payload['result']['evidence'][0]['text'])
    assert result['result']['literal_escape'] == r'\u0000'
    assert result['_storage_normalization']['nul_replacements'] == 2


def test_ordinary_events_unchanged():
    payload = {'type': 'report', 'output': '研究报告\n正文', 'usage': None}
    assert storage_safe_event(payload) == payload


def test_invalid_protocol_keys_not_silently_renamed():
    with pytest.raises(ValueError, match='field names'):
        storage_safe_event({'result': {'bad\x00key': 'value'}})
