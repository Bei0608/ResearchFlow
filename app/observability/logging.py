import json
import logging
import os
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """将ResearchFlow日志输出为单行JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(
                record.exc_info
            )
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """幂等配置researchflow命名空间日志。"""
    logger = logging.getLogger("researchflow")
    if getattr(logger, "_researchflow_configured", False):
        return

    handler = logging.StreamHandler()
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s"
            )
        )
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    logger._researchflow_configured = True
