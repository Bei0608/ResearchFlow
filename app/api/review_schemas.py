from datetime import datetime
from typing import Literal

from pydantic import Field

from app.api.schemas import APIModel


class ReviewTaskCreate(APIModel):
    rubric_version_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    reviewer_id: str | None = Field(default=None, max_length=64)


class ReviewTaskResponse(APIModel):
    task_id: str
    run_id: str
    rubric_version_id: str
    name: str
    status: Literal["open", "completed"]
    assignment_id: str
    reviewer_id: str
    assignment_status: Literal["assigned", "in_progress", "completed"]
    created_by: str
    created_at: datetime
    completed_at: datetime | None
    total_count: int
    draft_count: int
    submitted_count: int
    pending_count: int


class ReviewTaskListResponse(APIModel):
    tasks: list[ReviewTaskResponse]


class ReviewScoreWrite(APIModel):
    criterion_id: str = Field(min_length=1, max_length=64)
    score: float
    comment: str = Field(default="", max_length=2000)


class ReviewWrite(APIModel):
    expected_revision: int = Field(ge=0)
    overall_comment: str = Field(default="", max_length=5000)
    reason: str | None = Field(default=None, max_length=1000)
    scores: list[ReviewScoreWrite] = Field(default_factory=list)


class StartRevisionRequest(APIModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class HumanScoreResponse(ReviewScoreWrite):
    pass


class ReviewRevisionResponse(APIModel):
    revision_id: str
    review_id: str
    revision: int
    status: Literal["draft", "submitted", "superseded"]
    overall_comment: str
    reason: str | None
    created_by: str
    created_at: datetime
    submitted_at: datetime | None
    scores: list[HumanScoreResponse]


class ReviewCriterionResponse(APIModel):
    criterion_id: str
    key: str
    title: str
    description: str
    min_score: float
    max_score: float
    weight: float
    required: bool


class ReviewCaseResponse(APIModel):
    review_id: str
    case_result_id: str
    external_id: str
    input: dict
    expected: dict
    output: dict
    evidence: list[dict]
    review_status: Literal["pending", "draft", "submitted"]
    latest_revision: int


class ReviewTaskDetailResponse(APIModel):
    task: ReviewTaskResponse
    cases: list[ReviewCaseResponse]
    criteria: list[ReviewCriterionResponse]


class ReviewCaseDetailResponse(APIModel):
    task: ReviewTaskResponse
    case: ReviewCaseResponse
    criteria: list[ReviewCriterionResponse]
    revisions: list[ReviewRevisionResponse]
    program_metrics: list[dict]
