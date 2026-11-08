from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.api.schemas import APIModel


class BaselineSetRequest(APIModel):
    run_id: str = Field(min_length=1, max_length=64)


class BaselineResponse(APIModel):
    baseline_id: str
    application_id: str
    run_id: str
    active: bool
    activated_by: str
    activated_at: datetime
    deactivated_at: datetime | None


class GateRuleWrite(APIModel):
    rule_id: str = Field(min_length=1, max_length=128)
    source: Literal["program", "human"]
    namespace_key: str = Field(min_length=1, max_length=256)
    metric_key: str = Field(min_length=1, max_length=128)
    kind: Literal["absolute_min", "max_regression"]
    min_value: float | None = None
    max_drop: float | None = Field(default=None, ge=0)


class GatePolicyCreate(APIModel):
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    rules: list[GateRuleWrite] = Field(min_length=1)


class GatePolicyResponse(APIModel):
    policy_id: str
    workspace_id: str
    name: str
    version: str
    status: Literal["draft", "published"]
    rules: list[dict[str, Any]]
    created_by: str
    created_at: datetime
    published_at: datetime | None


class GatePolicyListResponse(APIModel):
    policies: list[GatePolicyResponse]


class GateEvaluationRequest(APIModel):
    policy_id: str = Field(min_length=1, max_length=64)


class GateEvaluationResponse(APIModel):
    gate_evaluation_id: str
    run_id: str
    baseline_run_id: str | None
    policy_id: str
    status: Literal["passed", "failed", "incomplete"]
    results: dict[str, Any]
    evaluated_by: str
    evaluated_at: datetime


class GateEvaluationListResponse(APIModel):
    evaluations: list[GateEvaluationResponse]
