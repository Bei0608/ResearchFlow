from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchContext:
    """ResearchFlow Agent单次运行所需的上下文。"""

    user_id: str
