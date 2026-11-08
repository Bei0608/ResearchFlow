from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from threading import RLock
from time import perf_counter
from statistics import mean
from typing import Any, Callable, Literal, Protocol
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.memory.checkpointer import get_postgres_pool


RunStatus = Literal["created", "running", "ready_for_review", "failed"]
CaseResultStatus = Literal["succeeded", "failed", "skipped"]


@dataclass(frozen=True)
class EvaluationRunRecord:
    run_id: str
    workspace_id: str
    agent_version_id: str
    dataset_version_id: str
    status: RunStatus
    trigger_type: str
    config_snapshot: dict[str, Any]
    git_commit: str | None
    created_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class CaseResultRecord:
    case_result_id: str
    run_id: str
    case_id: str
    status: CaseResultStatus
    output_json: dict[str, Any]
    evidence_json: list[dict[str, Any]]
    trace_json: dict[str, Any]
    latency_ms: int | None
    token_usage_json: dict[str, Any]
    error: str | None
    created_at: datetime


@dataclass(frozen=True)
class ProgramMetricRecord:
    program_metric_id: str
    run_id: str
    case_result_id: str | None
    source: Literal["program"]
    evaluator_key: str
    evaluator_version: str
    metric_key: str
    value: float
    details_json: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class RunCase:
    case_id: str
    external_id: str
    input: dict[str, Any]
    expected: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CaseExecution:
    output: dict[str, Any]
    evidence: list[dict[str, Any]]
    trace: dict[str, Any]
    latency_ms: int | None = None
    token_usage: dict[str, Any] | None = None


@dataclass(frozen=True)
class MetricValue:
    evaluator_key: str
    evaluator_version: str
    metric_key: str
    value: float
    details: dict[str, Any] | None = None


class ProgramEvaluator(Protocol):
    key: str
    version: str

    def evaluate(
        self,
        case: RunCase,
        execution: CaseExecution,
    ) -> list[MetricValue]: ...


class EvaluationRunRepository(Protocol):
    def create_run(self, **kwargs: Any) -> EvaluationRunRecord | None: ...
    def get_run(self, run_id: str, user_id: str) -> EvaluationRunRecord | None: ...
    def list_runs(self, workspace_id: str, user_id: str) -> list[EvaluationRunRecord]: ...
    def transition_run(self, run_id: str, user_id: str, status: RunStatus, *, error: str | None = None) -> EvaluationRunRecord | None: ...
    def save_case_result(self, **kwargs: Any) -> CaseResultRecord | None: ...
    def save_metric(self, **kwargs: Any) -> ProgramMetricRecord | None: ...
    def list_case_results(self, run_id: str, user_id: str) -> list[CaseResultRecord]: ...
    def list_metrics(self, run_id: str, user_id: str) -> list[ProgramMetricRecord]: ...


