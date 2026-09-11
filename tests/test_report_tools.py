from asteria_researcher.agentic.report_tools import validate_report_draft


SOURCE = "https://arxiv.org/abs/1706.03762"


def test_report_tool_checks_provenance_length_and_structure():
    result = validate_report_draft(
        "# 文献综述\n## 方法比较\n" + ("研究" * 500) + f"\n[论文]({SOURCE})",
        [SOURCE], target_chars=300,
    )

    assert not result["ok"]
    assert result["invalid_urls"] == []
    assert "方法比较" in result["headings"]
    assert any("篇幅" in issue for issue in result["issues"])


def test_report_tool_rejects_unread_source():
    result = validate_report_draft(
        "# 综述\n结论 [未读取论文](https://arxiv.org/abs/1810.04805)",
        [SOURCE],
    )

    assert not result["ok"]
    assert result["invalid_urls"] == ["https://arxiv.org/abs/1810.04805"]
