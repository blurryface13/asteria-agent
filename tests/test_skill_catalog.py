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
        return json.dumps({"content_skill": "general_writing" if len(calls) == 1 else "report_writing",
                           "guidance_skills": [] if len(calls) == 1 else ["source_priority"],
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
        return json.dumps({"content_skill": "report_writing", "guidance_skills": ["general_writing"], "format_profile": "academic", "reason": "bad"})
    with pytest.raises(ValueError, match="only guidance"):
        asyncio.run(select_writing(model, "综述", {}))


def test_model_contract_separates_primary_skill_from_guidance():
    async def model(system, payload):
        schema = json.loads(system.split('Return ONLY JSON: ', 1)[1])
        assert schema['properties']['content_skill']['type'] == 'string'
        assert 'report_writing' in schema['properties']['content_skill']['enum']
        assert 'report_writing' not in schema['properties']['guidance_skills']['items']['enum']
        return json.dumps({'content_skill': 'report_writing', 'guidance_skills': ['source_priority'],
                           'format_profile': 'academic', 'reason': '单一综述结构与一手来源规范'})
    selection, _, _ = asyncio.run(select_writing(model, '综述', {}))
    assert selection.skill_ids == ['report_writing', 'source_priority']


def test_financial_writing_excludes_academic_attribution_guidance():
    async def model(system, payload):
        schema = json.loads(system.split('Return ONLY JSON: ', 1)[1])
        assert 'financial_report' in schema['properties']['content_skill']['enum']
        assert 'report_writing' not in schema['properties']['content_skill']['enum']
        assert 'source_priority' not in schema['properties']['guidance_skills']['items']['enum']
        return json.dumps({'content_skill': 'financial_report', 'guidance_skills': [],
                           'format_profile': 'brief', 'reason': '两份财报原文核对'})
    selection, prompt, trace = asyncio.run(select_writing(
        model, '对比两份独立的年度报告', {},
        SkillOptions(skill_ids=['financial_report'], format_profile='brief'),
        domain='financial_research'))
    assert selection.skill_ids == ['financial_report']
    assert "comparative column" in prompt
    assert not any(entry['id'] == 'source_priority' for entry in trace)
