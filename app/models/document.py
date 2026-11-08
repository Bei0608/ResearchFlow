from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PageMetadata(BaseModel):
    """一页PDF文档的标准元数据。"""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(
        min_length=64,
        max_length=64,
        description="根据PDF内容计算出的SHA-256标识",
    )
    page_id: str = Field(
        description="当前页面的唯一标识",
    )
    source_file: str = Field(
        min_length=1,
        description="PDF文件名",
    )
    source_path: str = Field(
        min_length=1,
        description="PDF相对于项目根目录的路径",
    )
    file_type: Literal["pdf"] = "pdf"
    file_size_bytes: int = Field(ge=0)
    page_number: int = Field(
        ge=1,
        description="从1开始的物理页码",
    )
    total_pages: int = Field(ge=1)

    title: str | None = None
    author: str | None = None
    page_label: str | None = None


class ChunkMetadata(PageMetadata):
    """一个文本块的标准元数据。"""

    chunk_id: str = Field(
        min_length=64,
        max_length=64,
        description="文本块的SHA-256唯一标识",
    )
    chunk_index: int = Field(
        ge=0,
        description="当前页面内从0开始的文本块序号",
    )
    chunk_char_count: int = Field(
        ge=1,
        description="文本块包含的字符数量",
    )
    splitter: Literal["recursive_character"] = "recursive_character"
    configured_chunk_size: int = Field(ge=1)
    configured_chunk_overlap: int = Field(ge=0)
