import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("research_run_audit", Path(__file__).parents[1] / "scripts/audit-research-run.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def test_body_citations_deduplicate_versions_and_exclude_bibliography(tmp_path):
    (tmp_path / "report-with-citations.md").write_text(
        "# 综述\n发现 [A](https://arxiv.org/abs/2210.03629v2) "
        "[A PDF](https://arxiv.org/pdf/2210.03629.pdf)\n"
        "## 参考文献\n[B](https://arxiv.org/abs/2308.08155)\n")
    result = audit_module.audit(tmp_path)
    assert result["body_linked_arxiv_count"] == 1
    assert result["bibliography_only_links"] == ["https://arxiv.org/abs/2308.08155"]
    assert result["recorded_usage"] is None


def test_shared_passage_diagnostic_is_not_automatic_failure(tmp_path):
    events = [{"tool": "read_passage", "status": "completed", "agent": agent,
               "result": {"source": "https://arxiv.org/abs/2210.03629", "page": 2, "offset": 0}}
              for agent in ("A", "B")]
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    result = audit_module.audit(tmp_path)
    assert result["direct_read_calls"] == 2 and result["distinct_direct_passages"] == 1
    assert result["repeated_direct_reads"] == 1
    assert result["tool_failure_counts"] == {}
    assert not result["report_exists"]
