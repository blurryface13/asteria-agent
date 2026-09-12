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


def test_reclassified_plan_can_be_loaded_from_its_saved_json():
    plan = ReviewPlan(scope="范围", perspectives=[{"name": "方法", "query": "方法"}],
        required_goals=GOALS + [{"id": "g2", "description": "中文简报", "user_quote": "中文简报"}],
        delivery_constraints=[f"约束{i}" for i in range(8)])
    fixed = partition_contract(plan, ScopePartition(research_goal_ids=["g1"], delivery_goal_ids=["g2"]))
    assert len(ReviewPlan.model_validate_json(fixed.model_dump_json()).delivery_constraints) == 9


def test_negated_process_moves_to_constraint_without_becoming_required_search():
    plan = ReviewPlan(scope="范围", perspectives=[{"name": "方法", "query": "方法"}],
        required_goals=GOALS, process_requirements=[{"id": "p1", "kind": "autonomous_discovery",
            "description": "仅用给定论文", "user_quote": "无需检索其他论文"}])
    fixed = partition_contract(plan, ScopePartition(research_goal_ids=["g1"], process_constraint_ids=["p1"]))
    assert not fixed.process_requirements
    assert "无需检索其他论文" in fixed.delivery_constraints
    assert not process_checks([], searches=0, edges=0)
    assert len(plan.process_requirements) == 1
    with pytest.raises(ValueError, match="过程"):
        partition_contract(plan, ScopePartition(research_goal_ids=["g1"], process_constraint_ids=["p2"]))


def test_partition_retries_invalid_ids_without_silently_dropping_goals(tmp_path):
    requests = []
    async def model(system, payload):
        requests.append(json.loads(payload))
        return json.dumps({"research_goal_ids": ["g9"] if len(requests) == 1 else ["g1"]})
    async def emit(*args, **kwargs):
        pass
    runtime = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    plan = ReviewPlan(scope="范围", perspectives=[{"name": "方法", "query": "方法"}], required_goals=GOALS)
    fixed = asyncio.run(runtime.partition_with_contract(plan, "请比较注入方法"))
    assert fixed.required_goals == plan.required_goals
    assert len(requests) == 2 and requests[1]["required_id_set"] == ["g1"]


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


def test_planner_contract_gets_one_explicit_repair_turn(tmp_path):
    task = "请比较注入方法并总结实验结论"
    invalid = {"scope": task, "perspectives": [{"name": "方法", "query": "方法"}],
               "required_goals": [
                   {"id": "g1", "description": "比较注入方法", "user_quote": "比较注入方法"},
                   {"id": "g1", "description": "总结实验结论", "user_quote": "总结实验结论"}],
               "process_requirements": [], "delivery_constraints": [], "optional_extensions": []}
    repaired = {**invalid, "required_goals": [
        invalid["required_goals"][0], {**invalid["required_goals"][1], "id": "g2"}]}
    calls = []

    async def model(system, payload):
        calls.append(payload)
        return json.dumps(invalid if len(calls) == 1 else repaired, ensure_ascii=False)

    async def emit(*args, **kwargs):
        pass

    review = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    review.query = task
    plan = asyncio.run(review.plan_with_contract("plan", {"task": task}, task, "initial"))
    assert [goal.id for goal in plan.required_goals] == ["g1", "g2"]
    assert len(calls) == 2


def test_planner_contract_repairs_duplicate_ids_when_model_repeats_candidate(tmp_path):
    task = "请比较注入方法并总结实验结论"
    invalid = {"scope": task, "perspectives": [{"name": "方法", "query": "方法"}],
               "required_goals": [
                   {"id": "g1", "description": "比较注入方法", "user_quote": "比较注入方法"},
                   {"id": "g1", "description": "总结实验结论", "user_quote": "总结实验结论"}],
               "process_requirements": [], "delivery_constraints": [], "optional_extensions": []}
    calls = []

    async def model(system, payload):
        calls.append(payload)
        return json.dumps(invalid, ensure_ascii=False)

    async def emit(*args, **kwargs):
        pass

    review = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    review.query = task
    plan = asyncio.run(review.plan_with_contract("plan", {"task": task}, task, "initial"))
    assert [goal.id for goal in plan.required_goals] == ["g1", "g2"]
    assert len(calls) == 2


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


