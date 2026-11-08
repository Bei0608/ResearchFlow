from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from threading import RLock
from typing import Any, Literal, Protocol
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.memory.checkpointer import get_postgres_pool
from app.workspaces import WorkspaceRepository


CatalogStatus = Literal["draft", "published", "archived"]
Environment = Literal["demo", "test", "production"]


class DuplicateCatalogError(ValueError):
    pass


class ImmutableCatalogError(ValueError):
    pass


class CatalogValidationError(ValueError):
    pass


class DuplicateContentError(ValueError):
    pass


@dataclass(frozen=True)
class DatasetRecord:
    dataset_id: str
    workspace_id: str
    name: str
    description: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class DatasetVersionRecord:
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


@dataclass(frozen=True)
class EvaluationCaseRecord:
    case_id: str
    dataset_version_id: str
    external_id: str
    input_json: dict[str, Any]
    expected_json: dict[str, Any]
    metadata_json: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class RubricRecord:
    rubric_id: str
    workspace_id: str
    name: str
    description: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class RubricVersionRecord:
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


@dataclass(frozen=True)
class CriterionRecord:
    criterion_id: str
    rubric_version_id: str
    key: str
    title: str
    description: str
    min_score: float
    max_score: float
    weight: float
    required: bool
    created_at: datetime


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dataset_content_hash(cases: list[EvaluationCaseRecord]) -> str:
    payload = [
        {
            "external_id": item.external_id,
            "input": item.input_json,
            "expected": item.expected_json,
            "metadata": item.metadata_json,
        }
        for item in sorted(cases, key=lambda row: row.external_id)
    ]
    return _canonical_hash(payload)


def rubric_content_hash(
    instructions: str,
    criteria: list[CriterionRecord],
) -> str:
    payload = {
        "instructions": instructions,
        "criteria": [
            {
                "key": item.key,
                "title": item.title,
                "description": item.description,
                "min_score": item.min_score,
                "max_score": item.max_score,
                "weight": item.weight,
                "required": item.required,
            }
            for item in sorted(criteria, key=lambda row: row.key)
        ],
    }
    return _canonical_hash(payload)


def validate_dataset_for_publish(cases: list[EvaluationCaseRecord]) -> None:
    if not cases:
        raise CatalogValidationError("评测集至少需要一个案例")
    for item in cases:
        if not item.external_id.strip():
            raise CatalogValidationError("案例external_id不能为空")
        if not item.input_json:
            raise CatalogValidationError(
                f"案例{item.external_id}的input不能为空"
            )
        if not item.expected_json:
            raise CatalogValidationError(
                f"案例{item.external_id}的expected不能为空"
            )


def validate_rubric_for_publish(
    instructions: str,
    criteria: list[CriterionRecord],
) -> None:
    if not instructions.strip():
        raise CatalogValidationError("量表instructions不能为空")
    if not criteria:
        raise CatalogValidationError("量表至少需要一个评分准则")
    for item in criteria:
        if item.max_score <= item.min_score:
            raise CatalogValidationError(
                f"准则{item.key}的max_score必须大于min_score"
            )
        if item.weight <= 0:
            raise CatalogValidationError(f"准则{item.key}的weight必须大于0")
    if abs(sum(item.weight for item in criteria) - 1.0) > 1e-6:
        raise CatalogValidationError("量表准则weight之和必须为1")


