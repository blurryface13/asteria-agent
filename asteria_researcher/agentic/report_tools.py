"""Deterministic validation tools for evidence-backed academic reports."""
from __future__ import annotations

import re
from collections.abc import Iterable

from .library import canonical
from .runtime import urls


HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)
KNOWLEDGE_REF_RE = re.compile(r"〔(KB:[0-9a-f]{20})〕")


def knowledge_refs(markdown: str) -> set[str]:
    """Run-local, auditable chunk references (resolved in knowledge-sources.json)."""
    return set(KNOWLEDGE_REF_RE.findall(markdown or ""))


def _source_key(url: str) -> str:
    """Canonicalize supported scholarly URLs without rejecting local test sources."""
    if url.startswith("KB:"):
        return url
    try:
        return canonical(url)
    except ValueError:
        return url.rstrip("/ ")


def report_length(markdown: str) -> dict:
    """Body length: one CJK character or Latin/number word is one unit.

    Exclude reference appendix, URLs and citation markers, not English prose.
    This is a transparent display-length convention, not tokenizer billing.
    """
    body = re.split(r"(?im)^#{1,3}\s*(?:参考文献|参考资料|references)\s*$", markdown)[0]
    body = re.sub(r"\[[^\]]*\]\(https?://[^)]+\)", "", body)
    body = re.sub(r"https?://\S+|〔KB:[0-9a-f]{20}〕", "", body)
    chinese = len(re.findall(r"[\u4e00-\u9fff]", body))
    words = len(re.findall(r"[A-Za-z0-9]+(?:[.'_-][A-Za-z0-9]+)*", body))
    return {"body_chinese_chars": chinese, "body_latin_words": words,
            "length_units": chinese + words, "length_convention": "body_cjk_plus_latin_words_v1"}


def validate_report_draft(
    markdown: str,
    allowed_urls: Iterable[str],
    *,
    target_chars: int | None = None,
    max_length_ratio: float = 1.4,
    min_length_ratio: float = 0.0,
    enforce_length: bool = True,
) -> dict:
    """Return machine-checkable report issues without judging scientific truth."""
    cited = sorted(urls(markdown or "") | knowledge_refs(markdown or ""))
    allowed = {_source_key(url) for url in allowed_urls}
    invalid = [url for url in cited if _source_key(url) not in allowed]
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", markdown or ""))
    length = report_length(markdown or "")
    issues: list[str] = []
    if not (markdown or "").strip():
        issues.append("报告为空")
    if not cited:
        issues.append("报告缺少可追溯引用")
    if invalid:
        issues.append("报告引用了未读取来源")
    length_issues = []
    if target_chars and length["length_units"] > target_chars * max_length_ratio:
        length_issues.append(f"篇幅超出要求：正文 {length['length_units']} 字/词，目标约 {target_chars}")
    if target_chars and length["length_units"] < target_chars * min_length_ratio:
        length_issues.append(f"篇幅不足：正文 {length['length_units']} 字/词，目标约 {target_chars}；展开已有结论的比较和适用条件，不填充新事实")
    if enforce_length:
        issues.extend(length_issues)
    return {
        "ok": not issues,
        "issues": issues,
        "warnings": [] if enforce_length else length_issues,
        "citation_urls": cited,
        "invalid_urls": invalid,
        "chinese_chars": chinese_chars,
        **length,
        "headings": HEADING_RE.findall(markdown or ""),
    }
