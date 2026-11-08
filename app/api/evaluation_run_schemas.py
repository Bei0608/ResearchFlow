from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.api.schemas import APIModel


class EvaluationRunCreate(APIModel):
    agent_version_id: str = Field(min_length=1, max_length=64)
    dataset_version_id: str = Field(min_length=1, max_length=64)
    trigger_type: str = Field(default="api", min_length=1, max_length=64)
    config_snapshot: dict[str, Any] = Field(min_length=1)
    git_commit: str | None = Field(default=None, min_length=1, max_length=128)


class EvaluationRunResponse(APIModel):
    run_id: str
    workspace_id: str
    agent_version_id: str
    dataset_version_id: str
    status: Literal["created", "running", "ready_for_review", "failed"]
    trigger_type: str
    config_snapshot: dict[str, Any]
    git_commit: str | None
    created_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


class EvaluationRunListResponse(APIModel):
    runs: list[EvaluationRunResponse]


class CaseResultResponse(APIModel):
    case_result_id: str
    run_id: str
    case_id: str
    status: Literal["succeeded", "failed", "skipped"]
    output: dict[str, Any]
    evidence: list[dict[str, Any]]
    trace: dict[str, Any]
    latency_ms: int | None
    token_usage: dict[str, Any]
    error: str | None
    created_at: datetime


class ProgramMetricResponse(APIModel):
    program_metric_id: str
    run_id: str
    case_result_id: str | None
    source: Literal["program"]
    evaluator_key: str
    evaluator_version: str
    metric_key: str
    value: float
    details: dict[str, Any]
    created_at: datetime


class EvaluationRunDetailResponse(APIModel):
    run: EvaluationRunResponse
    results: list[CaseResultResponse]
    metrics: list[ProgramMetricResponse]
