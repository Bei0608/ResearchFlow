import logging
from functools import lru_cache
from collections.abc import Iterator
from typing import Any, Literal

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.llm.chat import get_chat_model
from app.memory import get_postgres_checkpointer
from app.rag.retriever import (
    RetrievedChunk,
    retrieve_relevant_chunks,
)
from app.workflows.research_state import (
    ResearchEvidence,
    ResearchWorkflowState,
)


logger = logging.getLogger("researchflow.workflow")

DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.45
MAX_TOP_K = 10

ANSWER_SYSTEM_PROMPT = """
你是一名严谨的具身智能论文研究助手。

回答规则：
1. 只能依据提供的论文证据回答。
2. 不得使用证据之外的事实补充答案。
3. 每个关键结论后必须标注[资料1]这样的证据编号。
4. 回答使用中文，模型名称和专业术语可以保留英文。
5. 不得编造论文、来源、页码、实验数据或引用。
""".strip()

ANSWER_HUMAN_PROMPT = """
请依据以下论文证据回答用户问题。

论文证据：
{context}

用户问题：
{question}
""".strip()

JUDGE_SYSTEM_PROMPT = """
你是论文证据充分性审查器。只判断给定原文证据是否直接包含回答问题所需的信息。

规则：
1. 主题或模型名称相关，不等于能够回答。
2. 问题要求精确数值、硬件、部署成本、版本或特定场景时，证据必须明确出现该信息。
3. 不允许依据常识、猜测或证据外知识补全。
4. 只要关键问题无法从证据直接推出，就判定为不可回答。
""".strip()

JUDGE_HUMAN_PROMPT = """
用户问题：
{question}

候选论文证据：
{context}
""".strip()


class EvidenceJudgement(BaseModel):
    """模型对候选证据能否直接回答问题的判定。"""

    answerable: bool = Field(
        description="证据是否直接包含回答问题所需信息"
    )
    reason: str = Field(
        description="一句话说明判定依据，不补充证据外事实"
    )


def prepare_question_node(
    state: ResearchWorkflowState,
) -> dict[str, Any]:
    """校验并标准化工作流输入。"""
    normalized_question = state.get("question", "").strip()
    top_k = state.get("top_k", DEFAULT_TOP_K)
    min_score = state.get("min_score", DEFAULT_MIN_SCORE)

    if not normalized_question:
        raise ValueError("问题不能为空")

    if not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(
            f"top_k必须在1到{MAX_TOP_K}之间"
        )

    if not 0 <= min_score <= 1:
        raise ValueError("min_score必须在0到1之间")

    return {
        "normalized_question": normalized_question,
        "top_k": top_k,
        "min_score": float(min_score),
        "error": None,
        "executed_nodes": ["prepare_question"],
    }


def chunk_to_evidence(
    chunk: RetrievedChunk,
) -> ResearchEvidence:
    """把Retriever结果转换成可持久化的普通字典。"""
    return {
        "content": chunk.content,
        "score": chunk.score,
        "chunk_id": chunk.chunk_id,
        "source_file": chunk.source_file,
        "page_number": chunk.page_number,
    }


def retrieve_evidence_node(
    state: ResearchWorkflowState,
) -> dict[str, Any]:
    """从Milvus检索论文证据，并把异常转换成安全状态。"""
    try:
        chunks = retrieve_relevant_chunks(
            query=state["normalized_question"],
            top_k=state["top_k"],
        )
    except Exception as exception:
        logger.exception("论文研究工作流检索失败")

        return {
            "evidence": [],
            "error": type(exception).__name__,
            "executed_nodes": ["retrieve_evidence"],
        }

    evidence = [
        chunk_to_evidence(chunk)
        for chunk in chunks
    ]

    return {
        "evidence": evidence,
        "error": None,
        "executed_nodes": ["retrieve_evidence"],
    }


