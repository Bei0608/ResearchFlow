from dataclasses import dataclass

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.chat import get_chat_model
from app.rag.retriever import (
    RetrievedChunk,
    retrieve_relevant_chunks,
)

SYSTEM_PROMPT = """
你是一名严谨的具身智能论文研究助手。

回答规则：
1. 只能依据用户提供的论文资料回答。
2. 不得使用资料之外的事实补充答案。
3. 每个关键结论后必须使用[资料1]这样的格式标注依据。
4. 如果资料不足以回答，应明确说明“根据当前检索资料无法确定”。
5. 回答使用中文，但论文中的模型名称和专业术语可以保留英文。
6. 不要编造论文、页码、实验数据或引用。
""".strip()


QUESTION_PROMPT = """
请根据以下论文资料回答问题。

论文资料：
{context}

用户问题：
{question}
""".strip()


@dataclass(frozen=True)
class RAGAnswer:
    """一次RAG问答的完整结果。"""

    question: str
    answer: str
    retrieved_chunks: list[RetrievedChunk]


def format_retrieved_context(
    retrieved_chunks: list[RetrievedChunk],
) -> str:
    """将检索结果转换成带编号的模型上下文。"""
    context_blocks: list[str] = []

    for index, chunk in enumerate(
        retrieved_chunks,
        start=1,
    ):
        context_blocks.append(
            "\n".join(
                [
                    f"[资料{index}]",
                    f"来源文件：{chunk.source_file}",
                    f"PDF物理页码：{chunk.page_number}",
                    f"检索相似度：{chunk.score:.6f}",
                    "原文内容：",
                    chunk.content,
                ]
            )
        )

    return "\n\n".join(context_blocks)


def answer_question(
    question: str,
    top_k: int = 5,
) -> RAGAnswer:
    """检索论文资料并生成带引用的中文答案。"""
    normalized_question = question.strip()

    if not normalized_question:
        raise ValueError("问题不能为空")

    retrieved_chunks = retrieve_relevant_chunks(
        query=normalized_question,
        top_k=top_k,
    )

    if not retrieved_chunks:
        return RAGAnswer(
            question=normalized_question,
            answer="根据当前检索资料无法确定。",
            retrieved_chunks=[],
        )

    context = format_retrieved_context(
        retrieved_chunks=retrieved_chunks,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", QUESTION_PROMPT),
        ]
    )

    chain = prompt | get_chat_model() | StrOutputParser()

    answer = chain.invoke(
        {
            "question": normalized_question,
            "context": context,
        }
    )

    return RAGAnswer(
        question=normalized_question,
        answer=answer,
        retrieved_chunks=retrieved_chunks,
    )