def test_assessor_does_not_receive_planner_expanded_chapter_requirements(tmp_path):
    seen = []
    async def model(system, payload):
        seen.append((system, json.loads(payload)))
        return json.dumps(finding(evidence_catalog(EVIDENCE, {URL})))
    async def emit(*args, **kwargs):
        pass
    runtime = AutonomousReview(model, None, emit, None, tmp_path, online_rag=False)
    runtime.query = "比较注入方法"
    runtime.plan = {"required_goals": GOALS, "scope": "必须有独立局限章节",
                    "perspectives": [{"name": "必须一视角一章", "query": "不限扩展"}],
                    "optional_extensions": ["补足一百篇"], "delivery_constraints": ["仅基于指定原文"]}
    runtime.library.papers[URL] = {}
    runtime.evidence = EVIDENCE
    result = asyncio.run(runtime.assess_sufficiency())
    assert result["ready"]
    assert "scope" not in seen[0][1] and "perspectives" not in seen[0][1]
    assert seen[0][1]["constraints"] == ["仅基于指定原文"]
    assert "same-named section" in seen[0][0]


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
    assert len(calls) == 2  # Initial review + one semantic review, cached thereafter.


def test_semantic_review_can_correct_format_only_gap(tmp_path):
    calls = []
    async def model(system, payload):
        data = json.loads(payload)
        calls.append(data)
        result = finding({e["id"]: e for e in data["evidence"]})
        if "candidate_assessment" not in data:
            result["goals"][0].update(status="partial", gap="没有独立方法章节")
        else:
            assert data["candidate_assessment"]["goals"][0]["gap"] == "没有独立方法章节"
            assert "不是替研究者争取通过" in system
        return json.dumps(result)
    review = runtime(tmp_path, model)
    result = asyncio.run(review.assess_sufficiency())
    assert result["ready"] and result["semantic_review"] and len(calls) == 2
    assert (review.folder / "assessment-1-review-attempt-1.json").exists()


def test_semantic_review_cannot_invent_support_to_release_task(tmp_path):
    calls = []
    async def model(system, payload):
        data = json.loads(payload)
        calls.append(data)
        result = finding({e["id"]: e for e in data["evidence"]}, "partial")
        if "candidate_assessment" in data:
            result["goals"][0].update(status="supported", gap="")
            result["goals"][0]["supports"] = [{"evidence_id": "e_invented"}]
        return json.dumps(result)
    review = runtime(tmp_path, model)
    with pytest.raises(ValueError, match="证据校验"):
        asyncio.run(review.assess_sufficiency())
    assert len(calls) == 3 and not review.assessments


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


def test_qualified_inference_needs_premises_reasoning_and_qualification():
    catalog = evidence_catalog(EVIDENCE, {URL})
    data = finding(catalog)
    data["goals"][0].update(answer_kind="inference", answer="限定推断", reasoning="由原文前提推导", qualification="尚未实测")
    report = SufficiencyReport.model_validate(data)
    assert validate_report(report, GOALS, catalog)
    report.goals[0].qualification = ""
    with pytest.raises(ValueError, match="限定"):
        validate_report(report, GOALS, catalog)
    report.goals[0].answer_kind = "unknown"
    with pytest.raises(ValueError, match="未知"):
        validate_report(report, GOALS, catalog)


def test_rejected_goal_limit_survives_new_passages_but_never_forces_success(tmp_path):
    calls = []
    async def model(system, payload):
        data = json.loads(payload)
        calls.append(data)
        assert "answer_kind" in system and "inference" in system
        result = finding({e["id"]: e for e in data["evidence"]}, "partial")
        # Let the runtime bind the exact current passage rather than copying old text.
        result["goals"][0]["supports"][0].pop("quote")
        return json.dumps(result)
    review = runtime(tmp_path, model)
    async def check():
        for i in range(3):
            review.evidence = [{"agent": "reader", "query": "method", "passages": [
                {"source": URL, "page": i + 1, "text": TEXT + str(i)}]}]
            result = await review.lead_checkpoint()
            if i < 2:
                assert result is None
        return result
    result = asyncio.run(check())
    assert result["status"] == "incomplete" and "连续 3 轮" in result["summary"]
    assert len(calls) == 6  # Each fresh evidence snapshot has only one semantic review.
    assert not review.assessments[-1]["ready"]


def test_success_at_rejection_boundary_is_not_blocked(tmp_path):
    async def model(system, payload):
        data = json.loads(payload)
        return json.dumps(finding({e["id"]: e for e in data["evidence"]}))
    review = runtime(tmp_path, model)
    partial = finding(evidence_catalog(EVIDENCE, {URL}), "partial")
    review.assessments = [partial, partial]
    assert asyncio.run(review.lead_checkpoint())["status"] == "completed"
