from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class ModelStats:
    model_name: str
    response_time: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    content: str = ""
    raw_request: Dict[str, Any] = field(default_factory=dict)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


@dataclass
class ExperimentResult:
    system_prompt: str
    user_prompt: str
    model_stats: List[ModelStats] = field(default_factory=list)
    eval_result: Optional[str] = None
    eval_model: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class Statistics:
    def __init__(self):
        self.experiments: List[ExperimentResult] = []

    def add_result(
        self,
        system_prompt: str,
        user_prompt: str,
        stats: List[ModelStats],
    ):
        result = ExperimentResult(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_stats=stats,
        )
        self.experiments.append(result)

    def set_eval_result(self, eval_result: str, eval_model: str):
        if self.experiments:
            self.experiments[-1].eval_result = eval_result
            self.experiments[-1].eval_model = eval_model

    def get_latest_stats(self) -> Optional[ExperimentResult]:
        return self.experiments[-1] if self.experiments else None

    def format_stats_text(self, stats: List[ModelStats]) -> str:
        lines = []
        for s in stats:
            if s.error:
                lines.append(f"{s.model_name}: ERROR - {s.error}")
            else:
                lines.append(
                    f"{s.model_name}: {s.response_time:.2f}s | "
                    f"Tokens: {s.prompt_tokens} + {s.completion_tokens} = {s.total_tokens}"
                )
        return "\n".join(lines)
