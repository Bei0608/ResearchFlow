import logging
from time import perf_counter

from langchain.agents.middleware import (
    wrap_model_call,
    wrap_tool_call,
)
from app.observability.metrics import (
    MODEL_CALLS,
    MODEL_DURATION,
    MODEL_TOKENS,
    TOOL_CALLS,
    TOOL_DURATION,
)

logger = logging.getLogger("researchflow.middleware")


@wrap_model_call
def observe_model_call(request, handler):
    """记录每次模型调用的消息数量和耗时。"""
    message_count = len(request.state.get("messages", []))

    started_at = perf_counter()

    logger.info(
        "模型调用开始 message_count=%s",
        message_count,
    )

    try:
        response = handler(request)
    except Exception:
        duration = perf_counter() - started_at
        MODEL_CALLS.labels(status="error").inc()
        MODEL_DURATION.observe(duration)

        logger.exception(
            "模型调用失败 duration=%.3fs",
            duration,
        )
        raise

    duration = perf_counter() - started_at
    MODEL_CALLS.labels(status="success").inc()
    MODEL_DURATION.observe(duration)

    for message in getattr(response, "result", []):
        usage = getattr(message, "usage_metadata", None) or {}
        for token_type in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
        ):
            value = usage.get(token_type)
            if isinstance(value, int) and value >= 0:
                MODEL_TOKENS.labels(
                    token_type=token_type
                ).inc(value)

    logger.info(
        "模型调用完成 duration=%.3fs",
        duration,
    )

    return response


@wrap_tool_call
def observe_tool_call(request, handler):
    """记录工具名称和工具执行耗时。"""
    tool_name = request.tool_call["name"]
    started_at = perf_counter()

    logger.info(
        "工具调用开始 tool=%s",
        tool_name,
    )

    try:
        response = handler(request)
    except Exception:
        duration = perf_counter() - started_at
        TOOL_CALLS.labels(
            tool=tool_name,
            status="error",
        ).inc()
        TOOL_DURATION.labels(tool=tool_name).observe(duration)

        logger.exception(
            "工具调用失败 tool=%s duration=%.3fs",
            tool_name,
            duration,
        )
        raise

    duration = perf_counter() - started_at
    TOOL_CALLS.labels(
        tool=tool_name,
        status="success",
    ).inc()
    TOOL_DURATION.labels(tool=tool_name).observe(duration)

    logger.info(
        "工具调用完成 tool=%s duration=%.3fs",
        tool_name,
        duration,
    )

    return response
