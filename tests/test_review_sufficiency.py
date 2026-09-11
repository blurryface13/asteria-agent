import asyncio
import json

import pytest

from asteria_researcher.agentic.autonomous import AutonomousReview
from asteria_researcher.agentic.sufficiency import (
    ReviewPlan, SufficiencyReport, evidence_catalog, validate_contract, validate_report,
    process_checks,
    ScopePartition, partition_contract,
)

URL = "https://arxiv.org/abs/1706.03762"
TEXT = "The method embeds a signature in the generated image."
GOALS = [{"id": "g1", "description": "比较注入方法", "user_quote": "比较注入方法"}]
EVIDENCE = [{"agent": "reader", "query": "method", "passages": [{"source": URL, "page": 3, "text": TEXT}]}]


def finding(catalog, status="supported"):
    return {"goals": [{"goal_id": "g1", "status": status, "reason": "原文描述了注入方式",
                       "supports": [{"evidence_id": next(iter(catalog)), "quote": TEXT}],
                       "gap": "" if status == "supported" else "缺少检测假设的原文证据"}],
            "optional_extensions": ["可以继续研究其他攻击，但不影响用户目标"],
            "synthesis": "注入方法的原文证据 " + URL}


def test_contract_requires_user_origin_and_unique_goal_ids():
    plan = ReviewPlan(scope="范围", perspectives=[{"name": "方法", "query": "方法"}], required_goals=GOALS)
    validate_contract(plan, "请比较注入方法")
    with pytest.raises(ValueError, match="引用用户"):
        validate_contract(plan, "随便研究一下")
    plan.required_goals.append(plan.required_goals[0])
    with pytest.raises(ValueError, match="重复"):
        validate_contract(plan, "请比较注入方法")


def test_delivery_goal_is_relocated_before_approval_without_dropping_requirements():
    plan = ReviewPlan(scope="范围", perspectives=[{"name": "方法", "query": "方法"}],
                      required_goals=GOALS + [{"id": "g2", "description": "写约2500字中文报告", "user_quote": "写约2500字"}])
    partition = ScopePartition(research_goal_ids=["g1"], delivery_goal_ids=["g2"])
    fixed = partition_contract(plan, partition)
    assert [g.id for g in fixed.required_goals] == ["g1"]
    assert fixed.delivery_constraints == ["写约2500字中文报告"]
    assert len(plan.required_goals) == 2
    with pytest.raises(ValueError, match="遗漏"):
        partition_contract(plan, ScopePartition(research_goal_ids=["g1"]))


def test_optional_expansion_never_blocks_supported_core():
    catalog = evidence_catalog(EVIDENCE, {URL})
    report = SufficiencyReport.model_validate(finding(catalog))
    assert validate_report(report, GOALS, catalog)
    report.goals[0].status, report.goals[0].gap = "partial", "需要补充证据"
    assert not validate_report(report, GOALS, catalog)


def test_shared_process_check_preserves_each_relocated_requirement():
    plan = ReviewPlan(scope="范围", perspectives=[{"name": "方法", "query": "方法"}],
                      required_goals=GOALS + [{"id": "g2", "description": "追踪关键论文书目", "user_quote": "追踪关键论文书目"}],
                      process_requirements=[{"id": "p1", "kind": "reference_tracing",
                                             "description": "追踪基础文献", "user_quote": "追踪基础文献"}])
    fixed = partition_contract(plan, ScopePartition(research_goal_ids=["g1"],
                               process_goals=[{"goal_id": "g2", "kind": "reference_tracing"}]))
    assert fixed.process_requirements[0].related_goals[0].id == "g2"
    assert fixed.process_requirements[0].description == "追踪基础文献"
    validate_contract(fixed, "比较注入方法，追踪基础文献，追踪关键论文书目")
    assert not plan.process_requirements[0].related_goals


def test_server_attaches_exact_source_text_for_selected_evidence_id():
    catalog = evidence_catalog(EVIDENCE, {URL})
    data = finding(catalog)
    data["goals"][0]["supports"][0].pop("quote")
    report = SufficiencyReport.model_validate(data)
    assert validate_report(report, GOALS, catalog)
    assert report.goals[0].supports[0].quote == TEXT


