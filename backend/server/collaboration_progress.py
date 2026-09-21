"""Bounded public progress projection: never copy full code/tool payloads."""


def project_event(event):
    allowed = {"parallel_batch", "parallel_result", "research_handoff", "delegation_quality"}
    if event.get("tool") not in allowed:
        return None
    result = {k: event[k] for k in ("agent", "tool", "status", "time", "batch_id", "request_id", "index",
              "elapsed_ms", "since_dispatch_ms", "first_result_ms", "returned", "wait_ms", "provisional") if k in event}
    result["purpose"] = str(event.get("purpose", ""))[:500]
    def assignment(a):
        return {k: str(a.get(k, ""))[:1200] for k in ("name", "role", "focus", "objective", "expected_output", "exclude")}
    if isinstance(event.get("assignments"), list):
        result["assignments"] = [assignment(a) for a in event["assignments"][:3]]
    if isinstance(event.get("assignment"), dict):
        result["assignment"] = assignment(event["assignment"])
    if event.get("tool") == "research_handoff" and isinstance(event.get("request"), dict):
        result["request"] = {k: str(event["request"].get(k, ""))[:1200]
                             for k in ("question", "observed_problem", "expected_answer")}
    value = event.get("result", {})
    if event["tool"] == "delegation_quality":
        result["error"] = str(value.get("error", ""))[:1000]
    elif isinstance(value, dict):
        result["result"] = {"summary": str(value.get("summary", ""))[:2400], "status": value.get("status")}
    return result
