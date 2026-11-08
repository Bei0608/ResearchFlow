"""Idempotently bootstrap the complete no-model demo platform into PostgreSQL."""

import argparse
import json
import os
from pathlib import Path

from pwdlib import PasswordHash

from app.applications import get_application_repository
from app.demo_data import verify_demo_bundle
from app.evaluation.catalog import get_evaluation_catalog_repository
from app.evaluation.catalog_importer import import_dataset_payload, import_rubric_payload
from app.evaluation.evaluators import StaticCaseMetricEvaluator
from app.evaluation.gates import GateService, get_gate_repository
from app.evaluation.reporting import ReportService, get_reporting_repository
from app.evaluation.reviews import get_review_repository
from app.evaluation.runs import (
    CaseExecution, EvaluationRunner, RunCase, get_evaluation_run_repository,
)
from app.security import get_identity_repository
from app.workspaces import get_workspace_repository


ROOT = Path(__file__).resolve().parents[1]
PASSWORD_ENV = "RESEARCHFLOW_DEMO_PASSWORD"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON顶层必须是对象：{path}")
    return value


def _ensure_run(*, role, workspace_id, user_id, agent_version_id,
                dataset, run_fixture, metric_fixture):
    repository = get_evaluation_run_repository()
    existing = next(
        (x for x in repository.list_runs(workspace_id, user_id)
         if x.agent_version_id == agent_version_id
         and x.dataset_version_id == dataset.dataset_version_id
         and x.config_snapshot.get("demo_role") == role),
        None,
    )
    if existing:
        return existing
    catalog = get_evaluation_catalog_repository()
    cases = [
        RunCase(x.case_id,x.external_id,x.input_json,x.expected_json,x.metadata_json)
        for x in catalog.list_cases(dataset.dataset_id,dataset.dataset_version_id,user_id)
    ]
    outputs = {str(x["case_id"]):x for x in run_fixture["results"]}
    metrics = {
        str(x["case_id"]):{k:float(v) for k,v in x.items() if k!="case_id"}
        for x in metric_fixture["case_metrics"]
    }
    created = repository.create_run(
        workspace_id=workspace_id, agent_version_id=agent_version_id,
        dataset_version_id=dataset.dataset_version_id,
        trigger_type="bundled_demo_fixture",
        config_snapshot={"schema_version":"1.0","demo_role":role,
                         "execution":"pre_generated_no_external_model_required",
                         "evaluator":"bundled_demo_metrics:1.0.0"},
        git_commit=None, user_id=user_id,
    )
    if created is None:
        raise RuntimeError("无法创建demo Evaluation Run")
    def execute(case: RunCase) -> CaseExecution:
        row=outputs[case.external_id]
        return CaseExecution(
            output={"answer":row["answer"],"route":row["actual_route"]},
            evidence=list(row.get("evidence",[])),
            trace={"origin":"bundled_demo_fixture"},
            latency_ms=int(row["latency_ms"]),
            token_usage=dict(row.get("token_usage",{})),
        )
    return EvaluationRunner(repository).run(
        run_id=created.run_id,user_id=user_id,cases=cases,execute_case=execute,
        evaluators=[StaticCaseMetricEvaluator(metrics)],
    )


