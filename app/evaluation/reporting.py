from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape
from psycopg.types.json import Jsonb

from app.memory.checkpointer import get_postgres_pool


ReportStatus = Literal["generating", "completed", "failed"]
ReportFormat = Literal["json", "html"]


@dataclass(frozen=True)
class AggregateMetricRecord:
    aggregate_metric_id: str
    run_id: str
    source: Literal["program", "human"]
    namespace_key: str
    metric_key: str
    value: float | None
    sample_count: int
    missing_count: int
    pass_count: int | None
    pass_rate: float | None
    details: dict[str, Any]
    calculated_at: datetime


@dataclass(frozen=True)
class ReportRecord:
    report_id: str
    run_id: str
    format: ReportFormat
    status: ReportStatus
    storage_path: str | None
    content_hash: str | None
    generated_at: datetime | None
    error: str | None
    created_by: str
    created_at: datetime


class ReportingRepository(Protocol):
    def load_snapshot(self, run_id: str, user_id: str) -> dict[str, Any] | None: ...
    def replace_aggregates(self, run_id: str, user_id: str, metrics: list[AggregateMetricRecord]) -> bool: ...
    def create_report(self, run_id: str, user_id: str, format: ReportFormat) -> ReportRecord | None: ...
    def complete_report(self, report_id: str, storage_path: str, content_hash: str) -> ReportRecord: ...
    def fail_report(self, report_id: str, error: str) -> ReportRecord: ...
    def get_report(self, report_id: str, user_id: str) -> ReportRecord | None: ...
    def list_reports(self, run_id: str, user_id: str) -> list[ReportRecord]: ...
    def attach_gate(self, run_id: str, user_id: str, gate: dict[str, Any]) -> None: ...


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_summary(snapshot: dict[str, Any], *, calculated_at: datetime | None = None) -> dict[str, Any]:
    """Build a deterministic projection from immutable facts and effective submissions."""
    calculated_at = calculated_at or datetime.now(timezone.utc)
    cases = snapshot["cases"]
    total_cases = len(cases)
    program_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in snapshot["program_metrics"]:
        key = (item["evaluator_key"], item["evaluator_version"], item["metric_key"])
        program_groups.setdefault(key, []).append(item)

    program_metrics = []
    for (evaluator, version, metric_key), rows in sorted(program_groups.items()):
        values = [float(row["value"]) for row in rows]
        case_ids = {row["case_result_id"] for row in rows if row["case_result_id"]}
        if case_ids:
            sample_count = len(case_ids)
            denominator = total_cases
        else:
            sample_count = len(rows)
            denominator = len(rows)
        is_binary = bool(values) and all(value in {0.0, 1.0} for value in values)
        pass_count = sum(value == 1.0 for value in values) if is_binary else None
        program_metrics.append(
            {
                "source": "program",
                "namespace_key": f"{evaluator}@{version}",
                "evaluator_key": evaluator,
                "evaluator_version": version,
                "metric_key": metric_key,
                "value": _mean(values),
                "sample_count": sample_count,
                "missing_count": max(denominator - sample_count, 0),
                "pass_count": pass_count,
                "pass_rate": pass_count / len(values) if is_binary and values else None,
                "details": {"pass_rule": "value_equals_1" if is_binary else "not_configured"},
            }
        )

    expected_by_rubric: dict[str, int] = {}
    for review in snapshot["reviews"]:
        rubric_id = review["rubric_version_id"]
        expected_by_rubric[rubric_id] = expected_by_rubric.get(rubric_id, 0) + 1
    human_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {
        (
            item["rubric_version_id"], item["rubric_version"],
            item["criterion_key"], item["criterion_title"],
        ): []
        for item in snapshot.get("human_dimensions", [])
    }
    for item in snapshot["human_scores"]:
        key = (
            item["rubric_version_id"],
            item["rubric_version"],
            item["criterion_key"],
            item["criterion_title"],
        )
        human_groups.setdefault(key, []).append(item)

    human_metrics = []
    for (rubric_id, rubric_version, criterion_key, title), rows in sorted(human_groups.items()):
        values = [float(row["score"]) for row in rows]
        sample_count = len(rows)
        expected = expected_by_rubric.get(rubric_id, sample_count)
        dimension = next(
            item for item in snapshot.get("human_dimensions", snapshot["human_scores"])
            if item["rubric_version_id"] == rubric_id and item["criterion_key"] == criterion_key
        )
        human_metrics.append(
            {
                "source": "human",
                "namespace_key": f"{rubric_id}@{rubric_version}",
                "rubric_version_id": rubric_id,
                "rubric_version": rubric_version,
                "metric_key": criterion_key,
                "title": title,
                "value": _mean(values),
                "sample_count": sample_count,
                "missing_count": max(expected - sample_count, 0),
                "pass_count": None,
                "pass_rate": None,
                "reviewer_count": len({row["reviewer_id"] for row in rows}),
                "details": {
                    "pass_rule": "not_configured",
                    "min_score": float(dimension["min_score"]),
                    "max_score": float(dimension["max_score"]),
                    "weight": float(dimension["weight"]),
                },
            }
        )

    statuses = [item["status"] for item in snapshot["reviews"]]
    total_reviews = len(statuses)
    review_progress = {
        "total_count": total_reviews,
        "pending_count": statuses.count("pending"),
        "draft_count": statuses.count("draft"),
        "submitted_count": statuses.count("submitted"),
        "completion_rate": statuses.count("submitted") / total_reviews if total_reviews else 0.0,
    }
    human_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in snapshot["human_scores"]:
        human_by_case.setdefault(row["case_result_id"], []).append(
            {
                "source": "human",
                "reviewer_id": row["reviewer_id"],
                "rubric_version_id": row["rubric_version_id"],
                "rubric_version": row["rubric_version"],
                "revision": row["revision"],
                "criterion_key": row["criterion_key"],
                "score": row["score"],
                "comment": row["comment"],
            }
        )
    program_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in snapshot["program_metrics"]:
        if row["case_result_id"]:
            program_by_case.setdefault(row["case_result_id"], []).append(
                {
                    "source": "program",
                    "evaluator_key": row["evaluator_key"],
                    "evaluator_version": row["evaluator_version"],
                    "metric_key": row["metric_key"],
                    "value": row["value"],
                }
            )
    report_cases = []
    for case in cases:
        report_cases.append(
            {
                **case,
                "program_metrics": program_by_case.get(case["case_result_id"], []),
                "human_scores": human_by_case.get(case["case_result_id"], []),
            }
        )
    failed_cases = [
        {"case_result_id": c["case_result_id"], "external_id": c["external_id"], "error": c["error"]}
        for c in cases if c["status"] == "failed"
    ]
    return {
        "schema_version": "1.0",
        "calculated_at": calculated_at.isoformat(),
        "run": deepcopy(snapshot["run"]),
        "case_counts": {
            "total": total_cases,
            "succeeded": sum(c["status"] == "succeeded" for c in cases),
            "failed": sum(c["status"] == "failed" for c in cases),
            "skipped": sum(c["status"] == "skipped" for c in cases),
        },
        "review_progress": review_progress,
        "program_metrics": program_metrics,
        "human_metrics": human_metrics,
        "failed_cases": failed_cases,
        "cases": report_cases,
        "gate": deepcopy(snapshot.get("gate")),
    }


