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


def test_report_tool_accepts_only_recorded_private_knowledge_citations():
    marker = "KB:" + "a" * 20
    report = f"# 综述\n实验室资料显示了方法上的对比结果。〔{marker}〕"
    assert validate_report_draft(report, [marker])["ok"]
    invalid = validate_report_draft(report, ["KB:" + "b" * 20])
    assert not invalid["ok"] and invalid["invalid_urls"] == [marker]


def test_financial_magnitude_guard_rejects_inverted_mixed_units():
    source = 'https://s201.q4cdn.com/141608511/files/doc_financials/2026/q4/10K-NVDA.pdf'
    wrong = f'# 财务分析\n952 亿美元的义务规模远超当期经营活动现金流（102,718 百万美元）。[来源]({source})'
    result = validate_report_draft(wrong, [source], domain='financial_research')
    assert not result['ok']
    assert any('95,200.00 百万美元' in issue and '102,718.00 百万美元' in issue
               for issue in result['issues'])
    assert validate_report_draft(wrong, [source])['ok']  # Academic prose is not financially audited.
    right = wrong.replace('远超', '低于')
    assert validate_report_draft(right, [source], domain='financial_research')['ok']
    ambiguous = f'# 财务分析\n另有 10 亿美元的存货，952 亿美元的义务规模高于 8,000 百万美元。[来源]({source})'
    assert validate_report_draft(ambiguous, [source], domain='financial_research')['ok']


def test_financial_report_rewrites_long_english_filing_quote():
    source = 'https://example.org/filing.pdf'
    quote = ' '.join(['These risks may affect reported revenue and operating cash flow'] * 5)
    long_report = f'公司风险披露：「{quote}」[原件]({source})'
    issues = validate_report_draft(long_report, [source], domain='financial_research')['issues']
    assert any('英文原文引述过长' in issue for issue in issues)
    brief = f'公司提示收入与现金流可能受相关风险影响。[原件]({source})'
    assert validate_report_draft(brief, [source], domain='financial_research')['ok']
