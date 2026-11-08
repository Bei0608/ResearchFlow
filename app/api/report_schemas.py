from datetime import datetime
from typing import Any, Literal

from app.api.schemas import APIModel


class AggregateMetricResponse(APIModel):
    source: Literal["program", "human"]
    namespace_key: str
    metric_key: str
    value: float | None
    sample_count: int
    missing_count: int
    pass_count: int | None
    pass_rate: float | None
    details: dict[str, Any]


class RunSummaryResponse(APIModel):
    schema_version: str
    calculated_at: datetime
    run: dict[str, Any]
    case_counts: dict[str, int]
    review_progress: dict[str, int | float]
    program_metrics: list[dict[str, Any]]
    human_metrics: list[dict[str, Any]]
    failed_cases: list[dict[str, Any]]
    cases: list[dict[str, Any]]
    gate: dict[str, Any] | None


class ReportResponse(APIModel):
    report_id: str
    run_id: str
    format: Literal["json", "html"]
    status: Literal["generating", "completed", "failed"]
    storage_path: str | None
    content_hash: str | None
    generated_at: datetime | None
    error: str | None
    created_by: str
    created_at: datetime
    content_url: str | None = None


class ReportListResponse(APIModel):
    reports: list[ReportResponse]
