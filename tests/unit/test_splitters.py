import pytest
from langchain_core.documents import Document

from app.models.document import PageMetadata
from app.rag.splitters import (
    clean_page_text,
    create_text_splitter,
    split_pages,
)

DOCUMENT_ID = "a" * 64


def create_test_page(text: str) -> Document:
    """创建不依赖真实PDF的测试页面。"""
    metadata = PageMetadata(
        document_id=DOCUMENT_ID,
        page_id=f"{DOCUMENT_ID}:page:1",
        source_file="test.pdf",
        source_path="data/papers/test.pdf",
        file_size_bytes=1000,
        page_number=1,
        total_pages=1,
    )

    return Document(
        page_content=text,
        metadata=metadata.model_dump(exclude_none=True),
    )


def test_clean_page_text_normalizes_whitespace() -> None:
    dirty_text = "第一行  \t文本\r\n" "\r\n" "\r\n" "第二行\u00a0文本\x00"

    cleaned_text = clean_page_text(dirty_text)

    assert cleaned_text == "第一行 文本\n\n第二行 文本"


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [
        (0, 0),
        (-1, 0),
        (100, -1),
        (100, 100),
        (100, 101),
    ],
)
def test_create_text_splitter_rejects_invalid_parameters(
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    with pytest.raises(ValueError):
        create_text_splitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


def test_split_pages_preserves_page_metadata() -> None:
    page = create_test_page(
        "机器人学习需要大量数据。" "视觉语言模型可以帮助机器人理解场景。" "具身智能系统需要结合感知、推理和控制。" * 20
    )

    chunks = split_pages(
        page_documents=[page],
        chunk_size=120,
        chunk_overlap=20,
    )

    assert len(chunks) > 1

    for chunk in chunks:
        assert chunk.metadata["document_id"] == DOCUMENT_ID
        assert chunk.metadata["page_number"] == 1
        assert chunk.metadata["source_file"] == "test.pdf"
        assert chunk.metadata["configured_chunk_size"] == 120
        assert chunk.metadata["configured_chunk_overlap"] == 20

        assert 0 < len(chunk.page_content) <= 120
        assert chunk.metadata["chunk_char_count"] == len(chunk.page_content)


def test_chunk_ids_are_unique() -> None:
    page = create_test_page("这是用于测试唯一标识的文本。" * 100)

    chunks = split_pages(
        page_documents=[page],
        chunk_size=100,
        chunk_overlap=10,
    )

    chunk_ids = [chunk.metadata["chunk_id"] for chunk in chunks]

    assert len(chunk_ids) == len(set(chunk_ids))


def test_chunk_ids_are_stable() -> None:
    page = create_test_page("相同输入应该产生相同的Chunk ID。" * 100)

    first_result = split_pages(
        page_documents=[page],
        chunk_size=100,
        chunk_overlap=10,
    )
    second_result = split_pages(
        page_documents=[page],
        chunk_size=100,
        chunk_overlap=10,
    )

    first_ids = [chunk.metadata["chunk_id"] for chunk in first_result]
    second_ids = [chunk.metadata["chunk_id"] for chunk in second_result]

    assert first_ids == second_ids


def test_empty_page_is_skipped() -> None:
    empty_page = create_test_page(" \n\t ")

    chunks = split_pages(
        page_documents=[empty_page],
    )

    assert chunks == []
