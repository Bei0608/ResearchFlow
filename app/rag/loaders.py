from hashlib import sha256
from pathlib import Path

from pypdf import PdfReader
from langchain_core.documents import Document

from app.models.document import PageMetadata


def discover_pdf_files(papers_dir: Path) -> list[Path]:
    """递归发现目录中的所有PDF文件。"""
    papers_dir = papers_dir.resolve()

    if not papers_dir.exists():
        raise FileNotFoundError(f"论文目录不存在：{papers_dir}")

    if not papers_dir.is_dir():
        raise NotADirectoryError(f"论文路径不是目录：{papers_dir}")

    pdf_files = sorted(path for path in papers_dir.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")

    if not pdf_files:
        raise FileNotFoundError(f"论文目录中没有PDF文件：{papers_dir}")

    return pdf_files


def calculate_file_hash(file_path: Path) -> str:
    """分块读取文件并计算SHA-256，避免一次性加载整个PDF。"""
    hash_object = sha256()

    with file_path.open("rb") as file:
        while data := file.read(1024 * 1024):
            hash_object.update(data)

    return hash_object.hexdigest()


def normalize_metadata_value(
    value: object,
) -> str | None:
    """将pypdf元数据转换成普通字符串。"""
    if value is None:
        return None

    normalized_value = str(value).strip()

    return normalized_value or None


def get_relative_source_path(
    file_path: Path,
    project_root: Path,
) -> str:
    """生成不依赖具体电脑盘符的相对来源路径。"""
    try:
        relative_path = file_path.resolve().relative_to(project_root.resolve())
        return relative_path.as_posix()
    except ValueError:
        return file_path.name


def load_pdf_pages(
    pdf_path: Path,
    project_root: Path,
) -> list[Document]:
    """逐页加载PDF，并为每页生成统一元数据。"""
    pdf_path = pdf_path.resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF不存在：{pdf_path}")

    if not pdf_path.is_file():
        raise ValueError(f"PDF路径不是文件：{pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"文件不是PDF：{pdf_path}")

    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    if total_pages == 0:
        raise ValueError(f"PDF没有任何页面：{pdf_path}")

    document_id = calculate_file_hash(pdf_path)
    source_path = get_relative_source_path(
        file_path=pdf_path,
        project_root=project_root,
    )

    raw_pdf_metadata = reader.metadata or {}

    title = normalize_metadata_value(raw_pdf_metadata.get("/Title"))
    author = normalize_metadata_value(raw_pdf_metadata.get("/Author"))

    page_labels = getattr(reader, "page_labels", None)

    normalized_documents: list[Document] = []

    for page_index, page in enumerate(reader.pages):
        page_number = page_index + 1
        page_content = page.extract_text() or ""

        page_label = None

        if isinstance(page_labels, list) and page_index < len(page_labels):
            page_label = normalize_metadata_value(page_labels[page_index])

        metadata_model = PageMetadata(
            document_id=document_id,
            page_id=f"{document_id}:page:{page_number}",
            source_file=pdf_path.name,
            source_path=source_path,
            file_size_bytes=pdf_path.stat().st_size,
            page_number=page_number,
            total_pages=total_pages,
            title=title,
            author=author,
            page_label=page_label,
        )

        normalized_document = Document(
            page_content=page_content,
            metadata=metadata_model.model_dump(exclude_none=True),
        )
        normalized_documents.append(normalized_document)

    return normalized_documents


def load_pdf_directory(
    papers_dir: Path,
    project_root: Path,
) -> list[Document]:
    """加载目录中所有PDF的全部页面。"""
    documents: list[Document] = []

    for pdf_path in discover_pdf_files(papers_dir):
        documents.extend(
            load_pdf_pages(
                pdf_path=pdf_path,
                project_root=project_root,
            )
        )

    return documents