class PostgresEvaluationRunRepository:
    def __init__(self) -> None:
        self._pool = get_postgres_pool()

    @staticmethod
    def _run(row: dict | None) -> EvaluationRunRecord | None:
        if not row:
            return None
        return EvaluationRunRecord(**{**row, "config_snapshot": dict(row["config_snapshot"])})

    @staticmethod
    def _result(row: dict | None) -> CaseResultRecord | None:
        if not row:
            return None
        return CaseResultRecord(
            **{
                **row,
                "output_json": dict(row["output_json"]),
                "evidence_json": list(row["evidence_json"]),
                "trace_json": dict(row["trace_json"]),
                "token_usage_json": dict(row["token_usage_json"]),
            }
        )

    @staticmethod
    def _metric(row: dict | None) -> ProgramMetricRecord | None:
        if not row:
            return None
        return ProgramMetricRecord(**{**row, "details_json": dict(row["details_json"])})

    def create_run(
        self,
        *,
        workspace_id: str,
        agent_version_id: str,
        dataset_version_id: str,
        trigger_type: str,
        config_snapshot: dict[str, Any],
        git_commit: str | None,
        user_id: str,
    ) -> EvaluationRunRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO researchflow_evaluation_runs (
                    run_id, workspace_id, agent_version_id,
                    dataset_version_id, trigger_type, config_snapshot,
                    git_commit, created_by
                )
                SELECT %s, %s, av.agent_version_id,
                       dv.dataset_version_id, %s, %s, %s, %s
                FROM researchflow_agent_versions av
                JOIN researchflow_applications a
                  ON a.application_id = av.application_id
                JOIN researchflow_evaluation_dataset_versions dv
                  ON dv.dataset_version_id = %s
                JOIN researchflow_evaluation_datasets d
                  ON d.dataset_id = dv.dataset_id
                JOIN researchflow_workspace_members m
                  ON m.workspace_id = %s
                WHERE av.agent_version_id = %s
                  AND av.status = 'published'
                  AND dv.status = 'published'
                  AND a.workspace_id = %s
                  AND d.workspace_id = %s
                  AND m.user_id = %s
                  AND m.role = 'owner'
                RETURNING run_id, workspace_id, agent_version_id,
                          dataset_version_id, status, trigger_type,
                          config_snapshot, git_commit, created_by,
                          created_at, started_at, finished_at, error
                """,
                (
                    uuid4().hex,
                    workspace_id,
                    trigger_type,
                    Jsonb(config_snapshot),
                    git_commit,
                    user_id,
                    dataset_version_id,
                    workspace_id,
                    agent_version_id,
                    workspace_id,
                    workspace_id,
                    user_id,
                ),
            )
            return self._run(cur.fetchone())

    def get_run(self, run_id: str, user_id: str) -> EvaluationRunRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.run_id,r.workspace_id,r.agent_version_id,
                       r.dataset_version_id,r.status,r.trigger_type,
                       r.config_snapshot,r.git_commit,r.created_by,
                       r.created_at,r.started_at,r.finished_at,r.error
                FROM researchflow_evaluation_runs r
                JOIN researchflow_workspace_members m
                  ON m.workspace_id=r.workspace_id
                WHERE r.run_id=%s AND m.user_id=%s
                """,
                (run_id, user_id),
            )
            return self._run(cur.fetchone())

    def list_runs(self, workspace_id: str, user_id: str) -> list[EvaluationRunRecord]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.run_id,r.workspace_id,r.agent_version_id,
                       r.dataset_version_id,r.status,r.trigger_type,
                       r.config_snapshot,r.git_commit,r.created_by,
                       r.created_at,r.started_at,r.finished_at,r.error
                FROM researchflow_evaluation_runs r
                JOIN researchflow_workspace_members m
                  ON m.workspace_id=r.workspace_id
                WHERE r.workspace_id=%s AND m.user_id=%s
                ORDER BY r.created_at,r.run_id
                """,
                (workspace_id, user_id),
            )
            return [self._run(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def transition_run(self, run_id: str, user_id: str, status: RunStatus, *, error: str | None = None) -> EvaluationRunRecord | None:
        if status not in {"running", "ready_for_review", "failed"}:
            raise ValueError("不支持的运行状态转换")
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE researchflow_evaluation_runs r
                SET status=%s,
                    started_at=CASE WHEN %s='running' THEN COALESCE(started_at,NOW()) ELSE started_at END,
                    finished_at=CASE WHEN %s IN ('ready_for_review','failed') THEN NOW() ELSE finished_at END,
                    error=%s
                FROM researchflow_workspace_members m
                WHERE r.run_id=%s AND m.workspace_id=r.workspace_id
                  AND m.user_id=%s AND m.role='owner'
                  AND ((%s='running' AND r.status='created')
                    OR (%s IN ('ready_for_review','failed')
                        AND r.status='running'))
                RETURNING r.run_id,r.workspace_id,r.agent_version_id,
                          r.dataset_version_id,r.status,r.trigger_type,
                          r.config_snapshot,r.git_commit,r.created_by,
                          r.created_at,r.started_at,r.finished_at,r.error
                """,
                (
                    status,
                    status,
                    status,
                    error,
                    run_id,
                    user_id,
                    status,
                    status,
                ),
            )
            return self._run(cur.fetchone())

    def save_case_result(
        self,
        *,
        run_id: str,
        case_id: str,
        user_id: str,
        status: CaseResultStatus,
        output_json: dict[str, Any],
        evidence_json: list[dict[str, Any]],
        trace_json: dict[str, Any],
        latency_ms: int | None,
        token_usage_json: dict[str, Any],
        error: str | None,
    ) -> CaseResultRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO researchflow_case_results (
                    case_result_id,run_id,case_id,status,output_json,
                    evidence_json,trace_json,latency_ms,
                    token_usage_json,error
                )
                SELECT %s,r.run_id,c.case_id,%s,%s,%s,%s,%s,%s,%s
                FROM researchflow_evaluation_runs r
                JOIN researchflow_evaluation_cases c
                  ON c.dataset_version_id=r.dataset_version_id
                JOIN researchflow_workspace_members m
                  ON m.workspace_id=r.workspace_id
                WHERE r.run_id=%s AND c.case_id=%s
                  AND m.user_id=%s AND m.role='owner'
                RETURNING case_result_id,run_id,case_id,status,
                          output_json,evidence_json,trace_json,latency_ms,
                          token_usage_json,error,created_at
                """,
                (
                    uuid4().hex,
                    status,
                    Jsonb(output_json),
                    Jsonb(evidence_json),
                    Jsonb(trace_json),
                    latency_ms,
                    Jsonb(token_usage_json),
                    error,
                    run_id,
                    case_id,
                    user_id,
                ),
            )
            return self._result(cur.fetchone())

    def save_metric(self, *, run_id: str, case_result_id: str, user_id: str, metric: MetricValue) -> ProgramMetricRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO researchflow_program_metrics (
                    program_metric_id,run_id,case_result_id,
                    evaluator_key,evaluator_version,metric_key,value,
                    details_json
                )
                SELECT %s,r.run_id,cr.case_result_id,%s,%s,%s,%s,%s
                FROM researchflow_evaluation_runs r
                JOIN researchflow_case_results cr ON cr.run_id=r.run_id
                JOIN researchflow_workspace_members m
                  ON m.workspace_id=r.workspace_id
                WHERE r.run_id=%s AND cr.case_result_id=%s
                  AND m.user_id=%s AND m.role='owner'
                RETURNING program_metric_id,run_id,case_result_id,
                          source,evaluator_key,evaluator_version,
                          metric_key,value,details_json,created_at
                """,
                (
                    uuid4().hex,
                    metric.evaluator_key,
                    metric.evaluator_version,
                    metric.metric_key,
                    metric.value,
                    Jsonb(metric.details or {}),
                    run_id,
                    case_result_id,
                    user_id,
                ),
            )
            return self._metric(cur.fetchone())

    def list_case_results(self, run_id: str, user_id: str) -> list[CaseResultRecord]:
        if self.get_run(run_id, user_id) is None:
            return []
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT case_result_id,run_id,case_id,status,
                output_json,evidence_json,trace_json,latency_ms,
                token_usage_json,error,created_at
                FROM researchflow_case_results WHERE run_id=%s
                ORDER BY created_at,case_result_id""",
                (run_id,),
            )
            return [self._result(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def list_metrics(self, run_id: str, user_id: str) -> list[ProgramMetricRecord]:
        if self.get_run(run_id, user_id) is None:
            return []
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT program_metric_id,run_id,case_result_id,
                source,evaluator_key,evaluator_version,metric_key,value,
                details_json,created_at FROM researchflow_program_metrics
                WHERE run_id=%s ORDER BY created_at,program_metric_id""",
                (run_id,),
            )
            return [self._metric(row) for row in cur.fetchall()]  # type: ignore[list-item]


