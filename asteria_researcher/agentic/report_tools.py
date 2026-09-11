"""Deterministic validation tools for evidence-backed academic reports."""
from __future__ import annotations

import re
from collections.abc import Iterable

from .library import canonical
from .runtime import urls


HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)


def _source_key(url: str) -> str:
    """Canonicalize supported scholarly URLs without rejecting local test sources."""
    try:
        return canonical(url)
    except ValueError:
        return url.rstrip("/ ")


def validate_report_draft(
    markdown: str,
    allowed_urls: Iterable[str],
    *,
    target_chars: int | None = None,
    max_length_ratio: float = 1.4,
) -> dict:
    """Return machine-checkable report issues without judging scientific truth."""
    cited = sorted(urls(markdown or ""))
    allowed = {_source_key(url) for url in allowed_urls}
    invalid = [url for url in cited if _source_key(url) not in allowed]
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", markdown or ""))
    issues: list[str] = []
    if not (markdown or "").strip():
        issues.append("报告为空")
    if not cited:
        issues.append("报告缺少可追溯引用")
    if invalid:
        issues.append("报告引用了未读取来源")
    if target_chars and chinese_chars > target_chars * max_length_ratio:
        issues.append(f"篇幅超出要求：当前约 {chinese_chars} 字，目标约 {target_chars} 字")
    return {
        "ok": not issues,
        "issues": issues,
        "citation_urls": cited,
        "invalid_urls": invalid,
        "chinese_chars": chinese_chars,
        "headings": HEADING_RE.findall(markdown or ""),
    }
