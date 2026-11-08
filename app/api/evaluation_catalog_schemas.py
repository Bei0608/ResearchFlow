from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.api.schemas import APIModel


Environment = Literal["demo", "test", "production"]
CatalogStatus = Literal["draft", "published", "archived"]


class NamedResourceCreate(APIModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1000)


class VersionCreate(APIModel):
    version: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    schema_version: str = Field(default="1.0", min_length=1, max_length=32)
    environment: Environment = "production"


class DatasetResponse(APIModel):
    dataset_id: str
    workspace_id: str
    name: str
    description: str
    created_by: str
    created_at: datetime


class DatasetListResponse(APIModel):
    datasets: list[DatasetResponse]


class DatasetVersionResponse(APIModel):
    dataset_version_id: str
    dataset_id: str
    version: str
    status: CatalogStatus
    schema_version: str
    environment: Environment
    content_hash: str | None
    created_by: str
    created_at: datetime
    published_at: datetime | None


class DatasetVersionListResponse(APIModel):
    versions: list[DatasetVersionResponse]


class EvaluationCaseWrite(APIModel):
    external_id: str = Field(min_length=1, max_length=128)
    input: dict[str, Any] = Field(min_length=1)
    expected: dict[str, Any] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationCaseResponse(EvaluationCaseWrite):
    case_id: str
    dataset_version_id: str
    created_at: datetime


class EvaluationCaseListResponse(APIModel):
    cases: list[EvaluationCaseResponse]


class RubricCreate(NamedResourceCreate):
    pass


class RubricResponse(APIModel):
    rubric_id: str
    workspace_id: str
    name: str
    description: str
    created_by: str
    created_at: datetime


class RubricListResponse(APIModel):
    rubrics: list[RubricResponse]


class RubricVersionCreate(VersionCreate):
    instructions: str = Field(min_length=1, max_length=5000)


class RubricVersionResponse(APIModel):
    rubric_version_id: str
    rubric_id: str
    version: str
    status: CatalogStatus
    schema_version: str
    environment: Environment
    instructions: str
    content_hash: str | None
    created_by: str
    created_at: datetime
    published_at: datetime | None


class RubricVersionListResponse(APIModel):
    versions: list[RubricVersionResponse]


class CriterionWrite(APIModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1000)
    min_score: float
    max_score: float
    weight: float = Field(gt=0)
    required: bool = True

    @model_validator(mode="after")
    def validate_range(self):
        if self.max_score <= self.min_score:
            raise ValueError("max_score必须大于min_score")
        return self


class CriterionResponse(CriterionWrite):
    criterion_id: str
    rubric_version_id: str
    created_at: datetime


class CriterionListResponse(APIModel):
    criteria: list[CriterionResponse]