def evaluate_evidence_node(
    state: ResearchWorkflowState,
) -> dict[str, Any]:
    """按可解释阈值过滤证据，并选择后续分支。"""
    if state.get("error"):
        return {
            "evidence_sufficient": False,
            "route": "error",
            "executed_nodes": ["evaluate_evidence"],
        }

    min_score = state["min_score"]
    relevant_evidence = [
        item
        for item in state.get("evidence", [])
        if item["score"] >= min_score
    ]

    evidence_sufficient = bool(relevant_evidence)
    route: Literal["answer", "insufficient"] = (
        "answer"
        if evidence_sufficient
        else "insufficient"
    )

    return {
        "evidence": relevant_evidence,
        "evidence_sufficient": evidence_sufficient,
        "route": route,
        "executed_nodes": ["evaluate_evidence"],
    }


def route_after_evaluation(
    state: ResearchWorkflowState,
) -> Literal["answer", "insufficient", "error"]:
    """根据证据评估结果选择下一节点。"""
    return state["route"]


def judge_answerability_node(
    state: ResearchWorkflowState,
) -> dict[str, Any]:
    """用结构化模型判定相关证据是否真的能回答问题。"""
    context = format_evidence_context(state["evidence"])
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", JUDGE_SYSTEM_PROMPT),
            ("human", JUDGE_HUMAN_PROMPT),
        ]
    )
    judge = get_chat_model().with_structured_output(
        EvidenceJudgement,
        method="function_calling",
    )
    try:
        judgement = (prompt | judge).invoke(
            {
                "question": state["normalized_question"],
                "context": context,
            }
        )
    except Exception as exception:
        logger.exception("论文证据充分性判定失败")
        return {
            "evidence_sufficient": False,
            "route": "error",
            "error": type(exception).__name__,
            "judge_reason": "证据充分性判定服务异常",
            "executed_nodes": ["judge_answerability"],
        }

    answerable = bool(judgement.answerable)
    return {
        "evidence_sufficient": answerable,
        "route": "answer" if answerable else "insufficient",
        "judge_reason": judgement.reason,
        "executed_nodes": ["judge_answerability"],
    }


def format_evidence_context(
    evidence: list[ResearchEvidence],
) -> str:
    """把证据转换成带稳定编号的模型上下文。"""
    blocks: list[str] = []

    for index, item in enumerate(evidence, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[资料{index}]",
                    f"来源文件：{item['source_file']}",
                    f"PDF物理页码：{item['page_number']}",
                    f"检索相似度：{item['score']:.6f}",
                    "原文内容：",
                    item["content"],
                ]
            )
        )

    return "\n\n".join(blocks)


def build_citations(
    evidence: list[ResearchEvidence],
) -> list[str]:
    """按文件和页码生成去重后的引用清单。"""
    citations: list[str] = []
    seen: set[tuple[str, int]] = set()

    for item in evidence:
        identity = (
            item["source_file"],
            item["page_number"],
        )

        if identity in seen:
            continue

        seen.add(identity)
        citations.append(
            f"{item['source_file']}，"
            f"PDF物理页码{item['page_number']}"
        )

    return citations


def generate_answer_node(
    state: ResearchWorkflowState,
) -> dict[str, Any]:
    """仅依据通过阈值的论文证据生成答案。"""
    evidence = state["evidence"]
    context = format_evidence_context(evidence)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ANSWER_SYSTEM_PROMPT),
            ("human", ANSWER_HUMAN_PROMPT),
        ]
    )
    chain = prompt | get_chat_model() | StrOutputParser()

    answer = chain.invoke(
        {
            "question": state["normalized_question"],
            "context": context,
        }
    )

    return {
        "answer": answer,
        "citations": build_citations(evidence),
        "executed_nodes": ["generate_answer"],
    }


def insufficient_answer_node(
    state: ResearchWorkflowState,
) -> dict[str, Any]:
    """证据不足时返回确定性的拒答。"""
    return {
        "answer": "根据当前论文资料无法确定。",
        "citations": [],
        "executed_nodes": ["insufficient_answer"],
    }


def error_answer_node(
    state: ResearchWorkflowState,
) -> dict[str, Any]:
    """依赖服务异常时返回安全的降级回答。"""
    return {
        "answer": "论文检索服务暂时不可用，请稍后重试。",
        "citations": [],
        "executed_nodes": ["error_answer"],
    }