class InMemoryEvaluationRunRepository:
    def __init__(self) -> None:
        self.runs: dict[str, EvaluationRunRecord] = {}
        self.results: dict[str, CaseResultRecord] = {}
        self.metrics: dict[str, ProgramMetricRecord] = {}
        self._lock = RLock()

    def create_run(self, *, workspace_id: str, agent_version_id: str, dataset_version_id: str, trigger_type: str, config_snapshot: dict[str, Any], git_commit: str | None, user_id: str) -> EvaluationRunRecord:
        item=EvaluationRunRecord(uuid4().hex,workspace_id,agent_version_id,dataset_version_id,"created",trigger_type,deepcopy(config_snapshot),git_commit,user_id,datetime.now(timezone.utc),None,None,None)
        self.runs[item.run_id]=item;return item
    def get_run(self,run_id,user_id):
        item=self.runs.get(run_id);return item if item and item.created_by==user_id else None
    def list_runs(self,workspace_id,user_id):return [x for x in self.runs.values() if x.workspace_id==workspace_id and x.created_by==user_id]
    def transition_run(self,run_id,user_id,status,*,error=None):
        item=self.get_run(run_id,user_id)
        if not item:return None
        if (status=="running" and item.status!="created") or (status in {"ready_for_review","failed"} and item.status!="running"):return None
        now=datetime.now(timezone.utc);item=replace(item,status=status,started_at=now if status=="running" and item.started_at is None else item.started_at,finished_at=now if status in {"ready_for_review","failed"} else item.finished_at,error=error);self.runs[run_id]=item;return item
    def save_case_result(self,*,run_id,case_id,user_id,status,output_json,evidence_json,trace_json,latency_ms,token_usage_json,error):
        if not self.get_run(run_id,user_id):return None
        item=CaseResultRecord(uuid4().hex,run_id,case_id,status,deepcopy(output_json),deepcopy(evidence_json),deepcopy(trace_json),latency_ms,deepcopy(token_usage_json),error,datetime.now(timezone.utc));self.results[item.case_result_id]=item;return item
    def save_metric(self,*,run_id,case_result_id,user_id,metric):
        if not self.get_run(run_id,user_id) or case_result_id not in self.results:return None
        item=ProgramMetricRecord(uuid4().hex,run_id,case_result_id,"program",metric.evaluator_key,metric.evaluator_version,metric.metric_key,float(metric.value),deepcopy(metric.details or {}),datetime.now(timezone.utc));self.metrics[item.program_metric_id]=item;return item
    def list_case_results(self,run_id,user_id):return [x for x in self.results.values() if x.run_id==run_id] if self.get_run(run_id,user_id) else []
    def list_metrics(self,run_id,user_id):return [x for x in self.metrics.values() if x.run_id==run_id] if self.get_run(run_id,user_id) else []


