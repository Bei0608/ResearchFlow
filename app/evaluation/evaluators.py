from __future__ import annotations

from app.evaluation.answer_quality import evaluate_answer
from app.evaluation.runs import CaseExecution, MetricValue, RunCase


class AnswerQualityEvaluator:
    key = "answer_quality"
    version = "1.0.0"

    def evaluate(self, case: RunCase, execution: CaseExecution) -> list[MetricValue]:
        quality = evaluate_answer(
            answer=str(execution.output["answer"]),
            route=str(execution.output["route"]),
            should_answer=bool(case.expected["should_answer"]),
            expected_keywords=list(case.expected.get("expected_keywords", [])),
            evidence_count=len(execution.evidence),
        )
        return [
            MetricValue(self.key,self.version,name,float(value),{})
            for name,value in quality.to_dict().items()
        ]


class RetrievalQualityEvaluator:
    key = "retrieval_quality"
    version = "1.0.0"

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def evaluate(self, case: RunCase, execution: CaseExecution) -> list[MetricValue]:
        expected=set(case.expected["expected_sources"])
        retrieved=list(execution.output["retrieved_sources"])
        matched=expected & set(retrieved)
        reciprocal_rank=0.0
        for rank,source in enumerate(retrieved,start=1):
            if source in expected:
                reciprocal_rank=1.0/rank
                break
        values={
            f"hit_at_{self.top_k}":float(bool(matched)),
            f"recall_at_{self.top_k}":len(matched)/len(expected),
            "reciprocal_rank":reciprocal_rank,
        }
        details={"expected_sources":sorted(expected),"retrieved_sources":retrieved}
        return [MetricValue(self.key,self.version,name,value,details) for name,value in values.items()]


class StaticCaseMetricEvaluator:
    """仅用于明确标记的预生成demo，不代表重新执行模型评测。"""

    key = "bundled_demo_metrics"
    version = "1.0.0"

    def __init__(self, values_by_external_id: dict[str, dict[str, float]]) -> None:
        self.values_by_external_id = values_by_external_id

    def evaluate(self, case: RunCase, execution: CaseExecution) -> list[MetricValue]:
        values = self.values_by_external_id.get(case.external_id)
        if values is None:
            raise ValueError(f"演示指标缺少案例：{case.external_id}")
        return [
            MetricValue(self.key,self.version,name,float(value),{"origin":"bundled_demo_fixture"})
            for name,value in values.items()
        ]
