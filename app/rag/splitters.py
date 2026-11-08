import re
from hashlib import sha256
from typing import Iterable

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.models.document import ChunkMetadata, PageMetadata

DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 200

CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_page_text(text: str) -> str:
    """执行保守的文本清洗，不改变原始语义。"""
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("\u00ad", "")
    text = CONTROL_CHARACTER_PATTERN.sub("", text)

    cleaned_lines = []

    for line in text.split("\n"):
        cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned_lines.append(cleaned_line)

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()


def create_chunk_id(
    page_id: str,
    chunk_index: int,
    chunk_text: str,
) -> str:
    """根据页面、块序号和内容生成稳定的Chunk ID。"""
    identity = f"{page_id}:{chunk_index}:{chunk_text}"
    return sha256(identity.encode("utf-8")).hexdigest()


def create_text_splitter(
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> RecursiveCharacterTextSplitter:
    """创建适合中英文论文的递归字符分块器。"""
    if chunk_size <= 0:
        raise ValueError("chunk_size必须大于0")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap不能小于0")

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap必须小于chunk_size")

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        keep_separator=True,
        strip_whitespace=True,
        separators=[
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            "；",
            ". ",
            "! ",
            "? ",
            "; ",
            "，",
            ", ",
            " ",
            "",
        ],
    )


def split_pages(
    page_documents: Iterable[Document],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    """逐页清洗并分块，同时保留论文和页码信息。"""
    splitter = create_text_splitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    chunk_documents: list[Document] = []

    for page_document in page_documents:
        page_metadata = PageMetadata.model_validate(page_document.metadata)

        cleaned_page_text = clean_page_text(page_document.page_content)

        if not cleaned_page_text:
            continue

        chunk_texts = splitter.split_text(cleaned_page_text)

        for chunk_index, chunk_text in enumerate(chunk_texts):
            chunk_text = chunk_text.strip()

            if not chunk_text:
                continue

            chunk_id = create_chunk_id(
                page_id=page_metadata.page_id,
                chunk_index=chunk_index,
                chunk_text=chunk_text,
            )

            chunk_metadata = ChunkMetadata(
                **page_metadata.model_dump(),
                chunk_id=chunk_id,
                chunk_index=chunk_index,
                chunk_char_count=len(chunk_text),
                configured_chunk_size=chunk_size,
                configured_chunk_overlap=chunk_overlap,
            )

            chunk_document = Document(
                page_content=chunk_text,
                metadata=chunk_metadata.model_dump(exclude_none=True),
            )
            chunk_documents.append(chunk_document)

    return chunk_documents