class EvaluationCatalogRepository(Protocol):
    def create_dataset(self, **kwargs: Any) -> DatasetRecord | None: ...
    def list_datasets(self, workspace_id: str, user_id: str) -> list[DatasetRecord]: ...
    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetRecord | None: ...
    def create_dataset_version(self, **kwargs: Any) -> DatasetVersionRecord | None: ...
    def list_dataset_versions(self, dataset_id: str, user_id: str) -> list[DatasetVersionRecord]: ...
    def get_dataset_version(self, dataset_id: str, version_id: str, user_id: str) -> DatasetVersionRecord | None: ...
    def find_dataset_version_by_hash(self, dataset_id: str, content_hash: str, user_id: str) -> DatasetVersionRecord | None: ...
    def add_case(self, **kwargs: Any) -> EvaluationCaseRecord | None: ...
    def update_case(self, **kwargs: Any) -> EvaluationCaseRecord | None: ...
    def delete_case(self, dataset_id: str, version_id: str, case_id: str, user_id: str) -> bool: ...
    def list_cases(self, dataset_id: str, version_id: str, user_id: str) -> list[EvaluationCaseRecord]: ...
    def publish_dataset_version(self, dataset_id: str, version_id: str, user_id: str) -> DatasetVersionRecord | None: ...
    def create_rubric(self, **kwargs: Any) -> RubricRecord | None: ...
    def list_rubrics(self, workspace_id: str, user_id: str) -> list[RubricRecord]: ...
    def get_rubric(self, rubric_id: str, user_id: str) -> RubricRecord | None: ...
    def create_rubric_version(self, **kwargs: Any) -> RubricVersionRecord | None: ...
    def list_rubric_versions(self, rubric_id: str, user_id: str) -> list[RubricVersionRecord]: ...
    def get_rubric_version(self, rubric_id: str, version_id: str, user_id: str) -> RubricVersionRecord | None: ...
    def find_rubric_version_by_hash(self, rubric_id: str, content_hash: str, user_id: str) -> RubricVersionRecord | None: ...
    def add_criterion(self, **kwargs: Any) -> CriterionRecord | None: ...
    def update_criterion(self, **kwargs: Any) -> CriterionRecord | None: ...
    def delete_criterion(self, rubric_id: str, version_id: str, criterion_id: str, user_id: str) -> bool: ...
    def list_criteria(self, rubric_id: str, version_id: str, user_id: str) -> list[CriterionRecord]: ...
    def publish_rubric_version(self, rubric_id: str, version_id: str, user_id: str) -> RubricVersionRecord | None: ...


