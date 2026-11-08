import logging

from langchain.agents.middleware import (
    ToolErrorMiddleware,
)

logger = logging.getLogger("researchflow.middleware")


def handle_tool_error(
    exception: Exception,
    request,
) -> str:
    """记录内部异常，并向模型返回安全的错误信息。"""
    tool_name = request.tool_call["name"]

    logger.error(
        "工具执行异常 tool=%s exception_type=%s",
        tool_name,
        type(exception).__name__,
        exc_info=(
            type(exception),
            exception,
            exception.__traceback__,
        ),
    )

    return (
        f"工具{tool_name}本次执行失败，"
        "当前无法获得可信的工具结果。"
        "不要根据缺失结果猜测答案，也不要自动重复调用；"
        "请向用户说明依赖服务暂时不可用。"
    )


tool_error_middleware = ToolErrorMiddleware(
    on_error=handle_tool_error,
)