def aggregate_records(summary: dict[str, Any]) -> list[AggregateMetricRecord]:
    calculated_at = datetime.fromisoformat(summary["calculated_at"])
    run_id = summary["run"]["run_id"]
    records = []
    for source_key in ("program_metrics", "human_metrics"):
        for item in summary[source_key]:
            records.append(
                AggregateMetricRecord(
                    aggregate_metric_id=uuid4().hex,
                    run_id=run_id,
                    source=item["source"],
                    namespace_key=item["namespace_key"],
                    metric_key=item["metric_key"],
                    value=item["value"],
                    sample_count=item["sample_count"],
                    missing_count=item["missing_count"],
                    pass_count=item["pass_count"],
                    pass_rate=item["pass_rate"],
                    details=deepcopy(item["details"]),
                    calculated_at=calculated_at,
                )
            )
    return records


class PostgresReportingRepository:
    def __init__(self) -> None:
        self._pool = get_postgres_pool()

    @staticmethod
    def _report(row: dict[str, Any] | None) -> ReportRecord | None:
        return ReportRecord(**row) if row else None

    def load_snapshot(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT er.run_id,er.workspace_id,er.status,er.trigger_type,
                er.config_snapshot,er.git_commit,er.created_at,er.started_at,er.finished_at,
                av.agent_version_id,av.version AS agent_version,a.name AS application_name,
                dv.dataset_version_id,dv.version AS dataset_version,dv.environment,
                d.name AS dataset_name
                FROM researchflow_evaluation_runs er
                JOIN researchflow_workspace_members wm ON wm.workspace_id=er.workspace_id
                JOIN researchflow_agent_versions av ON av.agent_version_id=er.agent_version_id
                JOIN researchflow_applications a ON a.application_id=av.application_id
                JOIN researchflow_evaluation_dataset_versions dv ON dv.dataset_version_id=er.dataset_version_id
                JOIN researchflow_evaluation_datasets d ON d.dataset_id=dv.dataset_id
                WHERE er.run_id=%s AND wm.user_id=%s AND wm.role='owner'""",
                (run_id, user_id),
            )
            run = cur.fetchone()
            if not run:
                return None
            run = dict(run)
            run["config_snapshot"] = dict(run["config_snapshot"])
            for key, value in list(run.items()):
                if isinstance(value, datetime):
                    run[key] = value.isoformat()
            cur.execute(
                """SELECT cr.case_result_id,cr.case_id,c.external_id,c.input_json,c.expected_json,
                cr.status,cr.output_json,cr.evidence_json,cr.latency_ms,cr.token_usage_json,cr.error
                FROM researchflow_case_results cr
                JOIN researchflow_evaluation_cases c ON c.case_id=cr.case_id
                WHERE cr.run_id=%s ORDER BY c.external_id""",
                (run_id,),
            )
            cases = [dict(row) for row in cur.fetchall()]
            for row in cases:
                for key in ("input_json", "expected_json", "output_json", "token_usage_json"):
                    row[key] = dict(row[key])
                row["evidence_json"] = list(row["evidence_json"])
            cur.execute(
                """SELECT case_result_id,evaluator_key,evaluator_version,metric_key,value
                FROM researchflow_program_metrics WHERE run_id=%s
                ORDER BY evaluator_key,evaluator_version,metric_key,case_result_id""",
                (run_id,),
            )
            program = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """SELECT rv.review_id,rv.case_result_id,rv.status,t.rubric_version_id
                FROM researchflow_review_tasks t
                JOIN researchflow_review_assignments ra ON ra.task_id=t.task_id
                JOIN researchflow_reviews rv ON rv.assignment_id=ra.assignment_id
                WHERE t.run_id=%s ORDER BY rv.review_id""",
                (run_id,),
            )
            reviews = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """SELECT DISTINCT t.rubric_version_id,ruv.version AS rubric_version,
                rc.criterion_key,rc.title AS criterion_title,rc.min_score,rc.max_score,rc.weight
                FROM researchflow_review_tasks t
                JOIN researchflow_rubric_versions ruv ON ruv.rubric_version_id=t.rubric_version_id
                JOIN researchflow_rubric_criteria rc ON rc.rubric_version_id=t.rubric_version_id
                WHERE t.run_id=%s ORDER BY t.rubric_version_id,rc.criterion_key""",
                (run_id,),
            )
            dimensions = [dict(row) for row in cur.fetchall()]
            for row in dimensions:
                for key in ("min_score", "max_score", "weight"):
                    row[key] = float(row[key])
            cur.execute(
                """SELECT rv.case_result_id,ra.reviewer_id,t.rubric_version_id,
                ruv.version AS rubric_version,rr.revision,rc.criterion_key,
                rc.title AS criterion_title,rc.min_score,rc.max_score,rc.weight,
                hs.score,hs.comment
                FROM researchflow_review_tasks t
                JOIN researchflow_review_assignments ra ON ra.task_id=t.task_id
                JOIN researchflow_reviews rv ON rv.assignment_id=ra.assignment_id
                JOIN researchflow_review_revisions rr ON rr.review_id=rv.review_id
                    AND rr.status='submitted'
                JOIN researchflow_human_scores hs ON hs.revision_id=rr.revision_id
                JOIN researchflow_rubric_criteria rc ON rc.criterion_id=hs.criterion_id
                JOIN researchflow_rubric_versions ruv ON ruv.rubric_version_id=t.rubric_version_id
                WHERE t.run_id=%s
                ORDER BY rv.case_result_id,rc.criterion_key""",
                (run_id,),
            )
            human = [dict(row) for row in cur.fetchall()]
            for row in human:
                for key in ("min_score", "max_score", "weight", "score"):
                    row[key] = float(row[key])
            cur.execute(
                """SELECT ge.gate_evaluation_id,ge.baseline_run_id,ge.policy_id,
                ge.status,ge.results_json AS results,ge.evaluated_at
                FROM researchflow_gate_evaluations ge WHERE ge.run_id=%s
                ORDER BY ge.evaluated_at DESC,ge.gate_evaluation_id DESC LIMIT 1""",
                (run_id,),
            )
            gate = cur.fetchone()
            if gate:
                gate = {**gate, "results": dict(gate["results"]),
                        "evaluated_at": gate["evaluated_at"].isoformat()}
            return {"run": run, "cases": cases, "program_metrics": program,
                    "reviews": reviews, "human_dimensions": dimensions,
                    "human_scores": human, "gate": gate}

    def replace_aggregates(self, run_id: str, user_id: str, metrics: list[AggregateMetricRecord]) -> bool:
        with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM researchflow_evaluation_runs er
                JOIN researchflow_workspace_members wm ON wm.workspace_id=er.workspace_id
                WHERE er.run_id=%s AND wm.user_id=%s AND wm.role='owner'""",
                (run_id, user_id),
            )
            if not cur.fetchone():
                return False
            cur.execute("DELETE FROM researchflow_aggregate_metrics WHERE run_id=%s", (run_id,))
            for item in metrics:
                cur.execute(
                    """INSERT INTO researchflow_aggregate_metrics (
                    aggregate_metric_id,run_id,source,namespace_key,metric_key,value,
                    sample_count,missing_count,pass_count,pass_rate,details_json,calculated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (item.aggregate_metric_id,item.run_id,item.source,item.namespace_key,item.metric_key,
                     item.value,item.sample_count,item.missing_count,item.pass_count,item.pass_rate,
                     Jsonb(item.details),item.calculated_at),
                )
            return True

    def create_report(self, run_id: str, user_id: str, format: ReportFormat) -> ReportRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO researchflow_reports (report_id,run_id,format,created_by)
                SELECT %s,er.run_id,%s,%s FROM researchflow_evaluation_runs er
                JOIN researchflow_workspace_members wm ON wm.workspace_id=er.workspace_id
                WHERE er.run_id=%s AND wm.user_id=%s AND wm.role='owner'
                RETURNING report_id,run_id,format,status,storage_path,content_hash,
                generated_at,error,created_by,created_at""",
                (uuid4().hex, format, user_id, run_id, user_id),
            )
            return self._report(cur.fetchone())

    def complete_report(self, report_id: str, storage_path: str, content_hash: str) -> ReportRecord:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE researchflow_reports SET status='completed',storage_path=%s,
                content_hash=%s,generated_at=NOW(),error=NULL WHERE report_id=%s
                RETURNING report_id,run_id,format,status,storage_path,content_hash,
                generated_at,error,created_by,created_at""",
                (storage_path, content_hash, report_id),
            )
            return self._report(cur.fetchone())  # type: ignore[return-value]

    def fail_report(self, report_id: str, error: str) -> ReportRecord:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE researchflow_reports SET status='failed',error=%s WHERE report_id=%s
                RETURNING report_id,run_id,format,status,storage_path,content_hash,
                generated_at,error,created_by,created_at""",
                (error[:2000], report_id),
            )
            return self._report(cur.fetchone())  # type: ignore[return-value]

    def get_report(self, report_id: str, user_id: str) -> ReportRecord | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT rp.report_id,rp.run_id,rp.format,rp.status,rp.storage_path,
                rp.content_hash,rp.generated_at,rp.error,rp.created_by,rp.created_at
                FROM researchflow_reports rp
                JOIN researchflow_evaluation_runs er ON er.run_id=rp.run_id
                JOIN researchflow_workspace_members wm ON wm.workspace_id=er.workspace_id
                WHERE rp.report_id=%s AND wm.user_id=%s AND wm.role='owner'""",
                (report_id, user_id),
            )
            return self._report(cur.fetchone())

    def list_reports(self, run_id: str, user_id: str) -> list[ReportRecord]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT rp.report_id,rp.run_id,rp.format,rp.status,rp.storage_path,
                rp.content_hash,rp.generated_at,rp.error,rp.created_by,rp.created_at
                FROM researchflow_reports rp
                JOIN researchflow_evaluation_runs er ON er.run_id=rp.run_id
                JOIN researchflow_workspace_members wm ON wm.workspace_id=er.workspace_id
                WHERE rp.run_id=%s AND wm.user_id=%s AND wm.role='owner'
                ORDER BY rp.created_at,rp.report_id""",
                (run_id, user_id),
            )
            return [self._report(row) for row in cur.fetchall()]  # type: ignore[list-item]

    def attach_gate(self, run_id: str, user_id: str, gate: dict[str, Any]) -> None:
        """PostgreSQL报告快照会直接读取最新GateEvaluation，无需缓存写入。"""