def main() -> None:
    parser=argparse.ArgumentParser(description="从空数据库幂等建立ResearchFlow完整demo")
    parser.add_argument("--username",default="researchflow-demo")
    args=parser.parse_args()
    bundle=verify_demo_bundle(ROOT)
    identity=get_identity_repository();user=identity.get_user_by_username(args.username)
    if user is None:
        password=os.getenv(PASSWORD_ENV,"")
        if len(password)<8:
            raise ValueError(f"首次创建用户前请设置至少8位的{PASSWORD_ENV}")
        user=identity.create_user(args.username,PasswordHash.recommended().hash(password))
    workspace=get_workspace_repository().ensure_personal_workspace(user.user_id,user.username)

    applications=get_application_repository()
    application=next((x for x in applications.list_applications(workspace.workspace_id,user.user_id)
                      if x.name=="ResearchFlow Demo Agent"),None)
    if application is None:
        application=applications.create_application(
            workspace_id=workspace.workspace_id,user_id=user.user_id,
            name="ResearchFlow Demo Agent",description="可复现的无模型评测演示",
            target_type="internal")
    version=next((x for x in applications.list_versions(application.application_id,user.user_id)
                  if x.version=="1.1-demo"),None)
    if version is None:
        version=applications.create_version(
            application_id=application.application_id,user_id=user.user_id,
            version="1.1-demo",config_snapshot={"schema_version":"1.0","mode":"bundled_demo"},
            git_commit=None)
    if version.status!="published":
        version=applications.publish_version(application.application_id,version.agent_version_id,user.user_id)

    catalog=get_evaluation_catalog_repository()
    dataset=import_dataset_payload(catalog,workspace_id=workspace.workspace_id,user_id=user.user_id,
        payload=_load(ROOT/"evaluations/demo/evaluation_dataset.json"))
    rubric=import_rubric_payload(catalog,workspace_id=workspace.workspace_id,user_id=user.user_id,
        payload=_load(ROOT/"evaluations/demo/rubric.json"))
    run_fixture=_load(ROOT/"evaluations/demo/agent_run.json")
    metric_fixture=_load(ROOT/"evaluations/demo/program_metrics.json")
    baseline_run=_ensure_run(role="baseline",workspace_id=workspace.workspace_id,user_id=user.user_id,
        agent_version_id=version.agent_version_id,dataset=dataset,
        run_fixture=run_fixture,metric_fixture=metric_fixture)
    candidate_run=_ensure_run(role="candidate",workspace_id=workspace.workspace_id,user_id=user.user_id,
        agent_version_id=version.agent_version_id,dataset=dataset,
        run_fixture=run_fixture,metric_fixture=metric_fixture)

    reviews=get_review_repository()
    task=next((x for x in reviews.list_tasks(user.user_id)
               if x.run_id==candidate_run.run_id and x.name=="Demo人工评审"),None)
    if task is None:
        task=reviews.create_task(run_id=candidate_run.run_id,rubric_version_id=rubric.rubric_version_id,
                                 name="Demo人工评审",reviewer_id=user.user_id,user_id=user.user_id)

    gates=get_gate_repository();baseline=gates.get_active_baseline(application.application_id,user.user_id)
    if baseline is None or baseline.run_id!=baseline_run.run_id:
        baseline=gates.set_baseline(application.application_id,baseline_run.run_id,user.user_id)
    rules=[
        {"rule_id":"citation-validity-min","source":"program",
         "namespace_key":"bundled_demo_metrics@1.0.0","metric_key":"citation_validity",
         "kind":"absolute_min","min_value":0.95},
        {"rule_id":"keyword-recall-regression","source":"program",
         "namespace_key":"bundled_demo_metrics@1.0.0","metric_key":"keyword_recall",
         "kind":"max_regression","max_drop":0.05},
    ]
    policy=next((x for x in gates.list_policies(workspace.workspace_id,user.user_id)
                 if x.name=="Demo Release Gate" and x.version=="1.0"),None)
    if policy is None:
        policy=gates.create_policy(workspace.workspace_id,"Demo Release Gate","1.0",rules,user.user_id)
    if policy.status!="published":
        policy=gates.publish_policy(policy.policy_id,user.user_id)
    evaluations=gates.list_evaluations(candidate_run.run_id,user.user_id)
    gate=next((x for x in reversed(evaluations)
               if x.policy_id==policy.policy_id and x.baseline_run_id==baseline_run.run_id),None)
    if gate is None:
        gate=GateService(gates,get_reporting_repository()).evaluate(candidate_run.run_id,policy.policy_id,user.user_id)
    reporting=get_reporting_repository();reports=reporting.list_reports(candidate_run.run_id,user.user_id)
    if not {x.format for x in reports if x.status=="completed"}>={"json","html"}:
        reports=ReportService(reporting).generate(candidate_run.run_id,user.user_id)

    print(json.dumps({
        "status":"ready","environment":"demo","bundle_sha256":bundle.bundle_sha256,
        "user_id":user.user_id,"username":user.username,"workspace_id":workspace.workspace_id,
        "application_id":application.application_id,"agent_version_id":version.agent_version_id,
        "dataset_version_id":dataset.dataset_version_id,"rubric_version_id":rubric.rubric_version_id,
        "baseline_run_id":baseline_run.run_id,"candidate_run_id":candidate_run.run_id,
        "review_task_id":task.task_id,"gate_status":gate.status,
        "completed_report_formats":sorted({x.format for x in reports if x.status=="completed"}),
    },ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
