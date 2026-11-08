import pytest

from app.evaluation.evaluators import AnswerQualityEvaluator, RetrievalQualityEvaluator
from app.evaluation.runs import CaseExecution, EvaluationRunner, InMemoryEvaluationRunRepository, RunCase


def _run(repository: InMemoryEvaluationRunRepository, user_id: str = "user-1"):
    return repository.create_run(workspace_id="workspace",agent_version_id="agent",dataset_version_id="dataset",trigger_type="test",config_snapshot={"schema_version":"1.0"},git_commit="abc",user_id=user_id)


def test_runner_persists_results_metrics_and_ready_status() -> None:
    repository=InMemoryEvaluationRunRepository();run=_run(repository)
    case=RunCase("case-1","external-1",{"question":"Q"},{"should_answer":True,"expected_keywords":["answer"]},{})
    final=EvaluationRunner(repository).run(run_id=run.run_id,user_id="user-1",cases=[case],execute_case=lambda _:CaseExecution({"answer":"answer [资料1]","route":"answer"},[{"source":"doc"}],{}),evaluators=[AnswerQualityEvaluator()])
    assert final.status=="ready_for_review"
    results=repository.list_case_results(run.run_id,"user-1")
    assert len(results)==1 and results[0].status=="succeeded"
    metrics=repository.list_metrics(run.run_id,"user-1")
    assert {x.metric_key for x in metrics} >= {"overall_score","route_correct","keyword_recall"}
    assert all(x.source=="program" for x in metrics)


def test_runner_keeps_partial_results_when_one_case_fails() -> None:
    repository=InMemoryEvaluationRunRepository();run=_run(repository)
    cases=[RunCase("ok","ok",{}, {"expected_sources":["doc"]},{}),RunCase("bad","bad",{}, {"expected_sources":["doc"]},{})]
    def execute(case):
        if case.case_id=="bad":raise RuntimeError("provider unavailable")
        return CaseExecution({"retrieved_sources":["doc"]},[],{})
    final=EvaluationRunner(repository).run(run_id=run.run_id,user_id="user-1",cases=cases,execute_case=execute,evaluators=[RetrievalQualityEvaluator()])
    assert final.status=="failed"
    assert "provider unavailable" in final.error
    results=repository.list_case_results(run.run_id,"user-1")
    assert [x.status for x in results]==["succeeded","failed"]
    assert len(repository.list_metrics(run.run_id,"user-1"))==3


def test_runner_rejects_foreign_user() -> None:
    repository=InMemoryEvaluationRunRepository();run=_run(repository)
    with pytest.raises(ValueError,match="不存在或无写权限"):
        EvaluationRunner(repository).run(run_id=run.run_id,user_id="other",cases=[],execute_case=lambda _:None,evaluators=[])


def test_completed_run_cannot_be_started_again() -> None:
    repository = InMemoryEvaluationRunRepository()
    run = _run(repository)
    repository.transition_run(run.run_id, "user-1", "running")
    repository.transition_run(run.run_id, "user-1", "ready_for_review")
    assert repository.transition_run(run.run_id, "user-1", "running") is None


def test_metric_persistence_failure_does_not_duplicate_case_result() -> None:
    class FailingMetricRepository(InMemoryEvaluationRunRepository):
        def save_metric(self, **kwargs):
            return None

    repository = FailingMetricRepository()
    run = _run(repository)
    case = RunCase(
        "case-1",
        "case-1",
        {},
        {"expected_sources": ["doc"]},
        {},
    )
    final = EvaluationRunner(repository).run(
        run_id=run.run_id,
        user_id="user-1",
        cases=[case],
        execute_case=lambda _: CaseExecution(
            {"retrieved_sources": ["doc"]}, [], {}
        ),
        evaluators=[RetrievalQualityEvaluator()],
    )
    assert final.status == "failed"
    assert "无法保存程序指标" in final.error
    assert len(repository.list_case_results(run.run_id, "user-1")) == 1
