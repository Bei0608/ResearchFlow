from pathlib import Path

from langchain_core.tools import tool

from app.rag.loaders import discover_pdf_files

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAPERS_DIR = PROJECT_ROOT / "data" / "papers"


@tool("list_available_papers")
def list_available_papers() -> str:
    """
    列出当前本地论文知识库中包含的全部PDF文件。

    当用户询问知识库有哪些论文、包含哪些资料、
    可以研究哪些论文时使用此工具。
    此工具只提供论文目录，不用于回答论文的具体内容。
    """
    pdf_files = discover_pdf_files(PAPERS_DIR)

    result_lines = [f"当前知识库共有{len(pdf_files)}篇论文："]

    for index, pdf_file in enumerate(
        pdf_files,
        start=1,
    ):
        result_lines.append(f"{index}. {pdf_file.name}")

    return "\n".join(result_lines)