class PostgresEvaluationCatalogRepository:
    def __init__(self) -> None:
        self._pool = get_postgres_pool()

    @staticmethod
    def _dataset(row: dict | None) -> DatasetRecord | None:
        return DatasetRecord(**row) if row else None

    @staticmethod
    def _dataset_version(row: dict | None) -> DatasetVersionRecord | None:
        return DatasetVersionRecord(**row) if row else None

    @staticmethod
    def _case(row: dict | None) -> EvaluationCaseRecord | None:
        if not row:
            return None
        return EvaluationCaseRecord(
            **{**row, "input_json": dict(row["input_json"]),
               "expected_json": dict(row["expected_json"]),
               "metadata_json": dict(row["metadata_json"])}
        )

    @staticmethod
    def _rubric(row: dict | None) -> RubricRecord | None:
        return RubricRecord(**row) if row else None

    @staticmethod
    def _rubric_version(row: dict | None) -> RubricVersionRecord | None:
        return RubricVersionRecord(**row) if row else None

    @staticmethod
    def _criterion(row: dict | None) -> CriterionRecord | None:
        if not row:
            return None
        return CriterionRecord(
            criterion_id=row["criterion_id"],
            rubric_version_id=row["rubric_version_id"],
            key=row["criterion_key"], title=row["title"],
            description=row["description"],
            min_score=float(row["min_score"]), max_score=float(row["max_score"]),
            weight=float(row["weight"]), required=row["required"],
            created_at=row["created_at"],
        )

    def create_dataset(self, *, workspace_id: str, user_id: str, name: str, description: str) -> DatasetRecord | None:
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO researchflow_evaluation_datasets
                    (dataset_id, workspace_id, name, description, created_by)
                    SELECT %s,%s,%s,%s,%s WHERE EXISTS (SELECT 1 FROM
                    researchflow_workspace_members WHERE workspace_id=%s AND user_id=%s AND role='owner')
                    RETURNING dataset_id,workspace_id,name,description,created_by,created_at""",
                    (uuid4().hex, workspace_id, name, description, user_id, workspace_id, user_id))
                return self._dataset(cur.fetchone())
        except UniqueViolation as exc:
            raise DuplicateCatalogError("Workspace中已存在同名评测集") from exc

    def list_datasets(self, workspace_id: str, user_id: str) -> list[DatasetRecord]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT d.dataset_id,d.workspace_id,d.name,d.description,d.created_by,d.created_at
                FROM researchflow_evaluation_datasets d JOIN researchflow_workspace_members m
                ON m.workspace_id=d.workspace_id WHERE d.workspace_id=%s AND m.user_id=%s
                ORDER BY d.created_at,d.dataset_id""", (workspace_id, user_id))
            return [self._dataset(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT d.dataset_id,d.workspace_id,d.name,d.description,d.created_by,d.created_at
                FROM researchflow_evaluation_datasets d JOIN researchflow_workspace_members m
                ON m.workspace_id=d.workspace_id WHERE d.dataset_id=%s AND m.user_id=%s""", (dataset_id, user_id))
            return self._dataset(cur.fetchone())

    def create_dataset_version(self, *, dataset_id: str, user_id: str, version: str, schema_version: str, environment: Environment) -> DatasetVersionRecord | None:
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO researchflow_evaluation_dataset_versions
                    (dataset_version_id,dataset_id,version,schema_version,environment,created_by)
                    SELECT %s,d.dataset_id,%s,%s,%s,%s FROM researchflow_evaluation_datasets d
                    JOIN researchflow_workspace_members m ON m.workspace_id=d.workspace_id
                    WHERE d.dataset_id=%s AND m.user_id=%s AND m.role='owner'
                    RETURNING dataset_version_id,dataset_id,version,status,schema_version,environment,content_hash,created_by,created_at,published_at""",
                    (uuid4().hex, version, schema_version, environment, user_id, dataset_id, user_id))
                return self._dataset_version(cur.fetchone())
        except UniqueViolation as exc:
            raise DuplicateCatalogError("评测集中已存在相同版本号") from exc

    def list_dataset_versions(self, dataset_id: str, user_id: str) -> list[DatasetVersionRecord]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT v.dataset_version_id,v.dataset_id,v.version,v.status,v.schema_version,v.environment,v.content_hash,v.created_by,v.created_at,v.published_at
                FROM researchflow_evaluation_dataset_versions v JOIN researchflow_evaluation_datasets d ON d.dataset_id=v.dataset_id
                JOIN researchflow_workspace_members m ON m.workspace_id=d.workspace_id WHERE v.dataset_id=%s AND m.user_id=%s ORDER BY v.created_at,v.dataset_version_id""", (dataset_id,user_id))
            return [self._dataset_version(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def get_dataset_version(self, dataset_id: str, version_id: str, user_id: str) -> DatasetVersionRecord | None:
        return next((v for v in self.list_dataset_versions(dataset_id,user_id) if v.dataset_version_id == version_id), None)

    def find_dataset_version_by_hash(self, dataset_id: str, content_hash: str, user_id: str) -> DatasetVersionRecord | None:
        return next((v for v in self.list_dataset_versions(dataset_id,user_id) if v.content_hash == content_hash), None)

    def _owned_dataset_version(self, dataset_id: str, version_id: str, user_id: str) -> DatasetVersionRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT v.dataset_version_id,v.dataset_id,v.version,v.status,v.schema_version,v.environment,v.content_hash,v.created_by,v.created_at,v.published_at
                FROM researchflow_evaluation_dataset_versions v JOIN researchflow_evaluation_datasets d ON d.dataset_id=v.dataset_id
                JOIN researchflow_workspace_members m ON m.workspace_id=d.workspace_id
                WHERE v.dataset_id=%s AND v.dataset_version_id=%s AND m.user_id=%s AND m.role='owner'""", (dataset_id,version_id,user_id))
            return self._dataset_version(cur.fetchone())

    def add_case(self, *, dataset_id: str, version_id: str, user_id: str, external_id: str, input_json: dict, expected_json: dict, metadata_json: dict) -> EvaluationCaseRecord | None:
        current = self._owned_dataset_version(dataset_id,version_id,user_id)
        if current and current.status != "draft": raise ImmutableCatalogError("已发布评测集版本不可修改")
        if current is None:
            return None
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO researchflow_evaluation_cases (case_id,dataset_version_id,external_id,input_json,expected_json,metadata_json)
                    SELECT %s,%s,%s,%s,%s,%s WHERE EXISTS (SELECT 1 FROM researchflow_evaluation_dataset_versions WHERE dataset_version_id=%s AND dataset_id=%s AND status='draft')
                    RETURNING case_id,dataset_version_id,external_id,input_json,expected_json,metadata_json,created_at""",
                    (uuid4().hex,version_id,external_id,Jsonb(input_json),Jsonb(expected_json),Jsonb(metadata_json),version_id,dataset_id))
                return self._case(cur.fetchone())
        except UniqueViolation as exc: raise DuplicateCatalogError("版本中已存在相同external_id") from exc

    def list_cases(self, dataset_id: str, version_id: str, user_id: str) -> list[EvaluationCaseRecord]:
        if not self.get_dataset_version(dataset_id,version_id,user_id): return []
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT case_id,dataset_version_id,external_id,input_json,expected_json,metadata_json,created_at FROM researchflow_evaluation_cases WHERE dataset_version_id=%s ORDER BY external_id,case_id""", (version_id,))
            return [self._case(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def update_case(self, *, dataset_id: str, version_id: str, case_id: str, user_id: str, external_id: str, input_json: dict, expected_json: dict, metadata_json: dict) -> EvaluationCaseRecord | None:
        current = self._owned_dataset_version(dataset_id,version_id,user_id)
        if current and current.status != "draft": raise ImmutableCatalogError("已发布评测集版本不可修改")
        if not current: return None
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("""UPDATE researchflow_evaluation_cases SET external_id=%s,input_json=%s,expected_json=%s,metadata_json=%s
                    WHERE case_id=%s AND dataset_version_id=%s RETURNING case_id,dataset_version_id,external_id,input_json,expected_json,metadata_json,created_at""",
                    (external_id,Jsonb(input_json),Jsonb(expected_json),Jsonb(metadata_json),case_id,version_id))
                return self._case(cur.fetchone())
        except UniqueViolation as exc: raise DuplicateCatalogError("版本中已存在相同external_id") from exc

    def delete_case(self, dataset_id: str, version_id: str, case_id: str, user_id: str) -> bool:
        current=self._owned_dataset_version(dataset_id,version_id,user_id)
        if current and current.status != "draft": raise ImmutableCatalogError("已发布评测集版本不可修改")
        if not current: return False
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM researchflow_evaluation_cases WHERE case_id=%s AND dataset_version_id=%s",(case_id,version_id)); return cur.rowcount == 1

    def publish_dataset_version(self, dataset_id: str, version_id: str, user_id: str) -> DatasetVersionRecord | None:
        current=self._owned_dataset_version(dataset_id,version_id,user_id)
        if not current or current.status == "published": return current
        cases=self.list_cases(dataset_id,version_id,user_id); validate_dataset_for_publish(cases); digest=dataset_content_hash(cases)
        if self.find_dataset_version_by_hash(dataset_id,digest,user_id): raise DuplicateContentError("相同内容的评测集版本已存在")
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE researchflow_evaluation_dataset_versions SET status='published',content_hash=%s,published_at=NOW()
                WHERE dataset_version_id=%s AND dataset_id=%s AND status='draft'
                RETURNING dataset_version_id,dataset_id,version,status,schema_version,environment,content_hash,created_by,created_at,published_at""",(digest,version_id,dataset_id))
            return self._dataset_version(cur.fetchone())

    def create_rubric(self, *, workspace_id: str, user_id: str, name: str, description: str) -> RubricRecord | None:
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO researchflow_rubrics (rubric_id,workspace_id,name,description,created_by)
                    SELECT %s,%s,%s,%s,%s WHERE EXISTS (SELECT 1 FROM researchflow_workspace_members WHERE workspace_id=%s AND user_id=%s AND role='owner')
                    RETURNING rubric_id,workspace_id,name,description,created_by,created_at""",(uuid4().hex,workspace_id,name,description,user_id,workspace_id,user_id)); return self._rubric(cur.fetchone())
        except UniqueViolation as exc: raise DuplicateCatalogError("Workspace中已存在同名量表") from exc

    def list_rubrics(self, workspace_id: str, user_id: str) -> list[RubricRecord]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT r.rubric_id,r.workspace_id,r.name,r.description,r.created_by,r.created_at FROM researchflow_rubrics r
                JOIN researchflow_workspace_members m ON m.workspace_id=r.workspace_id WHERE r.workspace_id=%s AND m.user_id=%s ORDER BY r.created_at,r.rubric_id""",(workspace_id,user_id)); return [self._rubric(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def get_rubric(self, rubric_id: str, user_id: str) -> RubricRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT r.rubric_id,r.workspace_id,r.name,r.description,r.created_by,r.created_at FROM researchflow_rubrics r
                JOIN researchflow_workspace_members m ON m.workspace_id=r.workspace_id WHERE r.rubric_id=%s AND m.user_id=%s""",(rubric_id,user_id)); return self._rubric(cur.fetchone())

    def create_rubric_version(self, *, rubric_id: str, user_id: str, version: str, schema_version: str, environment: Environment, instructions: str) -> RubricVersionRecord | None:
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO researchflow_rubric_versions (rubric_version_id,rubric_id,version,schema_version,environment,instructions,created_by)
                    SELECT %s,r.rubric_id,%s,%s,%s,%s,%s FROM researchflow_rubrics r JOIN researchflow_workspace_members m ON m.workspace_id=r.workspace_id
                    WHERE r.rubric_id=%s AND m.user_id=%s AND m.role='owner'
                    RETURNING rubric_version_id,rubric_id,version,status,schema_version,environment,instructions,content_hash,created_by,created_at,published_at""",
                    (uuid4().hex,version,schema_version,environment,instructions,user_id,rubric_id,user_id)); return self._rubric_version(cur.fetchone())
        except UniqueViolation as exc: raise DuplicateCatalogError("量表中已存在相同版本号") from exc

    def list_rubric_versions(self, rubric_id: str, user_id: str) -> list[RubricVersionRecord]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT v.rubric_version_id,v.rubric_id,v.version,v.status,v.schema_version,v.environment,v.instructions,v.content_hash,v.created_by,v.created_at,v.published_at
                FROM researchflow_rubric_versions v JOIN researchflow_rubrics r ON r.rubric_id=v.rubric_id JOIN researchflow_workspace_members m ON m.workspace_id=r.workspace_id
                WHERE v.rubric_id=%s AND m.user_id=%s ORDER BY v.created_at,v.rubric_version_id""",(rubric_id,user_id)); return [self._rubric_version(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def get_rubric_version(self,rubric_id:str,version_id:str,user_id:str)->RubricVersionRecord|None:
        return next((v for v in self.list_rubric_versions(rubric_id,user_id) if v.rubric_version_id==version_id),None)
    def find_rubric_version_by_hash(self,rubric_id:str,content_hash:str,user_id:str)->RubricVersionRecord|None:
        return next((v for v in self.list_rubric_versions(rubric_id,user_id) if v.content_hash==content_hash),None)
    def _owned_rubric_version(self,rubric_id:str,version_id:str,user_id:str)->RubricVersionRecord|None:
        rubric=self.get_rubric(rubric_id,user_id)
        if not rubric: return None
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT role FROM researchflow_workspace_members WHERE workspace_id=%s AND user_id=%s",(rubric.workspace_id,user_id)); row=cur.fetchone()
        return self.get_rubric_version(rubric_id,version_id,user_id) if row and row["role"]=="owner" else None

    def add_criterion(self, *, rubric_id:str,version_id:str,user_id:str,key:str,title:str,description:str,min_score:float,max_score:float,weight:float,required:bool)->CriterionRecord|None:
        current=self._owned_rubric_version(rubric_id,version_id,user_id)
        if current and current.status!="draft": raise ImmutableCatalogError("已发布量表版本不可修改")
        if not current:return None
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO researchflow_rubric_criteria (criterion_id,rubric_version_id,criterion_key,title,description,min_score,max_score,weight,required)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING criterion_id,rubric_version_id,criterion_key,title,description,min_score,max_score,weight,required,created_at""",
                    (uuid4().hex,version_id,key,title,description,min_score,max_score,weight,required));return self._criterion(cur.fetchone())
        except UniqueViolation as exc:raise DuplicateCatalogError("版本中已存在相同criterion key") from exc

    def list_criteria(self,rubric_id:str,version_id:str,user_id:str)->list[CriterionRecord]:
        if not self.get_rubric_version(rubric_id,version_id,user_id):return []
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT criterion_id,rubric_version_id,criterion_key,title,description,min_score,max_score,weight,required,created_at FROM researchflow_rubric_criteria WHERE rubric_version_id=%s ORDER BY criterion_key,criterion_id""",(version_id,));return [self._criterion(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def update_criterion(self, *, rubric_id:str,version_id:str,criterion_id:str,user_id:str,key:str,title:str,description:str,min_score:float,max_score:float,weight:float,required:bool)->CriterionRecord|None:
        current=self._owned_rubric_version(rubric_id,version_id,user_id)
        if current and current.status!="draft":raise ImmutableCatalogError("已发布量表版本不可修改")
        if not current:return None
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("""UPDATE researchflow_rubric_criteria SET criterion_key=%s,title=%s,description=%s,min_score=%s,max_score=%s,weight=%s,required=%s
                    WHERE criterion_id=%s AND rubric_version_id=%s RETURNING criterion_id,rubric_version_id,criterion_key,title,description,min_score,max_score,weight,required,created_at""",
                    (key,title,description,min_score,max_score,weight,required,criterion_id,version_id));return self._criterion(cur.fetchone())
        except UniqueViolation as exc:raise DuplicateCatalogError("版本中已存在相同criterion key") from exc

    def delete_criterion(self,rubric_id:str,version_id:str,criterion_id:str,user_id:str)->bool:
        current=self._owned_rubric_version(rubric_id,version_id,user_id)
        if current and current.status!="draft":raise ImmutableCatalogError("已发布量表版本不可修改")
        if not current:return False
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM researchflow_rubric_criteria WHERE criterion_id=%s AND rubric_version_id=%s",(criterion_id,version_id));return cur.rowcount==1

    def publish_rubric_version(self,rubric_id:str,version_id:str,user_id:str)->RubricVersionRecord|None:
        current=self._owned_rubric_version(rubric_id,version_id,user_id)
        if not current or current.status=="published":return current
        criteria=self.list_criteria(rubric_id,version_id,user_id);validate_rubric_for_publish(current.instructions,criteria);digest=rubric_content_hash(current.instructions,criteria)
        if self.find_rubric_version_by_hash(rubric_id,digest,user_id):raise DuplicateContentError("相同内容的量表版本已存在")
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE researchflow_rubric_versions SET status='published',content_hash=%s,published_at=NOW() WHERE rubric_version_id=%s AND rubric_id=%s AND status='draft'
                RETURNING rubric_version_id,rubric_id,version,status,schema_version,environment,instructions,content_hash,created_by,created_at,published_at""",(digest,version_id,rubric_id));return self._rubric_version(cur.fetchone())


class InMemoryEvaluationCatalogRepository:
    def __init__(self, workspaces: WorkspaceRepository) -> None:
        self._workspaces=workspaces;self._datasets={};self._dataset_versions={};self._cases={};self._rubrics={};self._rubric_versions={};self._criteria={};self._lock=RLock()
    def _read(self,wid,uid):return self._workspaces.get_workspace_for_user(wid,uid) is not None
    def _write(self,wid,uid):
        w=self._workspaces.get_workspace_for_user(wid,uid);return w is not None and w.role=="owner"
    def create_dataset(self,*,workspace_id,user_id,name,description):
        with self._lock:
            if not self._write(workspace_id,user_id):return None
            if any(x.workspace_id==workspace_id and x.name==name for x in self._datasets.values()):raise DuplicateCatalogError("Workspace中已存在同名评测集")
            x=DatasetRecord(uuid4().hex,workspace_id,name,description,user_id,datetime.now(timezone.utc));self._datasets[x.dataset_id]=x;return x
    def list_datasets(self,workspace_id,user_id):return sorted([x for x in self._datasets.values() if x.workspace_id==workspace_id],key=lambda x:x.created_at) if self._read(workspace_id,user_id) else []
    def get_dataset(self,dataset_id,user_id):
        x=self._datasets.get(dataset_id);return x if x and self._read(x.workspace_id,user_id) else None
    def create_dataset_version(self,*,dataset_id,user_id,version,schema_version,environment):
        d=self._datasets.get(dataset_id)
        if not d or not self._write(d.workspace_id,user_id):return None
        if any(x.dataset_id==dataset_id and x.version==version for x in self._dataset_versions.values()):raise DuplicateCatalogError("评测集中已存在相同版本号")
        x=DatasetVersionRecord(uuid4().hex,dataset_id,version,"draft",schema_version,environment,None,user_id,datetime.now(timezone.utc),None);self._dataset_versions[x.dataset_version_id]=x;return x
    def list_dataset_versions(self,dataset_id,user_id):return sorted([x for x in self._dataset_versions.values() if x.dataset_id==dataset_id],key=lambda x:x.created_at) if self.get_dataset(dataset_id,user_id) else []
    def get_dataset_version(self,dataset_id,version_id,user_id):return next((x for x in self.list_dataset_versions(dataset_id,user_id) if x.dataset_version_id==version_id),None)
    def find_dataset_version_by_hash(self,dataset_id,content_hash,user_id):return next((x for x in self.list_dataset_versions(dataset_id,user_id) if x.content_hash==content_hash),None)
    def _dataset_write(self,dataset_id,version_id,user_id):
        d=self._datasets.get(dataset_id);v=self._dataset_versions.get(version_id);return v if d and v and v.dataset_id==dataset_id and self._write(d.workspace_id,user_id) else None
    def add_case(self,*,dataset_id,version_id,user_id,external_id,input_json,expected_json,metadata_json):
        v=self._dataset_write(dataset_id,version_id,user_id)
        if v and v.status!="draft":raise ImmutableCatalogError("已发布评测集版本不可修改")
        if not v:return None
        if any(x.dataset_version_id==version_id and x.external_id==external_id for x in self._cases.values()):raise DuplicateCatalogError("版本中已存在相同external_id")
        x=EvaluationCaseRecord(uuid4().hex,version_id,external_id,deepcopy(input_json),deepcopy(expected_json),deepcopy(metadata_json),datetime.now(timezone.utc));self._cases[x.case_id]=x;return x
    def list_cases(self,dataset_id,version_id,user_id):return sorted([x for x in self._cases.values() if x.dataset_version_id==version_id],key=lambda x:x.external_id) if self.get_dataset_version(dataset_id,version_id,user_id) else []
    def update_case(self,*,dataset_id,version_id,case_id,user_id,external_id,input_json,expected_json,metadata_json):
        v=self._dataset_write(dataset_id,version_id,user_id)
        if v and v.status!="draft":raise ImmutableCatalogError("已发布评测集版本不可修改")
        old=self._cases.get(case_id)
        if not v or not old or old.dataset_version_id!=version_id:return None
        if any(x.case_id!=case_id and x.dataset_version_id==version_id and x.external_id==external_id for x in self._cases.values()):raise DuplicateCatalogError("版本中已存在相同external_id")
        x=replace(old,external_id=external_id,input_json=deepcopy(input_json),expected_json=deepcopy(expected_json),metadata_json=deepcopy(metadata_json));self._cases[case_id]=x;return x
    def delete_case(self,dataset_id,version_id,case_id,user_id):
        v=self._dataset_write(dataset_id,version_id,user_id)
        if v and v.status!="draft":raise ImmutableCatalogError("已发布评测集版本不可修改")
        x=self._cases.get(case_id)
        if not v or not x or x.dataset_version_id!=version_id:return False
        del self._cases[case_id];return True
    def publish_dataset_version(self,dataset_id,version_id,user_id):
        v=self._dataset_write(dataset_id,version_id,user_id)
        if not v or v.status=="published":return v
        cases=self.list_cases(dataset_id,version_id,user_id);validate_dataset_for_publish(cases);digest=dataset_content_hash(cases)
        if self.find_dataset_version_by_hash(dataset_id,digest,user_id):raise DuplicateContentError("相同内容的评测集版本已存在")
        v=replace(v,status="published",content_hash=digest,published_at=datetime.now(timezone.utc));self._dataset_versions[version_id]=v;return v
    def create_rubric(self,*,workspace_id,user_id,name,description):
        if not self._write(workspace_id,user_id):return None
        if any(x.workspace_id==workspace_id and x.name==name for x in self._rubrics.values()):raise DuplicateCatalogError("Workspace中已存在同名量表")
        x=RubricRecord(uuid4().hex,workspace_id,name,description,user_id,datetime.now(timezone.utc));self._rubrics[x.rubric_id]=x;return x
    def list_rubrics(self,workspace_id,user_id):return sorted([x for x in self._rubrics.values() if x.workspace_id==workspace_id],key=lambda x:x.created_at) if self._read(workspace_id,user_id) else []
    def get_rubric(self,rubric_id,user_id):
        x=self._rubrics.get(rubric_id);return x if x and self._read(x.workspace_id,user_id) else None
    def create_rubric_version(self,*,rubric_id,user_id,version,schema_version,environment,instructions):
        r=self._rubrics.get(rubric_id)
        if not r or not self._write(r.workspace_id,user_id):return None
        if any(x.rubric_id==rubric_id and x.version==version for x in self._rubric_versions.values()):raise DuplicateCatalogError("量表中已存在相同版本号")
        x=RubricVersionRecord(uuid4().hex,rubric_id,version,"draft",schema_version,environment,instructions,None,user_id,datetime.now(timezone.utc),None);self._rubric_versions[x.rubric_version_id]=x;return x
    def list_rubric_versions(self,rubric_id,user_id):return sorted([x for x in self._rubric_versions.values() if x.rubric_id==rubric_id],key=lambda x:x.created_at) if self.get_rubric(rubric_id,user_id) else []
    def get_rubric_version(self,rubric_id,version_id,user_id):return next((x for x in self.list_rubric_versions(rubric_id,user_id) if x.rubric_version_id==version_id),None)
    def find_rubric_version_by_hash(self,rubric_id,content_hash,user_id):return next((x for x in self.list_rubric_versions(rubric_id,user_id) if x.content_hash==content_hash),None)
    def _rubric_write(self,rubric_id,version_id,user_id):
        r=self._rubrics.get(rubric_id);v=self._rubric_versions.get(version_id);return v if r and v and v.rubric_id==rubric_id and self._write(r.workspace_id,user_id) else None
    def add_criterion(self,*,rubric_id,version_id,user_id,key,title,description,min_score,max_score,weight,required):
        v=self._rubric_write(rubric_id,version_id,user_id)
        if v and v.status!="draft":raise ImmutableCatalogError("已发布量表版本不可修改")
        if not v:return None
        if any(x.rubric_version_id==version_id and x.key==key for x in self._criteria.values()):raise DuplicateCatalogError("版本中已存在相同criterion key")
        x=CriterionRecord(uuid4().hex,version_id,key,title,description,min_score,max_score,weight,required,datetime.now(timezone.utc));self._criteria[x.criterion_id]=x;return x
    def list_criteria(self,rubric_id,version_id,user_id):return sorted([x for x in self._criteria.values() if x.rubric_version_id==version_id],key=lambda x:x.key) if self.get_rubric_version(rubric_id,version_id,user_id) else []
    def update_criterion(self,*,rubric_id,version_id,criterion_id,user_id,key,title,description,min_score,max_score,weight,required):
        v=self._rubric_write(rubric_id,version_id,user_id)
        if v and v.status!="draft":raise ImmutableCatalogError("已发布量表版本不可修改")
        old=self._criteria.get(criterion_id)
        if not v or not old or old.rubric_version_id!=version_id:return None
        if any(x.criterion_id!=criterion_id and x.rubric_version_id==version_id and x.key==key for x in self._criteria.values()):raise DuplicateCatalogError("版本中已存在相同criterion key")
        x=replace(old,key=key,title=title,description=description,min_score=min_score,max_score=max_score,weight=weight,required=required);self._criteria[criterion_id]=x;return x
    def delete_criterion(self,rubric_id,version_id,criterion_id,user_id):
        v=self._rubric_write(rubric_id,version_id,user_id)
        if v and v.status!="draft":raise ImmutableCatalogError("已发布量表版本不可修改")
        x=self._criteria.get(criterion_id)
        if not v or not x or x.rubric_version_id!=version_id:return False
        del self._criteria[criterion_id];return True
    def publish_rubric_version(self,rubric_id,version_id,user_id):
        v=self._rubric_write(rubric_id,version_id,user_id)
        if not v or v.status=="published":return v
        criteria=self.list_criteria(rubric_id,version_id,user_id);validate_rubric_for_publish(v.instructions,criteria);digest=rubric_content_hash(v.instructions,criteria)
        if self.find_rubric_version_by_hash(rubric_id,digest,user_id):raise DuplicateContentError("相同内容的量表版本已存在")
        v=replace(v,status="published",content_hash=digest,published_at=datetime.now(timezone.utc));self._rubric_versions[version_id]=v;return v


@lru_cache(maxsize=1)
def get_evaluation_catalog_repository() -> PostgresEvaluationCatalogRepository:
    return PostgresEvaluationCatalogRepository()
