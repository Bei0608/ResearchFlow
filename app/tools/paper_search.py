from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.rag.retriever import retrieve_relevant_chunks


class PaperSearchInput(BaseModel):
    """论文检索工具的输入参数。"""

    query: str = Field(
        min_length=1,
        description="需要从论文知识库中检索的问题",
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="需要返回的相关论文片段数量",
    )


@tool(
    "search_research_papers",
    args_schema=PaperSearchInput,
)
def search_research_papers(
    query: str,
    top_k: int = 5,
) -> str:
    """
    从本地具身智能论文知识库中检索相关原文。

    当用户询问RT-1、RT-2、PaLM-E、机器人控制、
    视觉语言动作模型或知识库论文内容时使用此工具。
    工具返回论文原文、来源文件、页码和相似度，
    不负责生成最终答案。
    """
    retrieved_chunks = retrieve_relevant_chunks(
        query=query,
        top_k=top_k,
    )

    if not retrieved_chunks:
        return "没有检索到相关论文资料。"

    result_blocks: list[str] = []

    for index, chunk in enumerate(
        retrieved_chunks,
        start=1,
    ):
        result_blocks.append(
            "\n".join(
                [
                    f"[资料{index}]",
                    f"来源：{chunk.source_file}",
                    f"PDF物理页码：{chunk.page_number}",
                    f"相似度：{chunk.score:.6f}",
                    "原文：",
                    chunk.content,
                ]
            )
        )

    return "\n\n".join(result_blocks)
