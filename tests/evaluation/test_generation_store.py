from tempfile import TemporaryDirectory

from asteria_researcher.evaluation.generation import AlignmentChecker, preview_task
from asteria_researcher.evaluation.models import EvalTask, SeedCase
from asteria_researcher.evaluation.store import EvaluationStore


def test_store_upsert_and_preview():
    with TemporaryDirectory() as directory:
        store = EvaluationStore(directory)
        seed = SeedCase(seed_id="s", prompt="测试", dimensions=["input_quality.ambiguity"])
        store.upsert("seeds", seed)
        assert store.get("seeds", "s")["prompt"] == "测试"
        task = EvalTask(task_id="t", name="preview", seed_ids=["s"], dimensions=["input_quality.ambiguity"])
        preview = preview_task(task, [seed])
        assert preview["expected_generated_count"] == 10
        valid, errors = AlignmentChecker.check({"prompt": "p", "expected_behavior": "e", "dimensions": ["input_quality.ambiguity"], "tags": [], "metadata": {"seed_ids": ["s"]}}, dimension="input_quality.ambiguity", seed=seed)
        assert valid and not errors
