from dataclasses import dataclass
from itertools import batched
from pathlib import Path

from langchain_core.documents import Document
from langchain_milvus import Milvus

from app.cache import get_retrieval_cache
from app.rag.loaders import load_pdf_directory
from app.rag.splitters import split_pages
from app.storage.milvus import (
    get_milvus_collection_name,
    get_milvus_vector_store,
)

ID_LOOKUP_BATCH_SIZE = 500
INSERT_BATCH_SIZE = 100


@dataclass(frozen=True)
class IndexingResult:
    """一次论文索引任务的执行结果。"""

    page_count: int
    chunk_count: int
    inserted_count: int
    skipped_count: int
    indexed_count: int
    collection_name: str
    collection_existed: bool


def get_chunk_ids(
    chunk_documents: list[Document],
) -> list[str]:
    """提取并检查文本块的稳定主键。"""
    chunk_ids: list[str] = []

    for chunk_document in chunk_documents:
        chunk_id = chunk_document.metadata.get("chunk_id")

        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError("文本块缺少有效的chunk_id")

        chunk_ids.append(chunk_id)

    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("检测到重复的chunk_id")

    return chunk_ids


def find_existing_chunk_ids(
    vector_store: Milvus,
    collection_name: str,
    chunk_ids: list[str],
) -> set[str]:
    """分批查询已经存在于Milvus中的Chunk ID。"""
    if not vector_store.client.has_collection(
        collection_name=collection_name,
    ):
        return set()

    existing_chunk_ids: set[str] = set()

    for chunk_id_batch in batched(
        chunk_ids,
        ID_LOOKUP_BATCH_SIZE,
    ):
        rows = vector_store.client.get(
            collection_name=collection_name,
            ids=list(chunk_id_batch),
            output_fields=["pk"],
        )

        for row in rows:
            primary_key = row.get("pk")

            if isinstance(primary_key, str):
                existing_chunk_ids.add(primary_key)

    return existing_chunk_ids


def index_pdf_directory(
    papers_dir: Path,
    project_root: Path,
) -> IndexingResult:
    """只将尚未存在的PDF文本块写入Milvus。"""
    page_documents = load_pdf_directory(
        papers_dir=papers_dir,
        project_root=project_root,
    )

    chunk_documents = split_pages(
        page_documents=page_documents,
    )

    if not chunk_documents:
        raise ValueError("没有生成可写入向量数据库的文本块")

    chunk_ids = get_chunk_ids(chunk_documents)

    vector_store = get_milvus_vector_store()
    collection_name = get_milvus_collection_name()

    collection_existed = vector_store.client.has_collection(
        collection_name=collection_name,
    )

    existing_chunk_ids = find_existing_chunk_ids(
        vector_store=vector_store,
        collection_name=collection_name,
        chunk_ids=chunk_ids,
    )

    new_documents: list[Document] = []
    new_chunk_ids: list[str] = []

    for chunk_document, chunk_id in zip(
        chunk_documents,
        chunk_ids,
        strict=True,
    ):
        if chunk_id in existing_chunk_ids:
            continue

        new_documents.append(chunk_document)
        new_chunk_ids.append(chunk_id)

    if new_documents:
        vector_store.add_documents(
            documents=new_documents,
            ids=new_chunk_ids,
            batch_size=INSERT_BATCH_SIZE,
        )

        vector_store.client.flush(
            collection_name=collection_name,
        )
        cache = get_retrieval_cache()
        if cache is not None:
            cache.bump_index_version()

    indexed_chunk_ids = find_existing_chunk_ids(
        vector_store=vector_store,
        collection_name=collection_name,
        chunk_ids=chunk_ids,
    )

    return IndexingResult(
        page_count=len(page_documents),
        chunk_count=len(chunk_documents),
        inserted_count=len(new_documents),
        skipped_count=len(existing_chunk_ids),
        indexed_count=len(indexed_chunk_ids),
        collection_name=collection_name,
        collection_existed=collection_existed,
    )
