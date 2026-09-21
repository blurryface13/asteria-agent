"""Expose the SAME task-scoped paper library to the coding loop as plain tools.

Looking up a known formula does not require another Agent. Broad synthesis may
still use request_research; both share source provenance and the run's budgets.
"""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .library import canonical
from .runtime import urls


class PaperSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    start: int = Field(default=0, ge=0, le=300)
    sort_by: Literal["relevance", "submittedDate", "lastUpdatedDate"] = "relevance"


class PaperRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_url: str = Field(min_length=1, max_length=1500)


class PaperPassage(PaperRead):
    page: int = Field(default=1, ge=1, le=1500)
    offset: int = Field(default=0, ge=0, le=5000000)


def build_paper_tools(runtime, agent):
    # Seed only user-provided scholarly URLs; arbitrary model URLs are not seeds.
    for value in urls(runtime.query):
        try:
            runtime.library.add({"url": value, "title": value})
        except ValueError:
            pass

    async def search(arguments):
        p = PaperSearch.model_validate(arguments)
        rows = await runtime.library.search(p.query, start=p.start, sort_by=p.sort_by)
        if rows:
            runtime.successful_searches += 1
        return {"candidates": rows, "evidence_kind": "search_candidates",
                "note": "标题/摘要不是原文结论；选择已发现论文后读具体页段。"}

    async def read(arguments):
        p = PaperRead.model_validate(arguments)
        result = await runtime.library.read(p.paper_url)
        return {**result, "source_url": canonical(p.paper_url), "evidence_kind": "download_preview",
                "note": "仅下载和预览；请继续 read_paper_passage，不能声称通读全文。"}

    async def passage(arguments):
        p = PaperPassage.model_validate(arguments)
        result = runtime.library.read_passage(p.paper_url, page=p.page, offset=p.offset)
        if result["text"].strip():
            key = (result["source"], result["page"], result["offset"])
            if key not in runtime.direct_passages:
                if runtime.direct_chars + len(result["text"]) > 120000:
                    raise ValueError("本轮原文读取预算已达到上限")
                runtime.direct_passages.add(key)
                runtime.direct_chars += len(result["text"])
            if not any(result in e["passages"] for e in runtime.evidence):
                runtime.evidence.append({"agent": agent, "query": p.paper_url, "passages": [result]})
            (runtime.folder / "evidence.json").write_text(json.dumps(runtime.evidence, ensure_ascii=False))
        return {**result, "source_url": result["source"], "evidence_kind": "read_passage"}

    return {"search_papers": (PaperSearch.model_json_schema(), search),
            "read_paper": (PaperRead.model_json_schema(), read),
            "read_paper_passage": (PaperPassage.model_json_schema(), passage)}
