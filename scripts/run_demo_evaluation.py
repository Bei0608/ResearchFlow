import argparse
import json
from pathlib import Path

from app.evaluation.catalog import get_evaluation_catalog_repository
from app.evaluation.evaluators import StaticCaseMetricEvaluator
from app.evaluation.runs import CaseExecution, EvaluationRunner, RunCase, get_evaluation_run_repository, summarize_program_metrics


ROOT=Path(__file__).resolve().parents[1]


def _load(path:Path)->dict:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):raise ValueError(f"JSON顶层必须是对象：{path}")
    return value


def parse_args()->argparse.Namespace:
    parser=argparse.ArgumentParser(description="将P1预生成demo通过统一Runner持久化；不会调用外部模型")
    parser.add_argument("--workspace-id",required=True)
    parser.add_argument("--user-id",required=True)
    parser.add_argument("--agent-version-id",required=True)
    parser.add_argument("--dataset-id",required=True)
    parser.add_argument("--dataset-version-id",required=True)
    parser.add_argument("--git-commit")
    parser.add_argument("--run-file",type=Path,default=ROOT/"evaluations/demo/agent_run.json")
    parser.add_argument("--metrics-file",type=Path,default=ROOT/"evaluations/demo/program_metrics.json")
    parser.add_argument(
        "--simulate-failure-case",
        help="仅用于验收部分失败保留；填写一个demo case_id",
    )
    return parser.parse_args()


def main()->None:
    args=parse_args();run_fixture=_load(args.run_file);metric_fixture=_load(args.metrics_file)
    if run_fixture.get("environment")!="demo" or metric_fixture.get("environment")!="demo":raise ValueError("只允许明确标记environment=demo的预生成输入")
    catalog=get_evaluation_catalog_repository();repository=get_evaluation_run_repository()
    version=catalog.get_dataset_version(args.dataset_id,args.dataset_version_id,args.user_id)
    if version is None or version.status!="published":raise ValueError("DatasetVersion不存在或尚未发布")
    cases_by_external={x.external_id:x for x in catalog.list_cases(args.dataset_id,args.dataset_version_id,args.user_id)}
    output_by_external={str(x["case_id"]):x for x in run_fixture["results"]}
    metrics_by_external={str(x["case_id"]):{k:float(v) for k,v in x.items() if k!="case_id"} for x in metric_fixture["case_metrics"]}
    cases=[RunCase(x.case_id,x.external_id,x.input_json,x.expected_json,x.metadata_json) for x in cases_by_external.values()]
    created=repository.create_run(workspace_id=args.workspace_id,agent_version_id=args.agent_version_id,dataset_version_id=args.dataset_version_id,trigger_type="bundled_demo_fixture",config_snapshot={"schema_version":"1.0","execution":"pre_generated_no_external_model_required","evaluator":"bundled_demo_metrics:1.0.0"},git_commit=args.git_commit,user_id=args.user_id)
    if created is None:raise ValueError("无法创建运行：请确认Workspace与两个版本均已发布且属于同一Workspace")
    def execute(case:RunCase)->CaseExecution:
        if case.external_id == args.simulate_failure_case:
            raise RuntimeError("simulated demo case failure")
        row=output_by_external[case.external_id]
        return CaseExecution(output={"answer":row["answer"],"route":row["actual_route"]},evidence=list(row.get("evidence",[])),trace={"origin":"bundled_demo_fixture"},latency_ms=int(row["latency_ms"]),token_usage=dict(row.get("token_usage",{})))
    final=EvaluationRunner(repository).run(run_id=created.run_id,user_id=args.user_id,cases=cases,execute_case=execute,evaluators=[StaticCaseMetricEvaluator(metrics_by_external)])
    metrics=repository.list_metrics(created.run_id,args.user_id)
    print(json.dumps({"run_id":final.run_id,"status":final.status,"case_count":len(repository.list_case_results(final.run_id,args.user_id)),"metric_count":len(metrics),"summary":summarize_program_metrics(metrics),"source":"program","execution":"pre_generated_demo_fixture"},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