@pytest.mark.parametrize("mutation", ["invent_goal", "invent_evidence", "invent_quote", "empty_support", "hidden_gap"])
def test_assessor_cannot_fake_completion(mutation):
    catalog = evidence_catalog(EVIDENCE, {URL})
    report = SufficiencyReport.model_validate(finding(catalog))
    goal = report.goals[0]
    if mutation == "invent_goal": goal.goal_id = "g2"
    if mutation == "invent_evidence": goal.supports[0].evidence_id = "e_fake"
    if mutation == "invent_quote": goal.supports[0].quote = "An imaginary claim not present in any paper."
    if mutation == "empty_support": goal.supports = []
    if mutation == "hidden_gap": goal.gap = "Still missing a required experiment"
    with pytest.raises(ValueError):
        validate_report(report, GOALS, catalog)


def test_unread_sources_cannot_enter_assessor_evidence():
    assert not evidence_catalog(EVIDENCE, set())


def test_process_requirements_need_real_discovery_and_verified_edges():
    requirements = [{"id": "p1", "kind": "autonomous_discovery"}, {"id": "p2", "kind": "reference_tracing"}]
    checks = process_checks(requirements, searches=2, edges=0)
    assert checks[0]["supported"] and not checks[1]["supported"]
    assert all(c["supported"] for c in process_checks(requirements, searches=2, edges=1))


def runtime(tmp_path, model):
    async def emit(*args): pass
    review = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    review.query = "比较注入方法"
    review.plan = {"scope": "比较注入方法", "required_goals": GOALS, "optional_extensions": []}
    review.library.papers[URL] = {}
    review.evidence = EVIDENCE.copy()
    return review


def test_independent_assessor_stops_lead_before_optional_delegation(tmp_path):
    seen = []
    async def model(system, payload):
        data = json.loads(payload)
        seen.append(data)
        assert "objective" not in data and "observations" not in data
        assert "independent research sufficiency assessor" in system
        return json.dumps(finding({e["id"]: e for e in data["evidence"]}))
    review = runtime(tmp_path, model)
    result = asyncio.run(review.loop("lead", "再研究额外方向", lead=True))
    assert result["status"] == "completed" and review.children == 0
    assert len(seen) == 1 and (review.folder / "sufficiency.json").exists()


def test_no_new_evidence_stops_repeated_followups_and_caches_assessment(tmp_path):
    calls = []
    async def model(system, payload):
        calls.append(payload)
        data = json.loads(payload)
        return json.dumps(finding({e["id"]: e for e in data["evidence"]}, "partial"))
    review = runtime(tmp_path, model)
    async def check():
        assert await review.lead_checkpoint() is None
        review.actions += 3
        assert await review.lead_checkpoint() is None
        review.actions += 3
        return await review.lead_checkpoint()
    result = asyncio.run(check())
    assert result["status"] == "incomplete" and "新证据" in result["summary"]
    assert len(calls) == 1


def test_invalid_assessment_is_repaired_not_accepted(tmp_path):
    calls = []
    async def model(system, payload):
        data = json.loads(payload)
        calls.append(data)
        result = finding({e["id"]: e for e in data["evidence"]})
        if len(calls) == 1:
            result["goals"][0]["supports"][0]["quote"] = "Fabricated evidence quotation"
        return json.dumps(result)
    review = runtime(tmp_path, model)
    assert asyncio.run(review.assess_sufficiency())["ready"]
    assert len(calls) == 2 and "validation_error" in calls[1]


def test_missing_process_requirement_blocks_then_rechecks_after_actual_progress(tmp_path):
    async def model(system, payload):
        data = json.loads(payload)
        return json.dumps(finding({e["id"]: e for e in data["evidence"]}))
    review = runtime(tmp_path, model)
    review.plan["process_requirements"] = [{"id": "p1", "kind": "autonomous_discovery"}]
    async def check():
        assert await review.lead_checkpoint() is None
        review.successful_searches = 1
        return await review.lead_checkpoint()
    assert asyncio.run(check())["status"] == "completed"
    assert len(review.assessments) == 2
