from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal, Protocol
from uuid import uuid4

from psycopg.types.json import Jsonb
from psycopg.errors import UniqueViolation

from app.evaluation.reporting import ReportService, ReportingRepository
from app.memory.checkpointer import get_postgres_pool


GateStatus = Literal["passed", "failed", "incomplete"]


class GateValidationError(ValueError):
    pass


@dataclass(frozen=True)
class BaselineRecord:
    baseline_id: str
    application_id: str
    run_id: str
    active: bool
    activated_by: str
    activated_at: datetime
    deactivated_at: datetime | None


@dataclass(frozen=True)
class GatePolicyRecord:
    policy_id: str
    workspace_id: str
    name: str
    version: str
    status: Literal["draft", "published"]
    rules: list[dict[str, Any]]
    created_by: str
    created_at: datetime
    published_at: datetime | None


@dataclass(frozen=True)
class GateEvaluationRecord:
    gate_evaluation_id: str
    run_id: str
    baseline_run_id: str | None
    policy_id: str
    status: GateStatus
    results: dict[str, Any]
    evaluated_by: str
    evaluated_at: datetime


class GateRepository(Protocol):
    def set_baseline(self, application_id: str, run_id: str, user_id: str) -> BaselineRecord | None: ...
    def get_active_baseline(self, application_id: str, user_id: str) -> BaselineRecord | None: ...
    def create_policy(self, workspace_id: str, name: str, version: str, rules: list[dict[str, Any]], user_id: str) -> GatePolicyRecord | None: ...
    def publish_policy(self, policy_id: str, user_id: str) -> GatePolicyRecord | None: ...
    def get_policy(self, policy_id: str, user_id: str) -> GatePolicyRecord | None: ...
    def list_policies(self, workspace_id: str, user_id: str) -> list[GatePolicyRecord]: ...
    def evaluation_context(self, run_id: str, policy_id: str, user_id: str) -> dict[str, Any] | None: ...
    def save_evaluation(self, run_id: str, baseline_run_id: str | None, policy_id: str, status: GateStatus, results: dict[str, Any], user_id: str) -> GateEvaluationRecord: ...
    def list_evaluations(self, run_id: str, user_id: str) -> list[GateEvaluationRecord]: ...


def validate_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rules:
        raise GateValidationError("Gate Policy至少需要一条规则")
    normalized = []
    seen = set()
    for raw in rules:
        rule = deepcopy(raw)
        required = {"rule_id", "source", "namespace_key", "metric_key", "kind"}
        if not required.issubset(rule):
            raise GateValidationError("Gate规则缺少必要字段")
        if rule["rule_id"] in seen:
            raise GateValidationError("Gate规则ID不能重复")
        seen.add(rule["rule_id"])
        if rule["source"] not in {"program", "human"}:
            raise GateValidationError("Gate规则source必须为program或human")
        if rule["kind"] == "absolute_min":
            if "min_value" not in rule:
                raise GateValidationError("absolute_min规则缺少min_value")
            rule["min_value"] = float(rule["min_value"])
        elif rule["kind"] == "max_regression":
            if "max_drop" not in rule or float(rule["max_drop"]) < 0:
                raise GateValidationError("max_regression规则需要非负max_drop")
            rule["max_drop"] = float(rule["max_drop"])
        else:
            raise GateValidationError("不支持的Gate规则类型")
        normalized.append(rule)
    return normalized


