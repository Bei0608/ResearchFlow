import pytest

import app.workflows.research_workflow as workflow_module
from app.rag.retriever import RetrievedChunk
from app.workflows.research_workflow import (
    build_citations,
    build_research_workflow,
    evaluate_evidence_node,
    format_evidence_context,
    prepare_question_node,
)


def make_chunk(
    *,
    content: str = "RT-2 represents actions as tokens.",
    score: float = 0.8,
    chunk_id: str = "chunk-1",
    source_file: str = "RT-2.pdf",
    page_number: int = 4,
) -> RetrievedChunk:
    """创建不依赖Milvus的Retriever测试结果。"""
    return RetrievedChunk(
        content=content,
        score=score,
        chunk_id=chunk_id,
        source_file=source_file,
        page_number=page_number,
        metadata={},
    )


def initial_state(
    question: str = "RT-2如何表示机器人动作？",
    min_score: float = 0.45,
) -> dict:
    """创建整图测试的初始状态。"""
    return {
        "question": question,
        "top_k": 5,
        "min_score": min_score,
        "evidence": [],
        "answer": "",
        "citations": [],
        "executed_nodes": [],
    }


def test_prepare_question_normalizes_input() -> None:
    result = prepare_question_node(
        {
            "question": "  RT-2是什么？  ",
            "top_k": 3,
            "min_score": 0.5,
        }
    )

    assert result["normalized_question"] == "RT-2是什么？"
    assert result["top_k"] == 3
    assert result["min_score"] == 0.5


@pytest.mark.parametrize(
    ("state", "message"),
    [
        ({"question": ""}, "问题不能为空"),
        (
            {"question": "test", "top_k": 0},
            "top_k必须在1到10之间",
        ),
        (
            {"question": "test", "min_score": 1.1},
            "min_score必须在0到1之间",
        ),
    ],
)
def test_prepare_question_rejects_invalid_input(
    state: dict,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_question_node(state)


def test_evaluate_evidence_filters_low_scores() -> None:
    result = evaluate_evidence_node(
        {
            "min_score": 0.45,
            "evidence": [
                {
                    "content": "high",
                    "score": 0.8,
                    "chunk_id": "high",
                    "source_file": "paper.pdf",
                    "page_number": 1,
                },
                {
                    "content": "low",
                    "score": 0.2,
                    "chunk_id": "low",
                    "source_file": "paper.pdf",
                    "page_number": 2,
                },
            ],
            "error": None,
        }
    )

    assert result["route"] == "answer"
    assert result["evidence_sufficient"] is True
    assert [item["chunk_id"] for item in result["evidence"]] == [
        "high"
    ]


def test_format_context_and_citations_use_physical_page() -> None:
    evidence = [
        {
            "content": "evidence one",
            "score": 0.8,
            "chunk_id": "one",
            "source_file": "paper.pdf",
            "page_number": 3,
        },
        {
            "content": "evidence two",
            "score": 0.7,
            "chunk_id": "two",
            "source_file": "paper.pdf",
            "page_number": 3,
        },
    ]

    context = format_evidence_context(evidence)
    citations = build_citations(evidence)

    assert "[资料1]" in context
    assert "[资料2]" in context
    assert "PDF物理页码：3" in context
    assert citations == ["paper.pdf，PDF物理页码3"]


def test_graph_routes_relevant_evidence_to_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow_module,
        "retrieve_relevant_chunks",
        lambda query, top_k: [make_chunk(score=0.8)],
    )

    def fake_generate_answer(state: dict) -> dict:
        return {
            "answer": "基于论文证据的答案。[资料1]",
            "citations": build_citations(state["evidence"]),
            "executed_nodes": ["generate_answer"],
        }

    monkeypatch.setattr(
        workflow_module,
        "generate_answer_node",
        fake_generate_answer,
    )
    monkeypatch.setattr(
        workflow_module,
        "judge_answerability_node",
        lambda state: {
            "evidence_sufficient": True,
            "route": "answer",
            "judge_reason": "证据直接回答",
            "executed_nodes": ["judge_answerability"],
        },
    )

    graph = build_research_workflow()
    result = graph.invoke(initial_state())

    assert result["route"] == "answer"
    assert result["answer"] == "基于论文证据的答案。[资料1]"
    assert result["citations"] == [
        "RT-2.pdf，PDF物理页码4"
    ]
    assert result["executed_nodes"] == [
        "prepare_question",
        "retrieve_evidence",
        "evaluate_evidence",
        "judge_answerability",
        "generate_answer",
    ]


def test_graph_rejects_topically_related_but_insufficient_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow_module,
        "retrieve_relevant_chunks",
        lambda query, top_k: [make_chunk(score=0.8)],
    )
    monkeypatch.setattr(
        workflow_module,
        "judge_answerability_node",
        lambda state: {
            "evidence_sufficient": False,
            "route": "insufficient",
            "judge_reason": "证据未包含指定硬件延迟",
            "executed_nodes": ["judge_answerability"],
        },
    )

    graph = build_research_workflow()
    result = graph.invoke(
        initial_state("RT-2在RTX 4090上的延迟是多少？")
    )

    assert result["route"] == "insufficient"
    assert result["answer"] == "根据当前论文资料无法确定。"
    assert result["judge_reason"] == "证据未包含指定硬件延迟"


def test_graph_routes_low_score_to_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow_module,
        "retrieve_relevant_chunks",
        lambda query, top_k: [make_chunk(score=0.2)],
    )

    graph = build_research_workflow()
    result = graph.invoke(initial_state())

    assert result["route"] == "insufficient"
    assert result["evidence"] == []
    assert result["answer"] == "根据当前论文资料无法确定。"
    assert result["citations"] == []
    assert result["executed_nodes"][-1] == "insufficient_answer"


def test_graph_routes_retriever_exception_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_retriever(query: str, top_k: int) -> list:
        raise RuntimeError("Milvus unavailable")

    monkeypatch.setattr(
        workflow_module,
        "retrieve_relevant_chunks",
        failing_retriever,
    )

    graph = build_research_workflow()
    result = graph.invoke(initial_state())

    assert result["route"] == "error"
    assert result["error"] == "RuntimeError"
    assert result["answer"] == (
        "论文检索服务暂时不可用，请稍后重试。"
    )
    assert result["citations"] == []
    assert result["executed_nodes"][-1] == "error_answer"
