import pytest

from app.evaluation import evaluate_answer


def test_answerable_response_scores_keywords_and_citations() -> None:
    result = evaluate_answer(
        answer="模型使用Transformer并输出动作token。[资料1]",
        route="answer",
        should_answer=True,
        expected_keywords=["Transformer", "token"],
        evidence_count=2,
    )
    assert result.route_correct is True
    assert result.keyword_recall == 1.0
    assert result.citation_validity == 1.0
    assert result.citation_present is True
    assert result.overall_score == pytest.approx(1.0)


def test_invalid_citation_and_missing_keyword_reduce_score() -> None:
    result = evaluate_answer(
        answer="模型输出动作。[资料3]",
        route="answer",
        should_answer=True,
        expected_keywords=["动作", "token"],
        evidence_count=2,
    )
    assert result.keyword_recall == 0.5
    assert result.citation_validity == 0.0
    assert result.overall_score < 1.0


def test_unanswerable_requires_insufficient_route_and_exact_refusal() -> None:
    result = evaluate_answer(
        answer="根据当前论文资料无法确定。",
        route="insufficient",
        should_answer=False,
        expected_keywords=[],
        evidence_count=0,
    )
    assert result.route_correct is True
    assert result.refusal_correct is True
    assert result.overall_score == 1.0
