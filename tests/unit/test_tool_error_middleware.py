from langchain.agents.middleware.types import (
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage

from app.middleware.error_handling import (
    tool_error_middleware,
)


def test_tool_error_is_converted_to_safe_message() -> None:
    request = ToolCallRequest(
        tool_call={
            "name": "search_research_papers",
            "args": {
                "query": "RT-2",
            },
            "id": "test-call-id",
            "type": "tool_call",
        },
        tool=None,
        state={},
        runtime=None,
    )

    def failing_handler(_request):
        raise ConnectionError("database-secret-address")

    response = tool_error_middleware.wrap_tool_call(
        request,
        failing_handler,
    )

    assert isinstance(response, ToolMessage)
    assert response.status == "error"
    assert response.tool_call_id == "test-call-id"

    assert "当前无法获得可信的工具结果" in str(response.content)

    # 内部异常详情不能泄露给模型。
    assert "database-secret-address" not in str(response.content)
