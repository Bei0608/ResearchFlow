from pathlib import Path

import pytest

from app.rag.loaders import (
    discover_pdf_files,
    load_pdf_directory,
)
from app.rag.splitters import (
    DEFAULT_CHUNK_SIZE,
    split_pages,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAPERS_DIR = PROJECT_ROOT / "data" / "papers"


@pytest.mark.integration
def test_real_pdf_pipeline() -> None:
    pdf_files = discover_pdf_files(PAPERS_DIR)

    pages = load_pdf_directory(
        papers_dir=PAPERS_DIR,
        project_root=PROJECT_ROOT,
    )
    chunks = split_pages(pages)

    assert len(pdf_files) >= 3
    assert len(pages) > 0
    assert len(chunks) > len(pages)

    required_metadata = {
        "document_id",
        "page_id",
        "source_file",
        "source_path",
        "page_number",
        "total_pages",
        "chunk_id",
        "chunk_index",
        "chunk_char_count",
    }

    chunk_ids = []

    for chunk in chunks:
        assert chunk.page_content.strip()
        assert len(chunk.page_content) <= DEFAULT_CHUNK_SIZE
        assert required_metadata.issubset(chunk.metadata)

        assert (
            chunk.metadata["chunk_char_count"]
            == len(chunk.page_content)
        )

        chunk_ids.append(chunk.metadata["chunk_id"])

    assert len(chunk_ids) == len(set(chunk_ids))


@pytest.mark.integration
def test_real_pipeline_produces_stable_chunk_ids() -> None:
    pages = load_pdf_directory(
        papers_dir=PAPERS_DIR,
        project_root=PROJECT_ROOT,
    )

    first_chunks = split_pages(pages)
    second_chunks = split_pages(pages)

    first_ids = [
        chunk.metadata["chunk_id"]
        for chunk in first_chunks
    ]
    second_ids = [
        chunk.metadata["chunk_id"]
        for chunk in second_chunks
    ]

    assert first_ids == second_ids