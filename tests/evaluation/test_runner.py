import asyncio
from tempfile import TemporaryDirectory

from asteria_researcher.evaluation.models import AgentRunOutput, EvalCase, EvalTask
from asteria_researcher.evaluation.runner import EvaluationRunner
from asteria_researcher.evaluation.store import EvaluationStore


def test_runner_persists_trace_and_report():
    async def executor(case, recorder):
        return AgentRunOutput(report=f"# {case.name or 'result'}\n\ncompleted")

    with TemporaryDirectory() as directory:
        store = EvaluationStore(directory)
        task = EvalTask(task_id="task", name="smoke", metadata={"repeats": 2})
        case = EvalCase(case_id="case", name="case", prompt="run")
        report = asyncio.run(EvaluationRunner(store, executor).run_task(task, [case]))
        assert report.result_count == 2
        assert report.pass_k == 1.0
        assert len(store.list("reports")) == 1
        assert len(store.list("traces")) == 2
