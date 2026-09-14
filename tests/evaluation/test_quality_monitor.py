from asteria_researcher.evaluation.monitor import aggregate_monitor
from asteria_researcher.evaluation.quality_judge import evaluate_provider_output, parse_judge_output


def test_judge_requires_all_dimensions_and_never_defaults_on_error():
    record = evaluate_provider_output("问题", "回答", '{"relevance": 0.9}')
    assert record.status == "judge_error"
    assert record.scores is None


def test_judge_parses_four_dimensions_and_overall():
    scores = parse_judge_output(
        '{"relevance": 0.8, "accuracy": 0.9, "completeness": 0.7, "helpfulness": 0.6, '
        '"reasons": {"accuracy": "有证据"}, "evidence_ids": ["e1"]}'
    )
    assert round(scores.overall, 3) == 0.75


def test_monitor_is_unknown_until_minimum_comparable_samples():
    snapshot = aggregate_monitor(
        [{"status": "completed", "task_success": True, "latency_ms": 100}],
        [{"spans": [{"kind": "agent"}, {"kind": "tool", "status": "ok"}]}],
    )
    assert snapshot["routing_state"] == "unknown"
    assert snapshot["monitor_penalty"] is None
    assert snapshot["tool_calls"] == 1
