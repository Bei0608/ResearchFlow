from datetime import datetime, timezone

from app.evaluation.reporting import (
    InMemoryReportingRepository,
    ReportService,
    aggregate_records,
    build_summary,
)


def reporting_snapshot() -> dict:
    return {
        "run": {
            "run_id": "run-1", "workspace_id": "ws-1", "status": "ready_for_review",
            "trigger_type": "demo", "config_snapshot": {"unsafe": "<script>alert(1)</script>"},
            "git_commit": "abc123", "created_at": "2026-11-06T00:00:00+00:00",
            "started_at": None, "finished_at": None, "agent_version_id": "agent-1",
            "agent_version": "1.0", "application_name": "Research Agent",
            "dataset_version_id": "dataset-1", "dataset_version": "1.0",
            "environment": "demo", "dataset_name": "Demo Dataset",
        },
        "cases": [
            {"case_result_id": "cr-1", "case_id": "c-1", "external_id": "case-1",
             "input_json": {"q": "one"}, "expected_json": {}, "status": "succeeded",
             "output_json": {"answer": "ok"}, "evidence_json": [], "latency_ms": 10,
             "token_usage_json": {}, "error": None},
            {"case_result_id": "cr-2", "case_id": "c-2", "external_id": "case-2",
             "input_json": {"q": "two"}, "expected_json": {}, "status": "succeeded",
             "output_json": {"answer": "partial"}, "evidence_json": [], "latency_ms": 12,
             "token_usage_json": {}, "error": None},
            {"case_result_id": "cr-3", "case_id": "c-3", "external_id": "case-3",
             "input_json": {"q": "three"}, "expected_json": {}, "status": "failed",
             "output_json": {}, "evidence_json": [], "latency_ms": 4,
             "token_usage_json": {}, "error": "model unavailable"},
        ],
        "program_metrics": [
            {"case_result_id": "cr-1", "evaluator_key": "quality", "evaluator_version": "1.0", "metric_key": "correct", "value": 1.0},
            {"case_result_id": "cr-2", "evaluator_key": "quality", "evaluator_version": "1.0", "metric_key": "correct", "value": 0.0},
            {"case_result_id": "cr-1", "evaluator_key": "quality", "evaluator_version": "1.0", "metric_key": "coverage", "value": 0.8},
        ],
        "reviews": [
            {"review_id": "r-1", "case_result_id": "cr-1", "status": "submitted", "rubric_version_id": "rubric-1"},
            {"review_id": "r-2", "case_result_id": "cr-2", "status": "draft", "rubric_version_id": "rubric-1"},
            {"review_id": "r-3", "case_result_id": "cr-3", "status": "pending", "rubric_version_id": "rubric-1"},
        ],
        "human_dimensions": [
            {"rubric_version_id": "rubric-1", "rubric_version": "1.0", "criterion_key": "faithfulness", "criterion_title": "忠实度", "min_score": 1.0, "max_score": 5.0, "weight": 0.6},
            {"rubric_version_id": "rubric-1", "rubric_version": "1.0", "criterion_key": "completeness", "criterion_title": "完整度", "min_score": 1.0, "max_score": 5.0, "weight": 0.4},
        ],
        "human_scores": [
            {"case_result_id": "cr-1", "reviewer_id": "owner-1", "rubric_version_id": "rubric-1",
             "rubric_version": "1.0", "revision": 4, "criterion_key": "faithfulness",
             "criterion_title": "忠实度", "min_score": 1.0, "max_score": 5.0,
             "weight": 0.6, "score": 4.0, "comment": "latest only"},
            {"case_result_id": "cr-1", "reviewer_id": "owner-1", "rubric_version_id": "rubric-1",
             "rubric_version": "1.0", "revision": 4, "criterion_key": "completeness",
             "criterion_title": "完整度", "min_score": 1.0, "max_score": 5.0,
             "weight": 0.4, "score": 3.0, "comment": "latest only"},
        ],
    }


def test_summary_separates_sources_and_counts_missing() -> None:
    summary = build_summary(reporting_snapshot(), calculated_at=datetime(2026, 11, 6, tzinfo=timezone.utc))
    assert summary["case_counts"] == {"total": 3, "succeeded": 2, "failed": 1, "skipped": 0}
    assert summary["review_progress"] == {
        "total_count": 3, "pending_count": 1, "draft_count": 1,
        "submitted_count": 1, "completion_rate": 1 / 3,
    }
    correct = next(x for x in summary["program_metrics"] if x["metric_key"] == "correct")
    assert correct["value"] == 0.5
    assert correct["sample_count"] == 2 and correct["missing_count"] == 1
    assert correct["pass_rate"] == 0.5
    coverage = next(x for x in summary["program_metrics"] if x["metric_key"] == "coverage")
    assert coverage["pass_rate"] is None
    faithfulness = next(x for x in summary["human_metrics"] if x["metric_key"] == "faithfulness")
    assert faithfulness["value"] == 4.0
    assert faithfulness["sample_count"] == 1 and faithfulness["missing_count"] == 2
    assert all(x["source"] == "program" for x in summary["program_metrics"])
    assert all(x["source"] == "human" for x in summary["human_metrics"])
    assert len(aggregate_records(summary)) == 4


def test_report_generation_escapes_html_and_persists_hash(tmp_path) -> None:
    repository = InMemoryReportingRepository()
    repository.seed_snapshot("run-1", "owner-1", reporting_snapshot())
    service = ReportService(repository, output_dir=tmp_path)
    reports = service.generate("run-1", "owner-1")
    assert reports is not None and {x.format for x in reports} == {"json", "html"}
    assert all(x.status == "completed" and len(x.content_hash or "") == 64 for x in reports)
    html_report = next(x for x in reports if x.format == "html")
    html = service.resolve_content(html_report).read_text(encoding="utf-8")  # type: ignore[union-attr]
    assert "<script>alert(1)</script>" not in html
    assert r"\u003cscript\u003ealert(1)\u003c/script\u003e" in html or "&lt;script&gt;" in html


def test_failed_report_is_recorded_and_retry_can_succeed(tmp_path, monkeypatch) -> None:
    repository = InMemoryReportingRepository()
    repository.seed_snapshot("run-1", "owner-1", reporting_snapshot())
    service = ReportService(repository, output_dir=tmp_path)
    original = service._render

    def fail_html(format, summary):
        if format == "html":
            raise RuntimeError("template failed")
        return original(format, summary)

    monkeypatch.setattr(service, "_render", fail_html)
    first = service.generate("run-1", "owner-1")
    assert first is not None
    assert [x.status for x in first] == ["completed", "failed"]
    assert "template failed" in (first[1].error or "")
    monkeypatch.setattr(service, "_render", original)
    retry = service.generate("run-1", "owner-1")
    assert retry is not None and all(x.status == "completed" for x in retry)
    assert len(repository.list_reports("run-1", "owner-1")) == 4
