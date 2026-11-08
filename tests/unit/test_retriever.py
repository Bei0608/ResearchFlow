import pytest
from langchain_core.documents import Document

import app.rag.retriever as retriever_module
from app.rag.retriever import retrieve_relevant_chunks


@pytest.fixture(autouse=True)
def disable_retrieval_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever_module,
        "get_retrieval_cache",
        lambda: None,
    )


class FakeVectorStore:
    """避免单元测试访问真实Embedding服务和Milvus。"""

    def similarity_search_with_score(
        self,
        query: str,
        k: int,
    ) -> list[tuple[Document, float]]:
        assert query == "测试问题"
        assert k == 2

        return [
            (
                Document(
                    page_content="第一个测试文本块",
                    metadata={
                        "chunk_id": "chunk-001",
                        "source_file": "paper-a.pdf",
                        "page_number": 3,
                    },
                ),
                0.91,
            ),
            (
                Document(
                    page_content="第二个测试文本块",
                    metadata={
                        "chunk_id": "chunk-002",
                        "source_file": "paper-b.pdf",
                        "page_number": 7,
                    },
                ),
                0.82,
            ),
        ]


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "\n",
    ],
)
def test_retrieve_rejects_empty_query(query: str) -> None:
    with pytest.raises(
        ValueError,
        match="检索问题不能为空",
    ):
        retrieve_relevant_chunks(query=query)


@pytest.mark.parametrize(
    "top_k",
    [
        0,
        -1,
    ],
)
def test_retrieve_rejects_invalid_top_k(
    top_k: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="top_k必须大于0",
    ):
        retrieve_relevant_chunks(
            query="测试问题",
            top_k=top_k,
        )


def test_retrieve_maps_vector_store_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever_module,
        "get_milvus_vector_store",
        lambda: FakeVectorStore(),
    )

    results = retrieve_relevant_chunks(
        query="测试问题",
        top_k=2,
        strategy="similarity",
    )

    assert len(results) == 2

    assert results[0].content == "第一个测试文本块"
    assert results[0].score == pytest.approx(0.91)
    assert results[0].chunk_id == "chunk-001"
    assert results[0].source_file == "paper-a.pdf"
    assert results[0].page_number == 3


def test_mmr_reuses_one_query_embedding_and_preserves_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        Document(
            page_content=f"文本{index}",
            metadata={
                "chunk_id": f"chunk-{index}",
                "source_file": f"paper-{index}.pdf",
                "page_number": index,
            },
        )
        for index in range(1, 5)
    ]

    class FakeEmbeddings:
        calls = 0

        def embed_query(self, query: str) -> list[float]:
            self.calls += 1
            assert query == "测试问题"
            return [0.1, 0.2]

    class FakeMMRStore:
        def similarity_search_with_score_by_vector(
            self,
            embedding: list[float],
            k: int,
        ):
            assert embedding == [0.1, 0.2]
            assert k == 8
            return list(
                zip(documents, [0.95, 0.9, 0.85, 0.8])
            )

        def max_marginal_relevance_search_by_vector(
            self,
            embedding: list[float],
            k: int,
            fetch_k: int,
            lambda_mult: float,
        ):
            assert k == 2
            assert fetch_k == 8
            assert lambda_mult == pytest.approx(0.65)
            return [documents[0], documents[2]]

    embeddings = FakeEmbeddings()
    monkeypatch.setattr(
        retriever_module,
        "get_embedding_model",
        lambda: embeddings,
    )
    monkeypatch.setattr(
        retriever_module,
        "get_milvus_vector_store",
        lambda: FakeMMRStore(),
    )
    monkeypatch.setattr(
        retriever_module,
        "get_retrieval_settings",
        lambda: retriever_module.RetrievalSettings(
            strategy="mmr",
            fetch_k_multiplier=4,
            mmr_lambda=0.65,
        ),
    )

    results = retrieve_relevant_chunks(
        query="测试问题",
        top_k=2,
    )

    assert embeddings.calls == 1
    assert [item.chunk_id for item in results] == [
        "chunk-1",
        "chunk-3",
    ]
    assert [item.score for item in results] == [0.95, 0.85]


def test_retrieval_cache_hit_skips_milvus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCache:
        def get(self, **kwargs):
            return [
                {
                    "content": "cached evidence",
                    "score": 0.91,
                    "chunk_id": "cached-1",
                    "source_file": "cached.pdf",
                    "page_number": 7,
                    "metadata": {
                        "chunk_id": "cached-1",
                        "source_file": "cached.pdf",
                        "page_number": 7,
                    },
                }
            ]

    monkeypatch.setattr(
        retriever_module,
        "get_retrieval_cache",
        lambda: FakeCache(),
    )
    monkeypatch.setattr(
        retriever_module,
        "get_milvus_vector_store",
        lambda: pytest.fail("cache hit should skip Milvus"),
    )

    results = retrieve_relevant_chunks("cached query", top_k=1)
    assert results[0].chunk_id == "cached-1"
    assert results[0].score == pytest.approx(0.91)
