import argparse
import json
from pathlib import Path
from statistics import mean
from uuid import uuid4

from app.evaluation.evaluators import AnswerQualityEvaluator
from app.evaluation.runs import CaseExecution, EvaluationRunner, InMemoryEvaluationRunRepository, RunCase
from app.workflows import run_research_workflow


PROJECT_ROOT=Path(__file__).resolve().parents[1]
DATASET_PATH=PROJECT_ROOT/"evaluations/datasets/answer_quality.json"
DEFAULT_OUTPUT_PATH=PROJECT_ROOT/"evaluations/results/answer_quality.json"


def load_dataset()->list[dict]:
    value=json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    if not isinstance(value,list):raise ValueError("答案质量数据集顶层必须是列表")
    return value


def main()->None:
    parser=argparse.ArgumentParser(description="运行ResearchFlow端到端答案质量评估")
    parser.add_argument("--limit",type=int)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--min-overall-score",type=float,default=0.90)
    parser.add_argument("--min-route-accuracy",type=float,default=0.90)
    args=parser.parse_args();dataset=load_dataset()
    if args.limit is not None:
        if args.limit<=0:raise ValueError("limit必须大于0")
        dataset=dataset[:args.limit]
    cases=[RunCase(str(x["id"]),str(x["id"]),{"question":x["question"]},{"should_answer":x["should_answer"],"expected_keywords":x["expected_keywords"]},{}) for x in dataset]
    repository=InMemoryEvaluationRunRepository();created=repository.create_run(workspace_id="local-cli",agent_version_id="current-workflow",dataset_version_id="answer-quality-json",trigger_type="cli",config_snapshot={"schema_version":"1.0","evaluator":"answer_quality:1.0.0"},git_commit=None,user_id="local-cli")
    def execute(case:RunCase)->CaseExecution:
        result=run_research_workflow(question=str(case.input["question"]),thread_id=f"eval-{case.external_id}-{uuid4().hex}")
        return CaseExecution(output={"answer":result["answer"],"route":result["route"]},evidence=list(result["evidence"]),trace={})
    final=EvaluationRunner(repository).run(run_id=created.run_id,user_id="local-cli",cases=cases,execute_case=execute,evaluators=[AnswerQualityEvaluator()])
    if final.status=="failed":raise RuntimeError(final.error)
    results={x.case_id:x for x in repository.list_case_results(created.run_id,"local-cli")}
    metrics=repository.list_metrics(created.run_id,"local-cli");metric_map={(x.case_result_id,x.metric_key):x.value for x in metrics}
    rows=[]
    for case in cases:
        result=results[case.case_id];values={key:metric_map[(result.case_result_id,key)] for key in ("route_correct","keyword_recall","citation_validity","citation_present","refusal_correct","overall_score")}
        for boolean_key in ("route_correct","citation_present","refusal_correct"):
            values[boolean_key]=bool(values[boolean_key])
        row={"id":case.external_id,"question":case.input["question"],"answer":result.output_json["answer"],"route":result.output_json["route"],"evidence_count":len(result.evidence_json),"metrics":values};rows.append(row);print(f"{case.external_id}: route={row['route']} score={values['overall_score']:.3f}")
    summary={"case_count":len(rows),"mean_overall_score":mean(x["metrics"]["overall_score"] for x in rows),"route_accuracy":mean(x["metrics"]["route_correct"] for x in rows),"mean_keyword_recall":mean(x["metrics"]["keyword_recall"] for x in rows)}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({"summary":summary,"cases":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2));print(f"报告已写入：{args.output}")
    passed=summary["mean_overall_score"]>=args.min_overall_score and summary["route_accuracy"]>=args.min_route_accuracy
    print(f"质量门禁：{'通过' if passed else '失败'}")
    if not passed:raise SystemExit(2)


if __name__=="__main__":main()
