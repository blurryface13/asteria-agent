import asyncio

import pytest
from fastapi import HTTPException

from backend.evaluation.routes import TaskRunRequest, run_task


def test_current_evaluation_does_not_silently_run_legacy_workflow():
    assert TaskRunRequest().variant == "current"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_task("unused", TaskRunRequest(), "admin@example.com"))
    assert exc.value.status_code == 501
    assert "Coordinator" in exc.value.detail


def test_legacy_workflow_must_be_named_explicitly():
    assert TaskRunRequest(variant="basic").variant == "basic"
