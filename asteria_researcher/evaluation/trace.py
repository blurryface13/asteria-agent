"""Trace recording and OpenTelemetry-style JSONL ingestion.

GoodQuestion's most reusable idea is the trace tree: an Agent run is a
collection of parented Agent/LLM/Tool spans, rather than only a final answer.
This module supports both native Asteria instrumentation and imported traces.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .models import SpanKind, TraceEnvelope, TraceSpan, TraceStatus, utc_now

logger = logging.getLogger(__name__)
_CURRENT_RECORDER: ContextVar["TraceRecorder | None"] = ContextVar(
    "asteria_evaluation_trace_recorder", default=None
)


def get_current_recorder() -> "TraceRecorder | None":
    return _CURRENT_RECORDER.get()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


class TraceRecorder:
    """In-memory recorder with nested spans and JSONL export."""

    def __init__(self, trace_id: str | None = None, name: str = "asteria-run", metadata: dict[str, Any] | None = None):
        self.trace_id = trace_id or uuid4().hex
        self.name = name
        self.metadata = dict(metadata or {})
        self.spans: list[TraceSpan] = []
        self._active: list[str] = []
        self._token = None

    def activate(self):
        self._token = _CURRENT_RECORDER.set(self)
        return self

    def deactivate(self) -> None:
        if self._token is not None:
            _CURRENT_RECORDER.reset(self._token)
            self._token = None

    def __enter__(self) -> "TraceRecorder":
        return self.activate()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.deactivate()

    def start_span(
        self,
        name: str,
        kind: SpanKind | str = SpanKind.UNKNOWN,
        *,
        parent_span_id: str | None = None,
        input_messages: list[dict[str, Any]] | None = None,
        attributes: dict[str, Any] | None = None,
        tool_name: str | None = None,
        tool_arguments: dict[str, Any] | None = None,
    ) -> TraceSpan:
        if not isinstance(kind, SpanKind):
            try:
                kind = SpanKind(str(kind))
            except ValueError:
                kind = SpanKind.UNKNOWN
        span = TraceSpan(
            trace_id=self.trace_id,
            span_id=uuid4().hex[:16],
            parent_span_id=parent_span_id or (self._active[-1] if self._active else None),
            name=name,
            kind=kind,
            start_time=_now(),
            input_messages=_jsonable(input_messages or []),
            attributes=_jsonable(attributes or {}),
            tool_name=tool_name,
            tool_arguments=_jsonable(tool_arguments or {}),
        )
        self.spans.append(span)
        self._active.append(span.span_id)
        return span

    def finish_span(
        self,
        span: TraceSpan,
        *,
        status: TraceStatus | str = TraceStatus.OK,
        output_messages: list[dict[str, Any]] | None = None,
        tool_result: Any | None = None,
        error: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> TraceSpan:
        if not isinstance(status, TraceStatus):
            try:
                status = TraceStatus(str(status))
            except ValueError:
                status = TraceStatus.UNSET
        end = _now()
        span.end_time = end
        span.status = status
        span.output_messages = _jsonable(output_messages or [])
        span.tool_result = _jsonable(tool_result)
        span.error = error
        if attributes:
            span.attributes.update(_jsonable(attributes))
        if span.start_time:
            span.duration_ms = max(0.0, (end - span.start_time).total_seconds() * 1000)
        if self._active and self._active[-1] == span.span_id:
            self._active.pop()
        elif span.span_id in self._active:
            self._active.remove(span.span_id)
        return span

    @contextmanager
    def span(self, name: str, kind: SpanKind | str = SpanKind.UNKNOWN, **kwargs) -> Iterator[TraceSpan]:
        current = self.start_span(name, kind, **kwargs)
        try:
            yield current
        except Exception as exc:
            self.finish_span(current, status=TraceStatus.ERROR, error=f"{type(exc).__name__}: {exc}")
            raise
        else:
            self.finish_span(current)

    def event(self, name: str, kind: SpanKind | str = SpanKind.UNKNOWN, *, attributes: dict[str, Any] | None = None, status: TraceStatus | str = TraceStatus.OK) -> TraceSpan:
        span = self.start_span(name, kind, attributes=attributes)
        return self.finish_span(span, status=status)

    def to_envelope(self, *, metadata: dict[str, Any] | None = None) -> TraceEnvelope:
        merged = {**self.metadata, **(metadata or {})}
        root = next((span for span in self.spans if not span.parent_span_id), None)
        return TraceEnvelope(
            trace_id=self.trace_id,
            name=self.name,
            root_span_id=root.span_id if root else None,
            spans=self.spans,
            metadata=_jsonable(merged),
        )

    def write_jsonl(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            for span in self.spans:
                handle.write(json.dumps(span.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return destination


class TraceIngestor:
    """Normalize native or OpenTelemetry-ish JSONL into trace envelopes."""

    def ingest_jsonl(self, text: str, *, batch_id: str | None = None, source_system: str | None = None) -> list[TraceEnvelope]:
        raw_spans: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc.msg}") from exc
            raw_spans.extend(self._expand_payload(payload))

        spans = [self.normalize_span(item) for item in raw_spans]
        grouped: dict[str, list[TraceSpan]] = {}
        for span in spans:
            grouped.setdefault(span.trace_id, []).append(span)

        envelopes = []
        for trace_id, items in grouped.items():
            items.sort(key=lambda item: item.start_time or utc_now())
            metadata: dict[str, Any] = {}
            root = next((item for item in items if not item.parent_span_id), items[0] if items else None)
            if root:
                metadata["prompt"] = _prompt_from_messages(root.input_messages)
                metadata["root_name"] = root.name
            envelopes.append(TraceEnvelope(
                trace_id=trace_id,
                name=root.name if root else "agent-run",
                root_span_id=root.span_id if root else None,
                source_batch_id=batch_id,
                source_system=source_system,
                spans=items,
                metadata=metadata,
            ))
        return envelopes

    def normalize_span(self, raw: dict[str, Any]) -> TraceSpan:
        attributes = self._attributes(raw.get("attributes", {}))
        attributes.update({key: value for key, value in raw.items() if key in {
            "gen_ai.operation.name", "gen_ai.system", "gen_ai.request.model",
            "gen_ai.tool.name", "tool.name", "tool.arguments", "tool.result",
        }})
        trace_id = str(raw.get("traceId") or raw.get("trace_id") or attributes.get("traceId") or uuid4().hex)
        span_id = str(raw.get("spanId") or raw.get("span_id") or uuid4().hex[:16])
        parent = raw.get("parentSpanId") or raw.get("parent_span_id")
        name = str(raw.get("name") or raw.get("operation") or "span")
        kind = self._span_kind(raw, attributes, name)
        status, error = self._status(raw, attributes)
        input_messages = self._messages(raw.get("input_messages") or raw.get("inputMessages") or attributes.get("gen_ai.input.messages"))
        output_messages = self._messages(raw.get("output_messages") or raw.get("outputMessages") or attributes.get("gen_ai.output.messages"))
        tool_name = raw.get("tool_name") or raw.get("toolName") or attributes.get("gen_ai.tool.name") or attributes.get("tool.name")
        tool_arguments = raw.get("tool_arguments") or raw.get("toolArguments") or attributes.get("tool.arguments") or {}
        tool_result = raw.get("tool_result")
        if tool_result is None:
            tool_result = raw.get("toolResult")
        if tool_result is None:
            tool_result = attributes.get("tool.result")
        start = self._timestamp(raw.get("startTimeUnixNano") or raw.get("start_time") or raw.get("startTime"))
        end = self._timestamp(raw.get("endTimeUnixNano") or raw.get("end_time") or raw.get("endTime"))
        duration = raw.get("duration_ms") or raw.get("durationMs")
        if duration is None and start and end:
            duration = max(0.0, (end - start).total_seconds() * 1000)
        if duration is not None:
            duration = float(duration)
        return TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=str(parent) if parent else None,
            name=name,
            kind=kind,
            status=status,
            start_time=start,
            end_time=end,
            duration_ms=duration,
            input_messages=input_messages,
            output_messages=output_messages,
            tool_name=str(tool_name) if tool_name else None,
            tool_arguments=self._as_dict(tool_arguments),
            tool_result=tool_result,
            error=error,
            attributes=attributes,
            events=raw.get("events", []) or [],
        )

    def _expand_payload(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and isinstance(payload.get("resourceSpans"), list):
            result: list[dict[str, Any]] = []
            for resource_span in payload["resourceSpans"]:
                for scope_span in resource_span.get("scopeSpans", []):
                    result.extend(scope_span.get("spans", []))
            return result
        if isinstance(payload, dict) and isinstance(payload.get("spans"), list):
            return [item for item in payload["spans"] if isinstance(item, dict)]
        return [payload] if isinstance(payload, dict) else []

    def _attributes(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return {str(key): self._unwrap(value) for key, value in raw.items()}
        if isinstance(raw, list):
            result = {}
            for item in raw:
                if isinstance(item, dict) and item.get("key"):
                    result[str(item["key"])] = self._unwrap(item.get("value"))
            return result
        return {}

    def _unwrap(self, value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("stringValue", "intValue", "boolValue", "doubleValue", "arrayValue", "kvlistValue"):
                if key in value:
                    return value[key]
        return value

    def _messages(self, value: Any) -> list[dict[str, Any]]:
        value = self._parse_json(value)
        if isinstance(value, dict) and isinstance(value.get("messages"), list):
            value = value["messages"]
        if not isinstance(value, list):
            return []
        return [item if isinstance(item, dict) else {"role": "unknown", "content": str(item)} for item in value]

    def _parse_json(self, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    def _as_dict(self, value: Any) -> dict[str, Any]:
        parsed = self._parse_json(value)
        return parsed if isinstance(parsed, dict) else {"value": parsed} if parsed not in (None, "") else {}

    def _span_kind(self, raw: dict[str, Any], attributes: dict[str, Any], name: str) -> SpanKind:
        explicit = raw.get("kind") or raw.get("span_kind") or raw.get("spanKind") or attributes.get("span.kind")
        if explicit:
            normalized = str(explicit).lower().replace("invoke_agent", "agent").replace("execute_tool", "tool").replace("chat", "llm")
            try:
                return SpanKind(normalized)
            except ValueError:
                pass
        operation = str(raw.get("operation") or attributes.get("gen_ai.operation.name") or "").lower()
        lowered = name.lower()
        if "tool" in operation or "tool" in lowered or attributes.get("gen_ai.tool.name") or attributes.get("tool.name"):
            return SpanKind.TOOL
        if "agent" in operation or "agent" in lowered or operation == "invoke_agent":
            return SpanKind.AGENT
        if operation in {"chat", "completion", "llm"} or "llm" in lowered or "model" in lowered:
            return SpanKind.LLM
        if "retriev" in lowered or "search" in lowered:
            return SpanKind.RETRIEVAL
        return SpanKind.UNKNOWN

    def _status(self, raw: dict[str, Any], attributes: dict[str, Any]) -> tuple[TraceStatus, str | None]:
        status = raw.get("status") or raw.get("status_code") or attributes.get("status")
        if isinstance(status, dict):
            status = status.get("code") or status.get("status_code")
        normalized = str(status or "").lower()
        error = raw.get("error") or raw.get("exception") or attributes.get("error.type") or attributes.get("error.message")
        if normalized in {"error", "status_code_error", "2", "failed", "failure"} or error:
            return TraceStatus.ERROR, str(error) if error else "span reported an error"
        if normalized in {"ok", "status_code_ok", "1", "success", "completed"}:
            return TraceStatus.OK, None
        return TraceStatus.UNSET, None

    def _timestamp(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            if isinstance(value, (int, float)):
                number = float(value)
                if number > 1e15:
                    return datetime.fromtimestamp(number / 1e9, tz=timezone.utc)
                if number > 1e12:
                    return datetime.fromtimestamp(number / 1000, tz=timezone.utc)
                return datetime.fromtimestamp(number, tz=timezone.utc)
            text = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None


def _prompt_from_messages(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") in {"user", "human"} and message.get("content"):
            return str(message["content"])
    return ""
