from asteria_researcher.evaluation.models import SpanKind, TraceStatus
from asteria_researcher.evaluation.trace import TraceIngestor, TraceRecorder


def test_recorder_builds_parented_tree():
    recorder = TraceRecorder(metadata={"prompt": "hello"})
    with recorder:
        with recorder.span("agent", SpanKind.AGENT):
            tool = recorder.start_span("search", SpanKind.TOOL, tool_name="search")
            recorder.finish_span(tool, tool_result={"ok": True})
    trace = recorder.to_envelope()
    assert trace.user_prompt() == "hello"
    assert trace.agent_count == 1
    assert trace.tool_count == 1
    assert trace.spans[1].parent_span_id == trace.spans[0].span_id


def test_ingests_otel_style_messages_and_status():
    text = '{"resourceSpans":[{"scopeSpans":[{"spans":[{"traceId":"t","spanId":"s","name":"execute_tool","startTimeUnixNano":1720000000000000000,"endTimeUnixNano":1720000000100000000,"attributes":[{"key":"gen_ai.tool.name","value":{"stringValue":"lookup"}}],"status":{"code":2,"message":"failed"}}]}]}]}'
    trace = TraceIngestor().ingest_jsonl(text)[0]
    span = trace.spans[0]
    assert span.kind == SpanKind.TOOL
    assert span.status == TraceStatus.ERROR
    assert span.duration_ms == 100.0