def build_research_workflow(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """构建可测试、可选持久化的论文研究工作流。"""
    builder = StateGraph(ResearchWorkflowState)

    builder.add_node(
        "prepare_question",
        prepare_question_node,
    )
    builder.add_node(
        "retrieve_evidence",
        retrieve_evidence_node,
    )
    builder.add_node(
        "evaluate_evidence",
        evaluate_evidence_node,
    )
    builder.add_node(
        "judge_answerability",
        judge_answerability_node,
    )
    builder.add_node(
        "generate_answer",
        generate_answer_node,
    )
    builder.add_node(
        "insufficient_answer",
        insufficient_answer_node,
    )
    builder.add_node(
        "error_answer",
        error_answer_node,
    )

    builder.add_edge(START, "prepare_question")
    builder.add_edge(
        "prepare_question",
        "retrieve_evidence",
    )
    builder.add_edge(
        "retrieve_evidence",
        "evaluate_evidence",
    )
    builder.add_conditional_edges(
        "evaluate_evidence",
        route_after_evaluation,
        {
            "answer": "judge_answerability",
            "insufficient": "insufficient_answer",
            "error": "error_answer",
        },
    )
    builder.add_conditional_edges(
        "judge_answerability",
        route_after_evaluation,
        {
            "answer": "generate_answer",
            "insufficient": "insufficient_answer",
            "error": "error_answer",
        },
    )
    builder.add_edge("generate_answer", END)
    builder.add_edge("insufficient_answer", END)
    builder.add_edge("error_answer", END)

    return builder.compile(
        checkpointer=checkpointer,
    )


@lru_cache(maxsize=1)
def get_research_workflow() -> CompiledStateGraph:
    """创建并缓存使用PostgreSQL持久化的研究工作流。"""
    return build_research_workflow(
        checkpointer=get_postgres_checkpointer(),
    )


def run_research_workflow(
    question: str,
    thread_id: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
) -> ResearchWorkflowState:
    """运行一次持久化论文研究工作流。"""
    normalized_thread_id = thread_id.strip()

    if not normalized_thread_id:
        raise ValueError("thread_id不能为空")

    result = get_research_workflow().invoke(
        {
            "question": question,
            "top_k": top_k,
            "min_score": min_score,
            "evidence": [],
            "answer": "",
            "citations": [],
            "executed_nodes": [],
        },
        config={
            "configurable": {
                "thread_id": normalized_thread_id,
            }
        },
    )

    return result


def stream_research_workflow(
    question: str,
    thread_id: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
) -> Iterator[dict[str, Any]]:
    """逐节点运行研究流程并产出适合SSE的事件。"""
    normalized_thread_id = thread_id.strip()
    if not normalized_thread_id:
        raise ValueError("thread_id不能为空")

    aggregate: dict[str, Any] = {
        "route": None,
        "evidence": [],
        "answer": "",
        "citations": [],
        "executed_nodes": [],
        "judge_reason": None,
    }
    initial_state: ResearchWorkflowState = {
        "question": question,
        "top_k": top_k,
        "min_score": min_score,
        "evidence": [],
        "answer": "",
        "citations": [],
        "executed_nodes": [],
    }

    for update in get_research_workflow().stream(
        initial_state,
        config={
            "configurable": {
                "thread_id": normalized_thread_id,
            }
        },
        stream_mode="updates",
    ):
        for node_name, node_output in update.items():
            if not isinstance(node_output, dict):
                continue

            for key, value in node_output.items():
                if key == "executed_nodes":
                    aggregate["executed_nodes"].extend(value)
                else:
                    aggregate[key] = value

            yield {
                "event": "node",
                "node": node_name,
                "route": aggregate.get("route"),
                "evidence_count": len(
                    aggregate.get("evidence", [])
                ),
            }

    yield {
        "event": "completed",
        "answer": aggregate["answer"],
        "route": aggregate["route"],
        "evidence_count": len(aggregate["evidence"]),
        "citations": aggregate["citations"],
        "executed_nodes": aggregate["executed_nodes"],
        "judge_reason": aggregate.get("judge_reason"),
    }
