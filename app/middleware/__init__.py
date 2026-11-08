from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)

from app.middleware.error_handling import (
    tool_error_middleware,
)

from app.middleware.memory_prompt import (
    inject_user_memories,
)

from app.middleware.observability import (
    observe_model_call,
    observe_tool_call,
)

AGENT_MIDDLEWARE = [
    # 每次调用模型前，注入当前用户的长期记忆
    inject_user_memories,
    observe_model_call,
    # 错误处理在外层，负责接住内部工具异常。
    tool_error_middleware,
    # 观测在内层，因此仍然可以记录工具失败。
    observe_tool_call,
    ModelCallLimitMiddleware(
        run_limit=6,
        exit_behavior="end",
    ),
    ToolCallLimitMiddleware(
        tool_name="search_research_papers",
        run_limit=2,
        exit_behavior="continue",
    ),
    ToolCallLimitMiddleware(
        run_limit=4,
        exit_behavior="error",
    ),
]


__all__ = [
    "AGENT_MIDDLEWARE",
    "inject_user_memories",
    "observe_model_call",
    "observe_tool_call",
    "tool_error_middleware",
]
