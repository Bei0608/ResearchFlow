from pydantic import BaseModel, ConfigDict, Field


class MCPResultModel(BaseModel):
    """MCP结构化输出的严格基类。"""

    model_config = ConfigDict(extra="forbid")


class PaperListResult(MCPResultModel):
    total: int = Field(ge=0)
    count: int = Field(ge=0)
    offset: int = Field(ge=0)
    papers: list[str]
    has_more: bool
    next_offset: int | None
    markdown: str


class EvidenceItem(MCPResultModel):
    rank: int = Field(ge=1)
    chunk_id: str
    source_file: str
    page_number: int = Field(ge=1)
    score: float
    content: str


class PaperSearchResult(MCPResultModel):
    query: str
    count: int = Field(ge=0)
    evidence: list[EvidenceItem]
    markdown: str


class ResearchAnswerResult(MCPResultModel):
    thread_id: str
    question: str
    answer: str
    route: str
    evidence_count: int = Field(ge=0)
    citations: list[str]
    executed_nodes: list[str]
    markdown: str
