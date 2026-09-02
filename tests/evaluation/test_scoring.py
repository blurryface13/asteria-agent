from asteria_researcher.evaluation.models import AgentRunOutput, EvalCase, EvalTask, SpanKind
from asteria_researcher.evaluation.scorers import pass_at_k, score_run, tool_scores
from asteria_researcher.evaluation.trace import TraceRecorder


def test_tool_scores_and_pass_k():
    precision, recall, f1 = tool_scores(["search"], ["search", "extra"])
    assert precision == 0.5 and recall == 1.0 and round(f1, 3) == 0.667
    case = EvalCase(case_id="c", prompt="x")
    task = EvalTask(task_id="t", name="t")
    output = AgentRunOutput(report="ok")
    first = score_run(task.task_id, case, output)
    second = score_run(task.task_id, case, AgentRunOutput(report=""), run_index=2)
    assert pass_at_k([first, second], 2) == 1.0
