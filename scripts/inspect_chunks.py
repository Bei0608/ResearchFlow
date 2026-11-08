from collections import defaultdict
from pathlib import Path

from langchain_core.documents import Document

from app.rag.loaders import load_pdf_directory
from app.rag.splitters import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    split_pages,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAPERS_DIR = PROJECT_ROOT / "data" / "papers"


def clean_preview(text: str, max_length: int = 300) -> str:
    return " ".join(text.split())[:max_length]


def group_chunks_by_source(
    chunks: list[Document],
) -> dict[str, list[Document]]:
    grouped_chunks: dict[str, list[Document]] = defaultdict(list)

    for chunk in chunks:
        source_file = chunk.metadata["source_file"]
        grouped_chunks[source_file].append(chunk)

    return dict(grouped_chunks)


def main() -> None:
    page_documents = load_pdf_directory(
        papers_dir=PAPERS_DIR,
        project_root=PROJECT_ROOT,
    )

    chunk_documents = split_pages(
        page_documents=page_documents,
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )

    print(f"页面总数：{len(page_documents)}")
    print(f"Chunk总数：{len(chunk_documents)}")
    print(f"配置Chunk大小：{DEFAULT_CHUNK_SIZE}")
    print(f"配置重叠大小：{DEFAULT_CHUNK_OVERLAP}")

    grouped_chunks = group_chunks_by_source(chunk_documents)

    for source_file, source_chunks in grouped_chunks.items():
        lengths = [len(chunk.page_content) for chunk in source_chunks]

        print("=" * 80)
        print(f"论文：{source_file}")
        print(f"Chunk数量：{len(source_chunks)}")
        print(f"最短Chunk：{min(lengths)}")
        print(f"最长Chunk：{max(lengths)}")
        print(f"平均Chunk：" f"{sum(lengths) / len(lengths):.2f}")

    print("=" * 80)
    print("前三个Chunk示例：")

    for chunk in chunk_documents[:3]:
        print("-" * 80)
        print(f"元数据：{chunk.metadata}")
        print(f"文本：{clean_preview(chunk.page_content)}")


if __name__ == "__main__":
    main()
