from app.tools.paper_catalog import list_available_papers
from app.tools.paper_search import search_research_papers
from app.tools.memory_tools import (
    MEMORY_TOOLS,
    delete_user_memory,
    list_user_memories,
    save_user_memory,
    update_user_memory,
)

PAPER_TOOLS = [
    list_available_papers,
    search_research_papers,
]

AGENT_TOOLS = [
    *PAPER_TOOLS,
    *MEMORY_TOOLS,
]


__all__ = [
    "MEMORY_TOOLS",
    "RESEARCH_TOOLS",
    "delete_user_memory",
    "list_available_papers",
    "list_user_memories",
    "save_user_memory",
    "search_research_papers",
    "update_user_memory",
]