class InMemoryReportingRepository:
    def __init__(self) -> None:
        self.snapshots: dict[str, tuple[str, dict[str, Any]]] = {}
        self.aggregates: dict[str, list[AggregateMetricRecord]] = {}
        self.reports: dict[str, ReportRecord] = {}

    def seed_snapshot(self, run_id: str, user_id: str, snapshot: dict[str, Any]) -> None:
        self.snapshots[run_id] = (user_id, deepcopy(snapshot))

    def load_snapshot(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        item = self.snapshots.get(run_id)
        return deepcopy(item[1]) if item and item[0] == user_id else None

    def replace_aggregates(self, run_id: str, user_id: str, metrics: list[AggregateMetricRecord]) -> bool:
        if self.load_snapshot(run_id, user_id) is None:
            return False
        self.aggregates[run_id] = deepcopy(metrics)
        return True

    def create_report(self, run_id: str, user_id: str, format: ReportFormat) -> ReportRecord | None:
        if self.load_snapshot(run_id, user_id) is None:
            return None
        now = datetime.now(timezone.utc)
        item = ReportRecord(uuid4().hex,run_id,format,"generating",None,None,None,None,user_id,now)
        self.reports[item.report_id] = item
        return item

    def complete_report(self, report_id: str, storage_path: str, content_hash: str) -> ReportRecord:
        old = self.reports[report_id]
        item = ReportRecord(old.report_id,old.run_id,old.format,"completed",storage_path,content_hash,
                            datetime.now(timezone.utc),None,old.created_by,old.created_at)
        self.reports[report_id] = item
        return item

    def fail_report(self, report_id: str, error: str) -> ReportRecord:
        old = self.reports[report_id]
        item = ReportRecord(old.report_id,old.run_id,old.format,"failed",None,None,None,error[:2000],old.created_by,old.created_at)
        self.reports[report_id] = item
        return item

    def get_report(self, report_id: str, user_id: str) -> ReportRecord | None:
        item = self.reports.get(report_id)
        return item if item and item.created_by == user_id else None

    def list_reports(self, run_id: str, user_id: str) -> list[ReportRecord]:
        return [x for x in self.reports.values() if x.run_id == run_id and x.created_by == user_id]

    def attach_gate(self, run_id: str, user_id: str, gate: dict[str, Any]) -> None:
        item = self.snapshots.get(run_id)
        if item and item[0] == user_id:
            item[1]["gate"] = deepcopy(gate)


class ReportService:
    def __init__(self, repository: ReportingRepository, output_dir: Path | None = None) -> None:
        self.repository = repository
        project_root = Path(__file__).resolve().parents[2]
        configured = Path(os.getenv("REPORT_OUTPUT_DIR", "reports/generated"))
        self.output_dir = (output_dir or (project_root / configured)).resolve()
        template_dir = Path(__file__).resolve().parents[1] / "api" / "templates"
        self.jinja = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(("html", "xml")),
        )

    def summary(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        snapshot = self.repository.load_snapshot(run_id, user_id)
        if snapshot is None:
            return None
        summary = build_summary(snapshot)
        self.repository.replace_aggregates(run_id, user_id, aggregate_records(summary))
        return summary

    def generate(self, run_id: str, user_id: str) -> list[ReportRecord] | None:
        summary = self.summary(run_id, user_id)
        if summary is None:
            return None
        records = []
        for format in ("json", "html"):
            record = self.repository.create_report(run_id, user_id, format)
            if record is None:
                return None
            try:
                content = self._render(format, summary)
                self.output_dir.mkdir(parents=True, exist_ok=True)
                target = (self.output_dir / f"{record.report_id}.{format}").resolve()
                if self.output_dir not in target.parents:
                    raise ValueError("报告路径越出允许目录")
                target.write_bytes(content)
                project_root = Path(__file__).resolve().parents[2]
                try:
                    stored_path = target.relative_to(project_root).as_posix()
                except ValueError:
                    stored_path = str(target)
                records.append(self.repository.complete_report(record.report_id, stored_path, hashlib.sha256(content).hexdigest()))
            except Exception as exc:
                records.append(self.repository.fail_report(record.report_id, f"{type(exc).__name__}: {exc}"))
        return records

    def _render(self, format: ReportFormat, summary: dict[str, Any]) -> bytes:
        if format == "json":
            return json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        template = self.jinja.get_template("evaluation_report.html")
        return template.render(report=summary).encode("utf-8")

    def resolve_content(self, report: ReportRecord) -> Path | None:
        if report.status != "completed" or not report.storage_path:
            return None
        project_root = Path(__file__).resolve().parents[2]
        path = (project_root / report.storage_path).resolve()
        return path if self.output_dir in path.parents and path.is_file() else None


@lru_cache(maxsize=1)
def get_reporting_repository() -> PostgresReportingRepository:
    return PostgresReportingRepository()
