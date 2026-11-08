import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from app.evaluation.evaluators import RetrievalQualityEvaluator
from app.evaluation.runs import CaseExecution, EvaluationRunner, InMemoryEvaluationRunRepository, RunCase
from app.rag.retriever import retrieve_relevant_chunks


PROJECT_ROOT=Path(__file__).resolve().parents[1]
QUESTIONS_FILE=PROJECT_ROOT/"evaluations/datasets/questions.json"
PAPERS_DIR=PROJECT_ROOT/"data/papers"
DEFAULT_TOP_K=5
DEFAULT_OUTPUT=PROJECT_ROOT/"evaluations/results/retrieval_quality.json"


def load_questions()->list[dict[str,Any]]:
    value=json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    if not isinstance(value,list):raise ValueError("questions.json的顶层必须是列表")
    return value


def get_available_sources()->set[str]:return {x.name for x in PAPERS_DIR.rglob("*.pdf") if x.is_file()}


def calculate_reciprocal_rank(retrieved_sources:list[str],expected_sources:set[str])->float:
    for rank,source in enumerate(retrieved_sources,start=1):
        if source in expected_sources:return 1.0/rank
    return 0.0


def main()->None:
    parser=argparse.ArgumentParser(description="运行检索评估并执行V1.0质量门禁")
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--min-hit",type=float,default=0.95)
    parser.add_argument("--min-recall",type=float,default=0.95)
    parser.add_argument("--min-mrr",type=float,default=0.90)
    args=parser.parse_args();available=get_available_sources();skipped=0;cases=[]
    for row in load_questions():
        expected=set(row["expected_documents"])
        if not row["should_answer"]:
            print(f"[跳过] {row['id']}：不可回答问题需要在回答层进行评估");skipped+=1;continue
        missing=expected-available
        if missing:
            print(f"[跳过] {row['id']}：知识库缺少 {sorted(missing)}");skipped+=1;continue
        cases.append(RunCase(str(row["id"]),str(row["id"]),{"question":row["question"]},{"expected_sources":sorted(expected)},{}))
    repository=InMemoryEvaluationRunRepository();created=repository.create_run(workspace_id="local-cli",agent_version_id="retriever",dataset_version_id="questions-json",trigger_type="cli",config_snapshot={"schema_version":"1.0","top_k":DEFAULT_TOP_K,"evaluator":"retrieval_quality:1.0.0"},git_commit=None,user_id="local-cli")
    def execute(case:RunCase)->CaseExecution:
        results=retrieve_relevant_chunks(query=str(case.input["question"]),top_k=DEFAULT_TOP_K)
        return CaseExecution(output={"retrieved_sources":[x.source_file for x in results]},evidence=[],trace={})
    final=EvaluationRunner(repository).run(run_id=created.run_id,user_id="local-cli",cases=cases,execute_case=execute,evaluators=[RetrievalQualityEvaluator(DEFAULT_TOP_K)])
    if final.status=="failed":raise RuntimeError(final.error)
    results={x.case_id:x for x in repository.list_case_results(created.run_id,"local-cli")};metrics=repository.list_metrics(created.run_id,"local-cli");values={(x.case_result_id,x.metric_key):x.value for x in metrics};rows=[]
    for case in cases:
        result=results[case.case_id];retrieved=result.output_json["retrieved_sources"];hit=values[(result.case_result_id,"hit_at_5")];recall=values[(result.case_result_id,"recall_at_5")];rr=values[(result.case_result_id,"reciprocal_rank")]
        row={"id":case.external_id,"question":case.input["question"],"expected_sources":case.expected["expected_sources"],"retrieved_sources":retrieved,"hit":hit,"recall":recall,"reciprocal_rank":rr};rows.append(row)
        print("="*80);print(f"问题ID：{case.external_id}");print(f"问题：{case.input['question']}");print(f"期望来源：{case.expected['expected_sources']}");print(f"检索来源：{retrieved}");print(f"命中：{bool(hit)}");print(f"Recall@{DEFAULT_TOP_K}：{recall:.3f}");print(f"Reciprocal Rank：{rr:.3f}")
    print("="*80);print("检索评估汇总");print(f"参与评估问题数：{len(rows)}");print(f"跳过问题数：{skipped}")
    if not rows:print("没有可用于评估的问题");raise SystemExit(1)
    summary={"evaluated_count":len(rows),"skipped_count":skipped,"hit_at_5":mean(x["hit"] for x in rows),"mean_recall_at_5":mean(x["recall"] for x in rows),"mrr":mean(x["reciprocal_rank"] for x in rows)}
    print(f"Hit@5：{summary['hit_at_5']:.3f}");print(f"Mean Recall@5：{summary['mean_recall_at_5']:.3f}");print(f"MRR：{summary['mrr']:.3f}")
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({"summary":summary,"cases":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    passed=summary["hit_at_5"]>=args.min_hit and summary["mean_recall_at_5"]>=args.min_recall and summary["mrr"]>=args.min_mrr
    print(f"质量门禁：{'通过' if passed else '失败'}")
    if not passed:raise SystemExit(2)


if __name__=="__main__":main()
