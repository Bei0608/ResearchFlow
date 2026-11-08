import asyncio
from pathlib import Path

import pytest
from mcp import Client

import app.mcp_server.server as server_module
from app.rag.retriever import RetrievedChunk


def test_mcp_lists_well_annotated_tools() -> None:
    async def scenario() -> None:
        async with Client(
            server_module.build_mcp_server(auth_enabled=False)
        ) as client:
            tools_result = await client.list_tools()

        by_name = {
            tool.name: tool for tool in tools_result.tools
        }
        assert set(by_name) == {
            "researchflow_list_papers",
            "researchflow_search_papers",
            "researchflow_answer_question",
        }
        assert (
            by_name[
                "researchflow_search_papers"
            ].annotations.read_only_hint
            is True
        )
        assert (
            by_name[
                "researchflow_answer_question"
            ].annotations.read_only_hint
            is False
        )

    asyncio.run(scenario())


def test_mcp_list_papers_returns_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_module,
        "discover_pdf_files",
        lambda _: [Path("RT-1.pdf"), Path("RT-2.pdf")],
    )

    async def scenario() -> None:
        async with Client(
            server_module.build_mcp_server(auth_enabled=False)
        ) as client:
            result = await client.call_tool(
                "researchflow_list_papers",
                {"limit": 1, "offset": 1},
            )
        data = result.structured_content
        assert data is not None
        assert data["total"] == 2
        assert data["papers"] == ["RT-2.pdf"]
        assert data["has_more"] is False

    asyncio.run(scenario())


def test_mcp_search_returns_traceable_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_module,
        "retrieve_relevant_chunks",
        lambda query, top_k: [
            RetrievedChunk(
                content="RT-2将动作表示为token。",
                score=0.82,
                chunk_id="chunk-1",
                source_file="RT-2.pdf",
                page_number=4,
                metadata={},
            )
        ],
    )

    async def scenario() -> None:
        async with Client(
            server_module.build_mcp_server(auth_enabled=False)
        ) as client:
            result = await client.call_tool(
                "researchflow_search_papers",
                {"query": "RT-2如何表示动作？", "top_k": 3},
            )
        data = result.structured_content
        assert data is not None
        assert data["count"] == 1
        assert data["evidence"][0]["chunk_id"] == "chunk-1"
        assert data["evidence"][0]["page_number"] == 4

    asyncio.run(scenario())


def test_mcp_answer_runs_auditable_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_module,
        "run_research_workflow",
        lambda **kwargs: {
            "answer": "动作被表示为token。[资料1]",
            "route": "answer",
            "evidence": [{"content": "evidence"}],
            "citations": ["RT-2.pdf，PDF物理页码4"],
            "executed_nodes": [
                "prepare_question",
                "retrieve_evidence",
                "evaluate_evidence",
                "generate_answer",
            ],
        },
    )

    async def scenario() -> None:
        async with Client(
            server_module.build_mcp_server(auth_enabled=False)
        ) as client:
            result = await client.call_tool(
                "researchflow_answer_question",
                {
                    "question": "RT-2如何表示动作？",
                    "thread_id": "mcp-test-thread",
                },
            )
        data = result.structured_content
        assert data is not None
        assert data["route"] == "answer"
        assert data["thread_id"] == "mcp-local-test-thread"
        assert data["executed_nodes"][-1] == "generate_answer"

    asyncio.run(scenario())
