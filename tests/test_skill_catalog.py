import asyncio
import json
import pytest
from asteria_researcher.agentic.skill_catalog import SkillOptions, SkillSession, catalog, skill_detail, select_writing


def test_catalog_ids_and_trusted_resources():
    entries = catalog()
    assert len({e["id"] for e in entries}) == len(entries)
    for entry in entries:
        assert skill_detail(entry["id"])["content"]
    with pytest.raises(ValueError):
        skill_detail("../../.env")


@pytest.mark.parametrize("data", [
    {"skill_ids": ["report_writing", "general_writing"]},
    {"skill_ids": ["report_formatting"]},
    {"skill_ids": ["missing"]},
    {"skill_ids": ["source_priority", "source_priority"]},
    {"format_profile": "../bad.tex"},
])
def test_invalid_pins_rejected(data):
    with pytest.raises(ValueError):
        SkillOptions(**data)


def test_phase_pins_and_independent_sessions():
    opts = SkillOptions(skill_ids=["source_priority", "report_writing"])
    first, second = SkillSession("research", opts), SkillSession("research")
    assert list(first.loaded) == ["source_priority"]
    assert first.trace()[0]["origin"] == "user"
    assert not second.loaded
    with pytest.raises(ValueError):
        first.load("report_writing")


def test_user_pins_checked_and_repaired_not_silently_overridden():
    calls = []
    async def model(system, payload):
        calls.append(json.loads(payload))
        return json.dumps({"skill_ids": ["general_writing"] if len(calls) == 1 else ["report_writing", "source_priority"],
                           "format_profile": "brief", "reason": "用户选择主题综述与一手来源审查"})
    selection, prompt, trace = asyncio.run(select_writing(model, "写综述", {},
        SkillOptions(skill_ids=["report_writing", "source_priority"], format_profile="brief")))
    assert len(calls) == 2 and "selection_error" in calls[1]
    assert selection.format_profile == "brief"
    assert {s["id"] for s in trace if s["origin"] == "user"} == {"report_writing", "source_priority"}
    assert trace[-1]["origin"] == "system"
    assert "report_formatting" in prompt


def test_auto_selection_cannot_stack_content_roles():
    async def model(*args):
        return json.dumps({"skill_ids": ["report_writing", "general_writing"], "format_profile": "academic", "reason": "bad"})
    with pytest.raises(ValueError, match="at most one"):
        asyncio.run(select_writing(model, "综述", {}))
