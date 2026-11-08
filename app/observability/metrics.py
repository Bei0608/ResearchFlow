from prometheus_client import Counter, Gauge, Histogram


HTTP_REQUESTS = Counter(
    "researchflow_http_requests_total",
    "HTTP requests by method, route and status",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "researchflow_http_request_duration_seconds",
    "HTTP request duration by method and route",
    ["method", "route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
HTTP_IN_PROGRESS = Gauge(
    "researchflow_http_requests_in_progress",
    "HTTP requests currently being processed",
)
RATE_LIMIT_REJECTIONS = Counter(
    "researchflow_rate_limit_rejections_total",
    "Requests rejected by the API rate limiter",
)
RATE_LIMIT_BACKEND_ERRORS = Counter(
    "researchflow_rate_limit_backend_errors_total",
    "Rate limiter backend failures that triggered fallback",
)
RETRIEVAL_CACHE_OPERATIONS = Counter(
    "researchflow_retrieval_cache_operations_total",
    "Retrieval cache operations by outcome",
    ["outcome"],
)
MODEL_CALLS = Counter(
    "researchflow_model_calls_total",
    "Model calls by outcome",
    ["status"],
)
MODEL_DURATION = Histogram(
    "researchflow_model_call_duration_seconds",
    "Model call duration",
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
MODEL_TOKENS = Counter(
    "researchflow_model_tokens_total",
    "Model token usage reported by the provider",
    ["token_type"],
)
TOOL_CALLS = Counter(
    "researchflow_tool_calls_total",
    "Tool calls by tool and outcome",
    ["tool", "status"],
)
TOOL_DURATION = Histogram(
    "researchflow_tool_call_duration_seconds",
    "Tool call duration by tool",
    ["tool"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
