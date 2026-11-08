from datetime import datetime, timezone

import pytest

from app.evaluation.catalog import (
    CatalogValidationError,
    CriterionRecord,
    EvaluationCaseRecord,
    dataset_content_hash,
    rubric_content_hash,
    validate_rubric_for_publish,
)


NOW = datetime.now(timezone.utc)


def _case(external_id: str) -> EvaluationCaseRecord:
    return EvaluationCaseRecord(
        case_id=external_id,
        dataset_version_id="version",
        external_id=external_id,
        input_json={"question": external_id},
        expected_json={"answer": external_id},
        metadata_json={},
        created_at=NOW,
    )


def test_dataset_hash_ignores_database_ids_and_input_order() -> None:
    first = [_case("b"), _case("a")]
    second = [_case("a"), _case("b")]
    assert dataset_content_hash(first) == dataset_content_hash(second)


def test_rubric_requires_weights_to_sum_to_one() -> None:
    criterion = CriterionRecord(
        criterion_id="criterion",
        rubric_version_id="version",
        key="faithfulness",
        title="Faithfulness",
        description="",
        min_score=1,
        max_score=5,
        weight=0.8,
        required=True,
        created_at=NOW,
    )
    with pytest.raises(CatalogValidationError, match="weight之和必须为1"):
        validate_rubric_for_publish("Score it", [criterion])


def test_rubric_hash_is_stable() -> None:
    rows = [
        CriterionRecord("1", "v", "b", "B", "", 1, 5, 0.5, True, NOW),
        CriterionRecord("2", "v", "a", "A", "", 1, 5, 0.5, True, NOW),
    ]
    assert rubric_content_hash("Score", rows) == rubric_content_hash(
        "Score", list(reversed(rows))
    )
