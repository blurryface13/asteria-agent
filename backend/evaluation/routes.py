"""GoodQuestion-inspired evaluation asset and regression API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from asteria_researcher.evaluation.badcase import BadCaseAnalyzer, DimensionCatalog, trace_to_seed
from asteria_researcher.evaluation.generation import TaskGenerator, preview_task
from asteria_researcher.evaluation.models import BadCase, BadCaseStatus, EvalCase, EvalTask, GeneratedCase, SeedCase, TraceEnvelope
from asteria_researcher.evaluation.store import EvaluationStore
from asteria_researcher.evaluation.trace import TraceIngestor
from asteria_researcher.evaluation.asteria_executor import build_asteria_executor
from asteria_researcher.evaluation.runner import EvaluationRunner
from backend.auth.dependencies import get_current_user_email

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])
store = EvaluationStore()


class TraceImportRequest(BaseModel):
    content: str = Field(min_length=1)
    batch_id: str | None = None
    source_system: str = "manual"


class TaskCreateRequest(BaseModel):
    name: str
    case_ids: list[str] = Field(default_factory=list)
    seed_ids: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    generation_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskRunRequest(BaseModel):
    variant: str = "basic"


class ReviewRequest(BaseModel):
    status: str
    note: str = ""


class TaskGenerateRequest(BaseModel):
    responses: list[str] | None = None


@router.get("/health")
async def health(_email: str = Depends(get_current_user_email)):
    return {"status": "ok", "store": str(store.root)}


@router.get("/dimensions")
async def dimensions(_email: str = Depends(get_current_user_email)):
    return {"dimensions": [item.__dict__ for item in DimensionCatalog.all()]}


@router.post("/traces/import")
async def import_traces(request: TraceImportRequest, _email: str = Depends(get_current_user_email)):
    try:
        traces = TraceIngestor().ingest_jsonl(request.content, batch_id=request.batch_id, source_system=request.source_system)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for trace in traces:
        store.upsert("traces", trace)
    return {"count": len(traces), "traces": [trace.model_dump(mode="json") for trace in traces]}


@router.post("/traces/import-file")
async def import_trace_file(file: UploadFile = File(...), batch_id: str | None = None, _email: str = Depends(get_current_user_email)):
    content = (await file.read()).decode("utf-8")
    return await import_traces(TraceImportRequest(content=content, batch_id=batch_id, source_system=file.filename or "upload"), _email)


@router.get("/traces")
async def list_traces(limit: int = 100, _email: str = Depends(get_current_user_email)):
    return {"traces": store.list("traces", limit=max(1, min(limit, 1000)))}


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, _email: str = Depends(get_current_user_email)):
    trace = store.get("traces", trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="trace not found")
    return trace


@router.post("/badcases/from-trace/{trace_id}")
async def create_badcase(trace_id: str, _email: str = Depends(get_current_user_email)):
    raw = store.get("traces", trace_id)
    if not raw:
        raise HTTPException(status_code=404, detail="trace not found")
    badcase = BadCaseAnalyzer().analyze(TraceEnvelope.model_validate(raw))
    if not badcase:
        return {"created": False, "message": "no rule-based failure detected"}
    store.upsert("badcases", badcase)
    return {"created": True, "badcase": badcase.model_dump(mode="json")}


@router.get("/badcases")
async def list_badcases(limit: int = 100, _email: str = Depends(get_current_user_email)):
    return {"badcases": store.list("badcases", limit=max(1, min(limit, 1000)))}


@router.post("/seeds/from-badcase/{badcase_id}")
async def create_seed(badcase_id: str, _email: str = Depends(get_current_user_email)):
    raw = store.get("badcases", badcase_id)
    if not raw:
        raise HTTPException(status_code=404, detail="badcase not found")
    badcase = BadCase.model_validate(raw)
    seed = trace_to_seed(badcase)
    store.upsert("seeds", seed)
    return {"seed": seed.model_dump(mode="json")}


@router.patch("/badcases/{badcase_id}/review")
async def review_badcase(badcase_id: str, request: ReviewRequest, _email: str = Depends(get_current_user_email)):
    raw = store.get("badcases", badcase_id)
    if not raw:
        raise HTTPException(status_code=404, detail="badcase not found")
    try:
        status = BadCaseStatus(request.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="status must be candidate/reviewed/accepted/rejected") from exc
    badcase = BadCase.model_validate(raw)
    badcase.status = status
    badcase.review_note = request.note
    badcase.reviewed_at = datetime.now(timezone.utc)
    store.upsert("badcases", badcase)
    return badcase.model_dump(mode="json")


@router.get("/seeds")
async def list_seeds(limit: int = 100, _email: str = Depends(get_current_user_email)):
    return {"seeds": store.list("seeds", limit=max(1, min(limit, 1000)))}


@router.post("/cases")
async def create_case(case: EvalCase, _email: str = Depends(get_current_user_email)):
    store.upsert("cases", case)
    return case.model_dump(mode="json")


@router.get("/cases")
async def list_cases(limit: int = 100, _email: str = Depends(get_current_user_email)):
    return {"cases": store.list("cases", limit=max(1, min(limit, 1000)))}


@router.get("/generated-cases")
async def list_generated_cases(limit: int = 100, _email: str = Depends(get_current_user_email)):
    return {"generated_cases": store.list("generated_cases", limit=max(1, min(limit, 1000)))}


@router.post("/tasks")
async def create_task(request: TaskCreateRequest, _email: str = Depends(get_current_user_email)):
    task = EvalTask(
        name=request.name, case_ids=request.case_ids, seed_ids=request.seed_ids,
        dimensions=request.dimensions, generation_config=request.generation_config,
        metadata=request.metadata,
    )
    store.upsert("tasks", task)
    return task.model_dump(mode="json")


@router.get("/tasks")
async def list_tasks(limit: int = 100, _email: str = Depends(get_current_user_email)):
    return {"tasks": store.list("tasks", limit=max(1, min(limit, 1000)))}


@router.get("/tasks/{task_id}/preview")
async def task_preview(task_id: str, _email: str = Depends(get_current_user_email)):
    raw = store.get("tasks", task_id)
    if not raw:
        raise HTTPException(status_code=404, detail="task not found")
    task = EvalTask.model_validate(raw)
    seeds = [SeedCase.model_validate(item) for item in store.list("seeds") if item.get("seed_id") in task.seed_ids]
    cases = [EvalCase.model_validate(item) for item in store.list("cases") if item.get("case_id") in task.case_ids]
    return preview_task(task, seeds, cases)


@router.post("/tasks/{task_id}/generate")
async def generate_task(task_id: str, request: TaskGenerateRequest, _email: str = Depends(get_current_user_email)):
    raw = store.get("tasks", task_id)
    if not raw:
        raise HTTPException(status_code=404, detail="task not found")
    task = EvalTask.model_validate(raw)
    seeds = [SeedCase.model_validate(item) for item in store.list("seeds") if item.get("seed_id") in task.seed_ids]
    if not seeds:
        raise HTTPException(status_code=400, detail="task has no seeds")
    if request.responses:
        index = 0
        async def llm(_prompt: str) -> str:
            nonlocal index
            value = request.responses[index % len(request.responses)]
            index += 1
            return value
    else:
        from asteria_researcher.config.config import Config
        from asteria_researcher.utils.llm import create_chat_completion
        config = Config()
        async def llm(prompt: str) -> str:
            return await create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=task.generation_config.model or config.smart_llm_model,
                llm_provider=config.smart_llm_provider,
                temperature=task.generation_config.temperature,
                max_tokens=1200,
                llm_kwargs=config.llm_kwargs,
            )
    try:
        generated = await TaskGenerator(llm).generate(task, seeds)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"generation failed: {exc}") from exc
    for case in generated:
        store.upsert("generated_cases", case)
    task.generated_case_ids = [case.generated_id for case in generated]
    task.updated_at = datetime.now(timezone.utc)
    store.upsert("tasks", task)
    return {"count": len(generated), "generated_cases": [case.model_dump(mode="json") for case in generated]}


@router.patch("/generated-cases/{generated_id}/review")
async def review_generated_case(generated_id: str, request: ReviewRequest, _email: str = Depends(get_current_user_email)):
    raw = store.get("generated_cases", generated_id)
    if not raw:
        raise HTTPException(status_code=404, detail="generated case not found")
    if request.status not in {"pending", "passed", "rejected", "needs_review"}:
        raise HTTPException(status_code=400, detail="invalid generated case status")
    case = GeneratedCase.model_validate(raw)
    case.quality_status = request.status
    case.quality_note = request.note
    store.upsert("generated_cases", case)
    return case.model_dump(mode="json")


@router.get("/reports")
async def list_reports(limit: int = 100, _email: str = Depends(get_current_user_email)):
    return {"reports": store.list("reports", limit=max(1, min(limit, 1000)))}


@router.post("/tasks/{task_id}/run")
async def run_task(task_id: str, request: TaskRunRequest, _email: str = Depends(get_current_user_email)):
    raw = store.get("tasks", task_id)
    if not raw:
        raise HTTPException(status_code=404, detail="task not found")
    task = EvalTask.model_validate(raw)
    cases = [EvalCase.model_validate(item) for item in store.list("cases") if item.get("case_id") in task.case_ids]
    if not cases:
        raise HTTPException(status_code=400, detail="task has no executable cases")
    try:
        executor = build_asteria_executor(request.variant)
        report = await EvaluationRunner(store=store, executor=executor).run_task(task, cases)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return report.model_dump(mode="json")
