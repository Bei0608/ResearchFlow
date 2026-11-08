import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal
from typing import Any

from dotenv import load_dotenv

from app.cache import get_retrieval_cache
from app.rag.embeddings import get_embedding_model
from app.storage.milvus import (
    get_milvus_collection_name,
    get_milvus_vector_store,
)

DEFAULT_TOP_K = 5
DEFAULT_RETRIEVAL_STRATEGY = "mmr"
DEFAULT_FETCH_K_MULTIPLIER = 4
DEFAULT_MMR_LAMBDA = 0.65
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class RetrievalSettings:
    """检索候选集和多样性重排配置。"""

    strategy: Literal["similarity", "mmr"]
    fetch_k_multiplier: int
    mmr_lambda: float


@lru_cache(maxsize=1)
def get_retrieval_settings() -> RetrievalSettings:
    """读取可缓存的检索策略配置。"""
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    strategy = os.getenv(
        "RETRIEVAL_STRATEGY",
        DEFAULT_RETRIEVAL_STRATEGY,
    ).lower()
    if strategy not in {"similarity", "mmr"}:
        raise RuntimeError(
            "RETRIEVAL_STRATEGY必须是similarity或mmr"
        )

    fetch_multiplier = int(
        os.getenv(
            "RETRIEVAL_FETCH_K_MULTIPLIER",
            str(DEFAULT_FETCH_K_MULTIPLIER),
        )
    )
    mmr_lambda = float(
        os.getenv(
            "RETRIEVAL_MMR_LAMBDA",
            str(DEFAULT_MMR_LAMBDA),
        )
    )
    if fetch_multiplier < 1:
        raise RuntimeError(
            "RETRIEVAL_FETCH_K_MULTIPLIER必须大于等于1"
        )
    if not 0 <= mmr_lambda <= 1:
        raise RuntimeError(
            "RETRIEVAL_MMR_LAMBDA必须在0到1之间"
        )
    return RetrievalSettings(
        strategy=strategy,
        fetch_k_multiplier=fetch_multiplier,
        mmr_lambda=mmr_lambda,
    )


@dataclass(frozen=True)
class RetrievedChunk:
    """一次向量检索返回的论文文本块。"""

    content: str
    score: float
    chunk_id: str
    source_file: str
    page_number: int
    metadata: dict[str, Any]


def retrieve_relevant_chunks(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    strategy: Literal["similarity", "mmr"] | None = None,
) -> list[RetrievedChunk]:
    """根据自然语言问题检索相关论文片段。"""
    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("检索问题不能为空")

    if top_k <= 0:
        raise ValueError("top_k必须大于0")

    settings = get_retrieval_settings()
    resolved_strategy = strategy or settings.strategy
    if resolved_strategy not in {"similarity", "mmr"}:
        raise ValueError("strategy必须是similarity或mmr")

    cache_identity = {
        "query": normalized_query,
        "top_k": top_k,
        "strategy": resolved_strategy,
        "collection": get_milvus_collection_name(),
    }
    cache = get_retrieval_cache()
    if cache is not None:
        cached_rows = cache.get(**cache_identity)
        if cached_rows is not None:
            return [
                RetrievedChunk(
                    content=str(row["content"]),
                    score=float(row["score"]),
                    chunk_id=str(row["chunk_id"]),
                    source_file=str(row["source_file"]),
                    page_number=int(row["page_number"]),
                    metadata=dict(row["metadata"]),
                )
                for row in cached_rows
            ]

    vector_store = get_milvus_vector_store()
    if resolved_strategy == "similarity":
        search_results = vector_store.similarity_search_with_score(
            query=normalized_query,
            k=top_k,
        )
    else:
        fetch_k = max(
            top_k,
            top_k * settings.fetch_k_multiplier,
        )
        embedding = get_embedding_model().embed_query(
            normalized_query
        )
        candidates = (
            vector_store.similarity_search_with_score_by_vector(
                embedding=embedding,
                k=fetch_k,
            )
        )
        score_by_chunk_id = {
            str(document.metadata.get("chunk_id")): float(score)
            for document, score in candidates
        }
        selected_documents = (
            vector_store.max_marginal_relevance_search_by_vector(
                embedding=embedding,
                k=top_k,
                fetch_k=fetch_k,
                lambda_mult=settings.mmr_lambda,
            )
        )
        search_results = [
            (
                document,
                score_by_chunk_id.get(
                    str(document.metadata.get("chunk_id")),
                    0.0,
                ),
            )
            for document in selected_documents
        ]

    retrieved_chunks: list[RetrievedChunk] = []

    for document, score in search_results:
        metadata = dict(document.metadata)

        retrieved_chunks.append(
            RetrievedChunk(
                content=document.page_content,
                score=float(score),
                chunk_id=str(metadata["chunk_id"]),
                source_file=str(metadata["source_file"]),
                page_number=int(metadata["page_number"]),
                metadata=metadata,
            )
        )

    if cache is not None:
        cache.set(
            [
                {
                    "content": chunk.content,
                    "score": chunk.score,
                    "chunk_id": chunk.chunk_id,
                    "source_file": chunk.source_file,
                    "page_number": chunk.page_number,
                    "metadata": chunk.metadata,
                }
                for chunk in retrieved_chunks
            ],
            **cache_identity,
        )

    return retrieved_chunks
