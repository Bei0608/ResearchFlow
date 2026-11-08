from operator import add
from typing import Annotated, Literal, TypedDict


class ResearchEvidence(TypedDict):
    """工作流使用的一条论文证据。"""

    content: str
    score: float
    chunk_id: str
    source_file: str
    page_number: int


class ResearchWorkflowState(TypedDict, total=False):
    """论文研究工作流在节点之间共享的状态。"""

    question: str
    normalized_question: str
    top_k: int
    min_score: float
    evidence: list[ResearchEvidence]
    evidence_sufficient: bool
    judge_reason: str
    route: Literal["answer", "insufficient", "error"]
    answer: str
    citations: list[str]
    error: str | None
    executed_nodes: Annotated[list[str], add]
