from asteria_researcher.evaluation.badcase import BadCaseAnalyzer, trace_to_seed
from asteria_researcher.evaluation.models import SpanKind, TraceStatus
from asteria_researcher.evaluation.trace import TraceRecorder


def test_tool_failure_becomes_seed_candidate():
    recorder = TraceRecorder(metadata={"prompt": "查询实验室资料"})
    with recorder:
        span = recorder.start_span("search", SpanKind.TOOL, tool_name="search")
        recorder.finish_span(span, status=TraceStatus.ERROR, error="permission denied")
    trace = recorder.to_envelope()
    badcase = BadCaseAnalyzer().analyze(trace)
    assert badcase is not None
    assert badcase.failure_type.value == "tool_error"
    assert badcase.failure_span_ids == [span.span_id]
    seed = trace_to_seed(badcase, trace)
    assert seed.prompt == "查询实验室资料"
    assert seed.source_trace_id == trace.trace_id
