"""Deterministic tool-result contracts, following EchoMind's tool/trace boundary.

Passage provenance is an Asteria extension; presence is not semantic correctness.
Only trusted tool adapters / the runtime may populate evidence, never model prose.
"""
import hashlib
import json
import re


READ_ONLY_TOOLS = frozenset({
    "list_workspace_files", "read_workspace_file", "read_experiment_file", "list_experiment_files",
    "inspect_repository", "read_repository_file",
    "search_papers", "read_paper", "read_paper_passage", "check_python_syntax", "preview_code_diff",
})


def needs_source_evidence(assignment):
    """Conservative task-contract hint, not another intent model or claim judge.

    Explicit source-dependent tasks need passages. General code tasks do not.
    Negated/ambiguous source requirements can conservatively request evidence.
    """
    text = " ".join((assignment.objective, assignment.focus, assignment.expected_output))
    return bool(re.search(r"论文|文献|原文|知识库|\b(?:papers?|arxiv|rag)\b", text, re.I))


def result_success(result):
    """Separate handler completion from an explicit business failure (EchoMind)."""
    rows = result if isinstance(result, list) else [result]
    states = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("success") is False or row.get("exists") is False or row.get("error") or
                row.get("status") in {"failed", "incomplete", "cancelled", "rejected"}):
            return False
        if row.get("success") is True or row.get("status") == "completed":
            states.append(True)
    return True if states else None


def passages(values):
    """Normalize actual read/retrieve results; titles, URLs and summaries aren't evidence."""
    result = []
    for value in values:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        for row in value if isinstance(value, list) else [value]:
            if (not isinstance(row, dict) or result_success(row) is False or
                    not isinstance(row.get("text"), str) or not row["text"].strip() or
                    not isinstance(row.get("source"), str) or not row["source"].strip()):
                continue
            result.append({k: row[k] for k in ("source", "page", "offset", "text") if k in row})
    return result


def evidence_index(tool_results, requests):
    """Keep IDs and provenance in every turn even when full observations roll off."""
    found = []
    for item in tool_results:
        result = item["result"]
        if item["tool"] == "read_paper_passage" and result_success(result) is not False:
            found.extend((item["id"], "direct", p) for p in passages([result]))
    for request in requests:
        response = request.get("response", {})
        if request.get("status") == "completed":
            found.extend((request["request_id"], "research", p)
                         for p in passages(response.get("evidence", [])))
    return [{"observation_id": oid, "via": via,
             **{k: p.get(k) for k in ("source", "page", "offset")},
             "text_sha256": hashlib.sha256(p["text"].encode()).hexdigest()}
            for oid, via, p in found]


def completion_check(required, index):
    return {"source_evidence_required": required, "observed_passages": len(index),
            "passed": not required or bool(index),
            "scope": "实际片段获取检查；不代表逐条论断正确、完整复现或代码测试通过"}
