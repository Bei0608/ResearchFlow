from pathlib import Path
import hashlib
from typing import Annotated
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.types import ToolAnnotations
from pydantic import Field

from app.mcp_server.models import (
    EvidenceItem,
    PaperListResult,
    PaperSearchResult,
    ResearchAnswerResult,
)
from app.mcp_server.auth import (
    JWTMCPTokenVerifier,
    get_mcp_auth_settings,
)
from app.rag.loaders import discover_pdf_files
from app.rag.retriever import retrieve_relevant_chunks
from app.workflows import run_research_workflow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAPERS_DIR = PROJECT_ROOT / "data" / "papers"


def build_mcp_server(
    auth_enabled: bool | None = None,
) -> MCPServer:
    """创建论文研究MCP Server及其领域工具。"""
    mcp_auth = get_mcp_auth_settings()
    use_auth = mcp_auth.enabled if auth_enabled is None else auth_enabled
    security_options = {}
    if use_auth:
        security_options = {
            "auth": AuthSettings(
                issuer_url=mcp_auth.issuer_url,
                resource_server_url=mcp_auth.resource_server_url,
                validate_token_resource=True,
                required_scopes=mcp_auth.required_scopes,
            ),
            "token_verifier": JWTMCPTokenVerifier(mcp_auth),
        }
    server = MCPServer(
        name="researchflow_mcp",
        title="ResearchFlow Paper Research",
        description=(
            "检索本地具身智能论文知识库，并运行可审计的"
            "LangGraph论文研究工作流。"
        ),
        version="1.0.0",
        instructions=(
            "先用researchflow_list_papers了解资料范围；"
            "需要原文证据时调用researchflow_search_papers；"
            "需要带引用的最终回答时调用researchflow_answer_question。"
        ),
        **security_options,
    )

    @server.tool(
        name="researchflow_list_papers",
        title="List ResearchFlow Papers",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    def list_papers(
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=100,
                description="本页最多返回的论文数量，1到100",
            ),
        ] = 20,
        offset: Annotated[
            int,
            Field(
                ge=0,
                description="从第几条论文记录开始返回",
            ),
        ] = 0,
    ) -> PaperListResult:
        """分页列出本地论文知识库中的PDF文件。

        适合在研究开始前确认知识库覆盖范围；不读取论文正文，
        也不回答论文事实问题。返回总数、分页信息和文件名。
        """
        paper_names = [
            path.name
            for path in discover_pdf_files(PAPERS_DIR)
        ]
        page = paper_names[offset : offset + limit]
        next_offset = offset + len(page)
        has_more = next_offset < len(paper_names)
        markdown_lines = [
            f"# ResearchFlow论文目录（{len(paper_names)}篇）",
            "",
        ]
        markdown_lines.extend(
            f"{offset + index}. {name}"
            for index, name in enumerate(page, start=1)
        )
        if not page:
            markdown_lines.append("当前分页没有论文。")

        return PaperListResult(
            total=len(paper_names),
            count=len(page),
            offset=offset,
            papers=page,
            has_more=has_more,
            next_offset=next_offset if has_more else None,
            markdown="\n".join(markdown_lines),
        )

    @server.tool(
        name="researchflow_search_papers",
        title="Search ResearchFlow Papers",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    def search_papers(
        query: Annotated[
            str,
            Field(
                min_length=1,
                max_length=8000,
                description="要在论文原文中检索的问题",
            ),
        ],
        top_k: Annotated[
            int,
            Field(
                ge=1,
                le=10,
                description="最多返回的相关原文块数量",
            ),
        ] = 5,
    ) -> PaperSearchResult:
        """从Milvus知识库检索相关论文原文证据。

        返回每条证据的稳定chunk_id、来源文件、PDF物理页码、
        余弦相似度和原文。此工具不生成结论；调用方应依据证据回答。
        """
        chunks = retrieve_relevant_chunks(query, top_k)
        evidence = [
            EvidenceItem(
                rank=index,
                chunk_id=chunk.chunk_id,
                source_file=chunk.source_file,
                page_number=chunk.page_number,
                score=chunk.score,
                content=chunk.content,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]
        blocks = []
        for item in evidence:
            blocks.append(
                "\n".join(
                    [
                        f"## [资料{item.rank}]",
                        f"- 来源：{item.source_file}",
                        f"- PDF物理页码：{item.page_number}",
                        f"- 相似度：{item.score:.6f}",
                        "",
                        item.content,
                    ]
                )
            )

        return PaperSearchResult(
            query=query.strip(),
            count=len(evidence),
            evidence=evidence,
            markdown="\n\n".join(blocks)
            if blocks
            else "没有检索到相关论文证据。",
        )

    @server.tool(
        name="researchflow_answer_question",
        title="Answer With ResearchFlow Workflow",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def answer_question(
        question: Annotated[
            str,
            Field(
                min_length=1,
                max_length=8000,
                description="需要基于论文证据回答的问题",
            ),
        ],
        top_k: Annotated[
            int,
            Field(ge=1, le=10, description="检索证据数量"),
        ] = 5,
        min_score: Annotated[
            float,
            Field(
                ge=0,
                le=1,
                description="证据通过的最低余弦相似度",
            ),
        ] = 0.45,
        thread_id: Annotated[
            str | None,
            Field(
                max_length=128,
                description=(
                    "可选工作流会话ID；省略时自动生成。"
                    "执行会写入LangGraph checkpoint。"
                ),
            ),
        ] = None,
    ) -> ResearchAnswerResult:
        """运行完整LangGraph研究流程并返回带引用的答案。

        工作流依次校验问题、MMR检索、相似度过滤、结构化证据判定，
        再生成带引用回答或确定性拒答。
        该调用会持久化checkpoint，但不会修改论文或向量数据。
        """
        access_token = get_access_token()
        subject_prefix = "local"
        if access_token is not None and access_token.subject:
            subject_prefix = hashlib.sha256(
                access_token.subject.encode("utf-8")
            ).hexdigest()[:16]
        resolved_thread_id = (
            f"mcp-{subject_prefix}-"
            f"{thread_id.removeprefix('mcp-')}"
            if thread_id
            else f"mcp-{subject_prefix}-{uuid4().hex}"
        )
        result = run_research_workflow(
            question=question,
            thread_id=resolved_thread_id,
            top_k=top_k,
            min_score=min_score,
        )
        citations = result["citations"]
        citation_text = (
            "\n".join(f"- {item}" for item in citations)
            if citations
            else "- 无"
        )
        markdown = (
            f"# 研究回答\n\n{result['answer']}\n\n"
            f"## 引用\n{citation_text}"
        )

        return ResearchAnswerResult(
            thread_id=resolved_thread_id,
            question=question.strip(),
            answer=result["answer"],
            route=result["route"],
            evidence_count=len(result["evidence"]),
            citations=citations,
            executed_nodes=result["executed_nodes"],
            markdown=markdown,
        )

    return server


mcp_server = build_mcp_server()