class EvaluationRunner:
    def __init__(self, repository: EvaluationRunRepository) -> None:
        self.repository = repository

    def run(
        self,
        *,
        run_id: str,
        user_id: str,
        cases: list[RunCase],
        execute_case: Callable[[RunCase], CaseExecution],
        evaluators: list[ProgramEvaluator],
    ) -> EvaluationRunRecord:
        current = self.repository.transition_run(run_id,user_id,"running")
        if current is None:
            raise ValueError("评测运行不存在或无写权限")
        errors: list[str] = []
        for case in cases:
            started=perf_counter()
            try:
                execution=execute_case(case)
                latency=execution.latency_ms
                if latency is None:latency=round((perf_counter()-started)*1000)
                metric_values=[]
                for evaluator in evaluators:metric_values.extend(evaluator.evaluate(case,execution))
            except Exception as exc:  # one bad case must not erase completed facts
                message=f"{case.external_id}: {type(exc).__name__}: {exc}"[:2000]
                errors.append(message)
                self.repository.save_case_result(run_id=run_id,case_id=case.case_id,user_id=user_id,status="failed",output_json={},evidence_json=[],trace_json={},latency_ms=round((perf_counter()-started)*1000),token_usage_json={},error=message)
                continue
            result=self.repository.save_case_result(run_id=run_id,case_id=case.case_id,user_id=user_id,status="succeeded",output_json=execution.output,evidence_json=execution.evidence,trace_json=execution.trace,latency_ms=latency,token_usage_json=execution.token_usage or {},error=None)
            if result is None:
                errors.append(f"{case.external_id}: 无法保存案例结果")
                continue
            for metric in metric_values:
                saved=self.repository.save_metric(run_id=run_id,case_result_id=result.case_result_id,user_id=user_id,metric=metric)
                if saved is None:
                    errors.append(
                        f"{case.external_id}: 无法保存程序指标 {metric.metric_key}"
                    )
                    break
        final_status: RunStatus = "failed" if errors else "ready_for_review"
        final=self.repository.transition_run(run_id,user_id,final_status,error="\n".join(errors) or None)
        if final is None:raise ValueError("无法完成评测运行")
        return final


def summarize_program_metrics(metrics: list[ProgramMetricRecord]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for metric in metrics:
        grouped.setdefault(metric.metric_key, []).append(metric.value)
    return {
        f"mean_{key}": mean(values)
        for key, values in sorted(grouped.items())
    }


@lru_cache(maxsize=1)
def get_evaluation_run_repository() -> PostgresEvaluationRunRepository:
    return PostgresEvaluationRunRepository()
