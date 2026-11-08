import re
from dataclasses import asdict, dataclass


REFUSAL_ANSWER = "根据当前论文资料无法确定。"
CITATION_PATTERN = re.compile(r"\[资料(\d+)\]")


@dataclass(frozen=True)
class AnswerQualityResult:
    """一条回答的确定性质量指标。"""

    route_correct: bool
    keyword_recall: float
    citation_validity: float
    citation_present: bool
    refusal_correct: bool
    overall_score: float

    def to_dict(self) -> dict[str, bool | float]:
        return asdict(self)


def _keyword_recall(
    answer: str,
    expected_keywords: list[str],
) -> float:
    if not expected_keywords:
        return 1.0
    matched = sum(
        keyword.casefold() in answer.casefold()
        for keyword in expected_keywords
    )
    return matched / len(expected_keywords)


def _citation_validity(
    answer: str,
    evidence_count: int,
) -> tuple[float, bool]:
    citation_numbers = [
        int(value)
        for value in CITATION_PATTERN.findall(answer)
    ]
    if not citation_numbers:
        return 0.0, False
    valid_count = sum(
        1 <= number <= evidence_count
        for number in citation_numbers
    )
    return valid_count / len(citation_numbers), True


def evaluate_answer(
    *,
    answer: str,
    route: str,
    should_answer: bool,
    expected_keywords: list[str],
    evidence_count: int,
) -> AnswerQualityResult:
    """评估路由、要点覆盖、引用合法性和拒答行为。"""
    route_correct = route == (
        "answer" if should_answer else "insufficient"
    )
    keyword_recall = (
        _keyword_recall(answer, expected_keywords)
        if should_answer
        else 1.0
    )
    citation_validity, citation_present = _citation_validity(
        answer,
        evidence_count,
    )
    refusal_correct = (
        answer.strip() == REFUSAL_ANSWER
        if not should_answer
        else True
    )

    if should_answer:
        overall_score = (
            0.25 * float(route_correct)
            + 0.35 * keyword_recall
            + 0.25 * citation_validity
            + 0.15 * float(citation_present)
        )
    else:
        overall_score = (
            0.5 * float(route_correct)
            + 0.5 * float(refusal_correct)
        )

    return AnswerQualityResult(
        route_correct=route_correct,
        keyword_recall=keyword_recall,
        citation_validity=citation_validity,
        citation_present=citation_present,
        refusal_correct=refusal_correct,
        overall_score=overall_score,
    )
