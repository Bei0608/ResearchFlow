from pathlib import Path

from app.rag.loaders import (
    discover_pdf_files,
    load_pdf_pages,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAPERS_DIR = PROJECT_ROOT / "data" / "papers"


def clean_preview(text: str, max_length: int = 300) -> str:
    """生成便于在终端显示的文本预览。"""
    return " ".join(text.split())[:max_length]


def inspect_pdf(pdf_path: Path) -> None:
    """检查一篇PDF的加载结果。"""
    print("=" * 80)
    print(f"论文：{pdf_path.name}")

    documents = load_pdf_pages(
        pdf_path=pdf_path,
        project_root=PROJECT_ROOT,
    )

    empty_pages = [document.metadata["page_number"] for document in documents if not document.page_content.strip()]

    total_characters = sum(len(document.page_content) for document in documents)

    first_non_empty_document = next(
        (document for document in documents if document.page_content.strip()),
        None,
    )

    print(f"document_id：{documents[0].metadata['document_id']}")
    print(f"总页数：{len(documents)}")
    print(f"提取字符数：{total_characters}")
    print(f"空文本页数：{len(empty_pages)}")

    if empty_pages:
        print(f"空文本页：{empty_pages}")

    if first_non_empty_document is not None:
        print("第一页有效文本的标准元数据：")
        print(first_non_empty_document.metadata)

        print("文本预览：")
        print(clean_preview(first_non_empty_document.page_content))
    else:
        print("警告：整篇PDF都没有提取到文本。")


def main() -> None:
    pdf_files = discover_pdf_files(PAPERS_DIR)

    print(f"论文目录：{PAPERS_DIR}")
    print(f"发现PDF数量：{len(pdf_files)}")

    for pdf_path in pdf_files:
        try:
            inspect_pdf(pdf_path)
        except Exception as error:
            print("=" * 80)
            print(f"论文：{pdf_path.name}")
            print(f"加载失败：{type(error).__name__}: {error}")


if __name__ == "__main__":
    main()
