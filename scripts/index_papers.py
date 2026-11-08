from pathlib import Path

from app.rag.indexer import index_pdf_directory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAPERS_DIR = PROJECT_ROOT / "data" / "papers"


def main() -> None:
    print(f"论文目录：{PAPERS_DIR}")
    print("开始检查PDF和Milvus索引……")

    result = index_pdf_directory(
        papers_dir=PAPERS_DIR,
        project_root=PROJECT_ROOT,
    )

    print("=" * 60)
    print("论文索引完成")
    print(f"页面数量：{result.page_count}")
    print(f"本次发现Chunk：{result.chunk_count}")
    print(f"本次新增Chunk：{result.inserted_count}")
    print(f"本次跳过Chunk：{result.skipped_count}")
    print(f"已确认有效Chunk：{result.indexed_count}")
    print(f"集合名称：{result.collection_name}")
    print(f"集合原本存在：{result.collection_existed}")


if __name__ == "__main__":
    main()
