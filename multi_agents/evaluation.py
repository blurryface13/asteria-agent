"""Reusable metrics for end-to-end research-agent evaluation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher


HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")


@dataclass
class AgentEvalCase:
    case_id: str
    query: str
    expected_sections: list[str]


@dataclass
class AgentEvalResult:
    case_id: str
    variant: str
    outline_coverage: float
    citation_count: int
    citation_support_precision: float | None
    success: bool
    latency_s: float
    report_path: str

    def to_dict(self) -> dict:
        return asdict(self)


def load_cases(data: dict) -> list[AgentEvalCase]:
    return [
        AgentEvalCase(
            case_id=item["id"],
            query=item["query"],
            expected_sections=item["expected_sections"],
        )
        for item in data.get("cases", [])
    ]


def extract_headings(report: str) -> list[str]:
    return [match.group(1).strip() for match in HEADING_RE.finditer(report)]


def count_citations(report: str) -> int:
    return len(set(LINK_RE.findall(report)))


def outline_coverage(report: str, expected_sections: list[str]) -> float:
    """Measure whether planned report headings cover a curated reference outline."""
    headings = [_normalize(value) for value in extract_headings(report)]
    if not expected_sections:
        return 0.0

    hits = 0
    for expected in expected_sections:
        normalized_expected = _normalize(expected)
        if any(_similar(normalized_expected, heading) for heading in headings):
            hits += 1
    return hits / len(expected_sections)


def cited_claims(report: str, limit: int = 8) -> list[str]:
    """Extract short sentences carrying Markdown citations for optional judging."""
    claims: list[str] = []
    for sentence in re.split(r"(?<=[.!?。！？])\s+", report):
        if LINK_RE.search(sentence):
            claims.append(sentence.strip()[:700])
        if len(claims) >= limit:
            break
    return claims


def _normalize(value: str) -> str:
    return re.sub(r"[^\w\s\u4e00-\u9fff]", " ", value.lower()).strip()


def _similar(expected: str, actual: str) -> bool:
    if not expected or not actual:
        return False
    if expected in actual or actual in expected:
        return True
    return SequenceMatcher(None, expected, actual).ratio() >= 0.58