def _metric(summary: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    key = "program_metrics" if rule["source"] == "program" else "human_metrics"
    return next(
        (item for item in summary[key]
         if item["namespace_key"] == rule["namespace_key"]
         and item["metric_key"] == rule["metric_key"]),
        None,
    )


def evaluate_rules(
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None,
    rules: list[dict[str, Any]],
) -> tuple[GateStatus, dict[str, Any]]:
    checked = validate_rules(rules)
    outcomes = []
    for rule in checked:
        candidate_metric = _metric(candidate, rule)
        baseline_metric = _metric(baseline, rule) if baseline else None
        outcome = {
            "rule_id": rule["rule_id"], "source": rule["source"],
            "namespace_key": rule["namespace_key"], "metric_key": rule["metric_key"],
            "kind": rule["kind"], "candidate_value": None, "baseline_value": None,
            "status": "incomplete", "reason": "",
        }
        if baseline is None:
            outcome["reason"] = "应用尚未设置活动Baseline"
        elif candidate_metric is None:
            outcome["reason"] = "候选运行缺少指标"
        elif candidate_metric["sample_count"] == 0 or candidate_metric["missing_count"] > 0:
            outcome["candidate_value"] = candidate_metric["value"]
            outcome["reason"] = "候选指标样本不完整"
        elif rule["source"] == "human" and candidate["review_progress"]["completion_rate"] < 1:
            outcome["candidate_value"] = candidate_metric["value"]
            outcome["reason"] = "候选运行人工评审尚未完成"
        elif rule["kind"] == "max_regression" and baseline_metric is None:
            outcome["candidate_value"] = candidate_metric["value"]
            outcome["reason"] = "Baseline缺少对比指标"
        elif rule["kind"] == "max_regression" and (
            baseline_metric["sample_count"] == 0 or baseline_metric["missing_count"] > 0
        ):
            outcome["candidate_value"] = candidate_metric["value"]
            outcome["baseline_value"] = baseline_metric["value"]
            outcome["reason"] = "Baseline指标样本不完整"
        else:
            candidate_value = float(candidate_metric["value"])
            outcome["candidate_value"] = candidate_value
            if rule["kind"] == "absolute_min":
                limit = float(rule["min_value"])
                outcome["limit"] = limit
                passed = candidate_value >= limit
                outcome["reason"] = (
                    f"{candidate_value:.6g} >= {limit:.6g}"
                    if passed else f"{candidate_value:.6g} < {limit:.6g}"
                )
            else:
                baseline_value = float(baseline_metric["value"])
                limit = baseline_value - float(rule["max_drop"])
                outcome["baseline_value"] = baseline_value
                outcome["limit"] = limit
                passed = candidate_value >= limit
                outcome["reason"] = (
                    f"{candidate_value:.6g} >= baseline {baseline_value:.6g} - {rule['max_drop']:.6g}"
                    if passed else f"{candidate_value:.6g} < baseline {baseline_value:.6g} - {rule['max_drop']:.6g}"
                )
            outcome["status"] = "passed" if passed else "failed"
        outcomes.append(outcome)
    statuses = {item["status"] for item in outcomes}
    status: GateStatus = "failed" if "failed" in statuses else "incomplete" if "incomplete" in statuses else "passed"
    return status, {
        "status": status,
        "candidate_run_id": candidate["run"]["run_id"],
        "baseline_run_id": baseline["run"]["run_id"] if baseline else None,
        "rules": outcomes,
        "summary": {
            "passed": sum(x["status"] == "passed" for x in outcomes),
            "failed": sum(x["status"] == "failed" for x in outcomes),
            "incomplete": sum(x["status"] == "incomplete" for x in outcomes),
        },
    }


class PostgresGateRepository:
    def __init__(self) -> None:
        self._pool = get_postgres_pool()

    @staticmethod
    def _baseline(row):
        return BaselineRecord(**row) if row else None

    @staticmethod
    def _policy(row):
        if not row:
            return None
        return GatePolicyRecord(**{**row, "rules": list(row["rules"])})

    @staticmethod
    def _evaluation(row):
        if not row:
            return None
        return GateEvaluationRecord(**{**row, "results": dict(row["results"])})

    def set_baseline(self, application_id, run_id, user_id):
        with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM researchflow_applications a
                JOIN researchflow_workspace_members wm ON wm.workspace_id=a.workspace_id
                JOIN researchflow_agent_versions av ON av.application_id=a.application_id
                JOIN researchflow_evaluation_runs er ON er.agent_version_id=av.agent_version_id
                WHERE a.application_id=%s AND er.run_id=%s AND er.status='ready_for_review'
                AND wm.user_id=%s AND wm.role='owner'""", (application_id,run_id,user_id))
            if not cur.fetchone(): return None
            cur.execute("UPDATE researchflow_baselines SET active=FALSE,deactivated_at=NOW() WHERE application_id=%s AND active",(application_id,))
            cur.execute(
                """INSERT INTO researchflow_baselines (baseline_id,application_id,run_id,activated_by)
                VALUES (%s,%s,%s,%s) ON CONFLICT (application_id,run_id) DO UPDATE
                SET active=TRUE,activated_by=EXCLUDED.activated_by,activated_at=NOW(),deactivated_at=NULL
                RETURNING baseline_id,application_id,run_id,active,activated_by,activated_at,deactivated_at""",
                (uuid4().hex,application_id,run_id,user_id))
            return self._baseline(cur.fetchone())

    def get_active_baseline(self, application_id, user_id):
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT b.baseline_id,b.application_id,b.run_id,b.active,b.activated_by,b.activated_at,b.deactivated_at
                FROM researchflow_baselines b JOIN researchflow_applications a ON a.application_id=b.application_id
                JOIN researchflow_workspace_members wm ON wm.workspace_id=a.workspace_id
                WHERE b.application_id=%s AND b.active AND wm.user_id=%s AND wm.role='owner'""",(application_id,user_id))
            return self._baseline(cur.fetchone())

    def create_policy(self, workspace_id, name, version, rules, user_id):
        rules=validate_rules(rules)
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO researchflow_gate_policies (policy_id,workspace_id,name,version,rules_json,created_by)
                    SELECT %s,%s,%s,%s,%s,%s FROM researchflow_workspace_members wm
                    WHERE wm.workspace_id=%s AND wm.user_id=%s AND wm.role='owner'
                    RETURNING policy_id,workspace_id,name,version,status,rules_json AS rules,
                    created_by,created_at,published_at""",
                    (uuid4().hex,workspace_id,name,version,Jsonb(rules),user_id,workspace_id,user_id))
                return self._policy(cur.fetchone())
        except UniqueViolation:
            raise GateValidationError("Gate Policy名称和版本已存在") from None

    def publish_policy(self, policy_id, user_id):
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE researchflow_gate_policies p SET status='published',published_at=NOW()
                FROM researchflow_workspace_members wm WHERE p.policy_id=%s
                AND wm.workspace_id=p.workspace_id AND wm.user_id=%s AND wm.role='owner' AND p.status='draft'
                RETURNING p.policy_id,p.workspace_id,p.name,p.version,p.status,p.rules_json AS rules,
                p.created_by,p.created_at,p.published_at""",(policy_id,user_id))
            return self._policy(cur.fetchone())

    def get_policy(self, policy_id, user_id):
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT p.policy_id,p.workspace_id,p.name,p.version,p.status,p.rules_json AS rules,
                p.created_by,p.created_at,p.published_at FROM researchflow_gate_policies p
                JOIN researchflow_workspace_members wm ON wm.workspace_id=p.workspace_id
                WHERE p.policy_id=%s AND wm.user_id=%s""",(policy_id,user_id))
            return self._policy(cur.fetchone())

    def list_policies(self, workspace_id, user_id):
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT p.policy_id,p.workspace_id,p.name,p.version,p.status,p.rules_json AS rules,
                p.created_by,p.created_at,p.published_at FROM researchflow_gate_policies p
                JOIN researchflow_workspace_members wm ON wm.workspace_id=p.workspace_id
                WHERE p.workspace_id=%s AND wm.user_id=%s ORDER BY p.created_at,p.policy_id""",(workspace_id,user_id))
            return [self._policy(x) for x in cur.fetchall()]

    def evaluation_context(self, run_id, policy_id, user_id):
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT er.run_id,a.application_id,p.policy_id,p.rules_json AS rules,b.run_id AS baseline_run_id
                FROM researchflow_evaluation_runs er
                JOIN researchflow_agent_versions av ON av.agent_version_id=er.agent_version_id
                JOIN researchflow_applications a ON a.application_id=av.application_id
                JOIN researchflow_workspace_members wm ON wm.workspace_id=er.workspace_id
                JOIN researchflow_gate_policies p ON p.workspace_id=er.workspace_id AND p.policy_id=%s
                LEFT JOIN researchflow_baselines b ON b.application_id=a.application_id AND b.active
                WHERE er.run_id=%s AND er.status IN ('ready_for_review','failed')
                AND p.status='published' AND wm.user_id=%s AND wm.role='owner'""",(policy_id,run_id,user_id))
            row=cur.fetchone()
            return {**row,"rules":list(row["rules"])} if row else None

    def save_evaluation(self, run_id, baseline_run_id, policy_id, status, results, user_id):
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO researchflow_gate_evaluations
                (gate_evaluation_id,run_id,baseline_run_id,policy_id,status,results_json,evaluated_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING gate_evaluation_id,run_id,baseline_run_id,policy_id,status,
                results_json AS results,evaluated_by,evaluated_at""",
                (uuid4().hex,run_id,baseline_run_id,policy_id,status,Jsonb(results),user_id))
            return self._evaluation(cur.fetchone())

    def list_evaluations(self, run_id, user_id):
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT ge.gate_evaluation_id,ge.run_id,ge.baseline_run_id,ge.policy_id,
                ge.status,ge.results_json AS results,ge.evaluated_by,ge.evaluated_at
                FROM researchflow_gate_evaluations ge JOIN researchflow_evaluation_runs er ON er.run_id=ge.run_id
                JOIN researchflow_workspace_members wm ON wm.workspace_id=er.workspace_id
                WHERE ge.run_id=%s AND wm.user_id=%s AND wm.role='owner'
                ORDER BY ge.evaluated_at,ge.gate_evaluation_id""",(run_id,user_id))
            return [self._evaluation(x) for x in cur.fetchall()]


class InMemoryGateRepository:
    def __init__(self) -> None:
        self.run_contexts={};self.baselines={};self.policies={};self.evaluations=[]
    def seed_run(self,run_id,application_id,workspace_id,user_id,status="ready_for_review"):
        self.run_contexts[run_id]={"application_id":application_id,"workspace_id":workspace_id,"user_id":user_id,"status":status}
    def set_baseline(self,application_id,run_id,user_id):
        ctx=self.run_contexts.get(run_id)
        if not ctx or ctx["application_id"]!=application_id or ctx["user_id"]!=user_id or ctx["status"]!="ready_for_review":return None
        for key,value in list(self.baselines.items()):
            if value.application_id==application_id and value.active:self.baselines[key]=replace(value,active=False,deactivated_at=datetime.now(timezone.utc))
        now=datetime.now(timezone.utc);item=BaselineRecord(uuid4().hex,application_id,run_id,True,user_id,now,None);self.baselines[item.baseline_id]=item;return item
    def get_active_baseline(self,application_id,user_id):
        return next((x for x in self.baselines.values() if x.application_id==application_id and x.active and x.activated_by==user_id),None)
    def create_policy(self,workspace_id,name,version,rules,user_id):
        if not any(x["workspace_id"]==workspace_id and x["user_id"]==user_id for x in self.run_contexts.values()):return None
        if any(x.workspace_id==workspace_id and x.name==name and x.version==version for x in self.policies.values()):raise GateValidationError("Gate Policy版本已存在")
        item=GatePolicyRecord(uuid4().hex,workspace_id,name,version,"draft",validate_rules(rules),user_id,datetime.now(timezone.utc),None);self.policies[item.policy_id]=item;return item
    def publish_policy(self,policy_id,user_id):
        item=self.policies.get(policy_id)
        if not item or item.created_by!=user_id or item.status!="draft":return None
        item=replace(item,status="published",published_at=datetime.now(timezone.utc));self.policies[policy_id]=item;return item
    def get_policy(self,policy_id,user_id):
        item=self.policies.get(policy_id);return item if item and item.created_by==user_id else None
    def list_policies(self,workspace_id,user_id):return [x for x in self.policies.values() if x.workspace_id==workspace_id and x.created_by==user_id]
    def evaluation_context(self,run_id,policy_id,user_id):
        ctx=self.run_contexts.get(run_id);policy=self.policies.get(policy_id)
        if not ctx or ctx["user_id"]!=user_id or not policy or policy.created_by!=user_id or policy.status!="published":return None
        baseline=next((x for x in self.baselines.values() if x.application_id==ctx["application_id"] and x.active),None)
        return {"run_id":run_id,"application_id":ctx["application_id"],"policy_id":policy_id,"rules":deepcopy(policy.rules),"baseline_run_id":baseline.run_id if baseline else None}
    def save_evaluation(self,run_id,baseline_run_id,policy_id,status,results,user_id):
        item=GateEvaluationRecord(uuid4().hex,run_id,baseline_run_id,policy_id,status,deepcopy(results),user_id,datetime.now(timezone.utc));self.evaluations.append(item);return item
    def list_evaluations(self,run_id,user_id):return [x for x in self.evaluations if x.run_id==run_id and x.evaluated_by==user_id]


class GateService:
    def __init__(self, gates: GateRepository, reporting: ReportingRepository) -> None:
        self.gates=gates;self.reporting=reporting
    def evaluate(self,run_id,policy_id,user_id):
        context=self.gates.evaluation_context(run_id,policy_id,user_id)
        if context is None:return None
        reporter=ReportService(self.reporting)
        candidate=reporter.summary(run_id,user_id)
        if candidate is None:return None
        baseline_id=context["baseline_run_id"]
        baseline=reporter.summary(baseline_id,user_id) if baseline_id else None
        status,results=evaluate_rules(candidate,baseline,context["rules"])
        item=self.gates.save_evaluation(run_id,baseline_id,policy_id,status,results,user_id)
        self.reporting.attach_gate(run_id,user_id,{
            "gate_evaluation_id":item.gate_evaluation_id,
            "baseline_run_id":item.baseline_run_id,
            "policy_id":item.policy_id,
            "status":item.status,
            "results":deepcopy(item.results),
            "evaluated_at":item.evaluated_at.isoformat(),
        })
        return item


@lru_cache(maxsize=1)
def get_gate_repository() -> PostgresGateRepository:
    return PostgresGateRepository()
