"""Explicit, bounded live-model acceptance probes. No code execution or real edits.

python scripts/evaluate-collaboration.py --live [--case planning|coding|all]
The planning probe evaluates assignment quality, not finished research quality.
The coding probe reads a real local fixture and may read actual papers online.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asteria_researcher.agentic.autonomous import AutonomousReview, Action
from asteria_researcher.agentic.collaboration import (
    Assignment, allocation_report, AUDIT_PROMPT, DelegationAudit, validate_audit)


async def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.lab", override=True)
    from backend.server.agentic_runner import configured_model
    actual = configured_model()
    calls = 0
    async def model(system, user):
        nonlocal calls
        calls += 1
        if calls > 24:
            raise RuntimeError("验收模型调用已达到24次上限")
        try:
            return await actual(system, user)
        except Exception as error:
            failure = {"status": "blocked", "model_calls": calls,
                       "reason": "模型余额不足（HTTP 402）" if "402" in str(error) else type(error).__name__,
                       "note": "真实模型验收未完成，不计为通过；未自动切换模型。"}
            (folder / "summary.json").write_text(json.dumps({**summary, **failure}, ensure_ascii=False, indent=2))
            print(json.dumps({"folder": str(folder), **failure}, ensure_ascii=False))
            raise
    folder = ROOT / "outputs" / ("collaboration-eval-" + uuid4().hex[:10])
    folder.mkdir(parents=True)
    summary = {"time": datetime.now(timezone.utc).isoformat(), "mode": "live-model",
               "limitations": "分工测试不执行完整调研；代码场景只读本地夹具，不修改用户文件、不运行代码。", "cases": []}
    async def emit(*args, **kw):
        pass
    async def approve(_):
        raise ValueError("本验收不自动批准任何修改或执行")

    if args.case in {"planning", "all"}:
        r = AutonomousReview(model, None, emit, approve, folder, online_rag=False, max_actions=20)
        r.query = "围绕扩散模型图像水印写一份调研报告。请并行调查：方法如何嵌入和提取水印、面对图像编辑攻击的鲁棒性如何评估。两路不要重复讲方法大全，计算和数据需求可以由负责人保留后续调查。"
        r.plan = {"required_goals": [{"id": "g1", "description": "嵌入和提取机制"},
                                     {"id": "g2", "description": "编辑攻击下的鲁棒性评估"},
                                     {"id": "g3", "description": "计算和数据需求"}]}
        attempts, error = [], None
        for _ in range(3):
            raw = await r.llm(
                "You are the research Lead. Allocate complementary tasks based on user goals, not a fixed workflow. "
                "Use tool=delegate with 1-3 researcher assignments. Each needs name,objective,goal_ids,focus,expected_output,exclude. "
                "Declare retained_goal_ids for goals you will handle yourself. Do not confuse ownership with completed evidence. "
                "Respond to rejected allocation feedback by improving the actual objectives. Return ONLY JSON " + json.dumps(Action.model_json_schema()),
                {"task": r.query, "goals": r.plan["required_goals"], "previous_error": error})
            attempt = {"lead_response": raw}
            attempts.append(attempt)
            try:
                action = Action.model_validate_json(raw)
                if action.tool != "delegate" or any(a.role != "researcher" for a in action.assignments):
                    raise ValueError("本场景要求并行文献调查")
                attempt["allocation"] = allocation_report(action.assignments, ["g1", "g2", "g3"], action.retained_goal_ids)
                audit = DelegationAudit.model_validate_json(await r.llm(AUDIT_PROMPT + json.dumps(DelegationAudit.model_json_schema()),
                    {"task": r.query, "goals": r.plan["required_goals"], "assignments": [a.model_dump() for a in action.assignments],
                     "retained_goal_ids": action.retained_goal_ids}))
                attempt["audit"] = audit.model_dump()
                validate_audit(audit, action.assignments)
                attempt["status"] = "passed"
                error = None
                break
            except ValueError as exc:
                error = str(exc)[:1500]
                attempt.update(status="failed", error=error)
        (folder / "planning.json").write_text(json.dumps({"prompt": r.query, "attempts": attempts}, ensure_ascii=False, indent=2))
        summary["cases"].append({"case": "planning", "status": "passed" if error is None else "failed", "attempts": len(attempts)})

    if args.case in {"coding", "all"}:
        async def read(args):
            if args != {"name": "attention_demo.py"}:
                raise ValueError("本验收只能读取 attention_demo.py")
            return {"name": "attention_demo.py", "content": (ROOT / "tests/fixtures/attention_demo.py").read_text()}
        r = AutonomousReview(model, None, emit, approve, folder, online_rag=False, max_actions=30,
                              coding_tools={"read_workspace_file": ({"name": "attention_demo.py"}, read)})
        r.query = ("请检查 attention_demo.py 的注意力计算，和 Attention Is All You Need "
                   "（https://arxiv.org/abs/1706.03762）的定义是否一致。代码里好像缺了一个缩放因子，"
                   "我不确定理由，请先读文件；遇到论文原理疑问时请调研角色查原文解释，再回到代码给出修改建议。不要修改文件，也不要运行代码。")
        r.plan = {}
        a = Assignment(name="核对注意力实现", objective=r.query, role="coding", focus="缩放项及其原理",
                       expected_output="原文依据与代码修改建议；不执行")
        result = (await r.dispatch_assignments([a]))[0]
        requests = result.get("research_requests", [])
        ok = (result["status"] == "completed" and requests and any(q["status"] == "completed" for q in requests)
              and result["execution_performed"] is False)
        (folder / "coding.json").write_text(json.dumps({"prompt": r.query, "result": result}, ensure_ascii=False, indent=2))
        summary["cases"].append({"case": "coding", "status": "passed" if ok else "failed", "research_requests": len(requests),
                                 "note": "通过表示完成工具求助与回传；最终建议仍需人工核对。"})
    summary["model_calls"] = calls
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({"folder": str(folder), **summary}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="使用已配置真实模型，可能产生费用")
    parser.add_argument("--case", choices=("planning", "coding", "all"), default="all")
    args = parser.parse_args()
    if not args.live:
        parser.error("必须显式传入 --live；离线测试请使用 pytest tests/test_agentic_collaboration.py")
    asyncio.run(main(args))
