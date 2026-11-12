"""Strategic Model Routing across Gemini 2.5 Pro and Flash Tiers (Criterion 3.2).

Dynamically routes tasks to the optimal Gemini model tier based on reasoning
complexity, latency targets, and cost efficiency:
- `gemini-2.5-pro`: Assigned to high-reasoning tasks (Coordinator multi-agent
  orchestration, end-to-end 28-day constraint solving, and LLM-as-a-Judge quality
  evaluation).
- `gemini-2.5-flash`: Assigned to low-latency, high-throughput tasks (parallel
  North/South Island segment lookups, campsite/weather tool execution, media
  gallery curation, and history summarization).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Literal

TaskComplexityTier = Literal[
    "coordinator_orchestration",
    "quality_judge_evaluation",
    "complex_constraint_planning",
    "island_segment_planning",
    "campsite_and_ferry_logistics",
    "media_and_website_generation",
    "history_summarization",
]

REASONING_ARCHITECT_MODEL = os.environ.get(
    "KIWICAMP_PRO_MODEL", "gemini-2.5-pro"
)
FAST_EXECUTION_MODEL = os.environ.get(
    "KIWICAMP_FLASH_MODEL", "gemini-2.5-flash"
)


@dataclass
class StrategicModelRouter:
    """Routes each agent role or dynamic query to the optimal Gemini model tier."""

    pro_model: str = REASONING_ARCHITECT_MODEL
    flash_model: str = FAST_EXECUTION_MODEL
    role_routing_table: Dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.role_routing_table = {
            "coordinator_orchestration": self.pro_model,
            "quality_judge_evaluation": self.pro_model,
            "complex_constraint_planning": self.pro_model,
            "island_segment_planning": self.flash_model,
            "campsite_and_ferry_logistics": self.flash_model,
            "media_and_website_generation": self.flash_model,
            "history_summarization": self.flash_model,
        }

    def get_model_for_role(self, role: TaskComplexityTier) -> str:
        """Returns the configured Gemini model identifier for a specific agent role."""
        return self.role_routing_table.get(role, self.flash_model)

    def route_by_query_complexity(self, user_query: str) -> str:
        """Dynamically selects `gemini-2.5-pro` vs `gemini-2.5-flash` from prompt signals."""
        q_low = (user_query or "").lower()
        complex_indicators = (
            "28-day",
            "4-week",
            "four-week",
            "full itinerary",
            "cape reinga",
            "slope point",
            "bluff",
            "optimize",
            "compare",
            "evaluate",
            "re-plan",
            "budget breakdown",
        )
        if any(ind in q_low for ind in complex_indicators) or len(q_low.split()) > 35:
            return self.pro_model
        return self.flash_model


_DEFAULT_ROUTER = StrategicModelRouter()


def select_model_for_task(role: TaskComplexityTier) -> str:
    """Convenience helper to fetch the routed model name for a task tier."""
    return _DEFAULT_ROUTER.get_model_for_role(role)
