"""History Compaction, Sliding Windows, and Context Caching (Criterion 2.2).

Prevents context bloat during multi-turn 28-day itinerary refinement sessions via:
1. ADK `EventsCompactionConfig` + `LlmEventSummarizer` (summarizing older turns every
   `compaction_interval` invocations while preserving `overlap_size` recent turns).
2. ADK `ContextFilterPlugin` (retaining the last `num_invocations_to_keep` turns).
3. ADK `ContextCacheConfig` (caching large constitutional prompts & 28-day reference
   knowledge across turns).
4. `SlidingWindowHistoryCompactor` (deterministic token estimation, truncation, and
   rolling summary generation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

try:
    from google.adk.apps.app import EventsCompactionConfig
    from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
    from google.adk.models import Gemini
    from google.adk.plugins.context_filter_plugin import ContextFilterPlugin
except ImportError:  # pragma: no cover - offline compatibility shim
    EventsCompactionConfig = None  # type: ignore[assignment,misc]
    LlmEventSummarizer = None  # type: ignore[assignment,misc]
    Gemini = None  # type: ignore[assignment,misc]
    ContextFilterPlugin = None  # type: ignore[assignment,misc]

try:
    from google.adk.agents.context_cache_config import ContextCacheConfig
except ImportError:  # pragma: no cover
    ContextCacheConfig = None  # type: ignore[assignment,misc]


@dataclass
class SlidingWindowHistoryCompactor:
    """Manages conversation history compaction via sliding window + rolling summary.

    Attributes:
        max_token_budget: Maximum token budget allocated to conversation history.
        sliding_window_turns: Number of most recent turns kept verbatim.
        compaction_interval: Number of turns that trigger a rolling summarization pass.
        overlap_size: Overlap of turns included in successive summaries for continuity.
    """

    max_token_budget: int = 16000
    sliding_window_turns: int = 8
    compaction_interval: int = 10
    overlap_size: int = 2
    summaries_generated: int = field(default=0, init=False)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimates token count (~4 characters per token heuristic)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def summarize_evicted_events(self, evicted_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compacts older conversation events into a single rolling summary event."""
        self.summaries_generated += 1
        key_points: List[str] = []
        for ev in evicted_events:
            role = ev.get("role", "user")
            content = str(ev.get("content", "")).strip()
            if content:
                snippet = content[:140] + ("..." if len(content) > 140 else "")
                key_points.append(f"[{role}] {snippet}")

        summary_text = (
            f"[COMPACTED_HISTORY_SUMMARY #{self.summaries_generated} "
            f"({len(evicted_events)} earlier turns)] " + " | ".join(key_points[:10])
        )
        return {
            "role": "system",
            "event_type": "compacted_summary",
            "compacted_turn_count": len(evicted_events),
            "content": summary_text,
        }

    def compact_history(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Applies sliding-window truncation and summarization when turns or tokens exceed thresholds."""
        if not events:
            return []

        total_tokens = sum(
            self.estimate_tokens(str(e.get("content", ""))) for e in events
        )
        needs_compaction = (
            len(events) > self.sliding_window_turns
            or len(events) >= self.compaction_interval
            or total_tokens > self.max_token_budget
        )

        if not needs_compaction:
            return list(events)

        keep_count = max(self.overlap_size, min(self.sliding_window_turns, len(events)))
        evicted = events[:-keep_count]
        recent = events[-keep_count:]

        if not evicted:
            return recent

        summary_event = self.summarize_evicted_events(evicted)
        return [summary_event, *recent]


def build_events_compaction_config(
    summarizer_model: str = "gemini-2.5-flash",
    compaction_interval: int = 10,
    overlap_size: int = 2,
) -> Any:
    """Builds the official ADK `EventsCompactionConfig` with `LlmEventSummarizer`."""
    if (
        EventsCompactionConfig is not None
        and LlmEventSummarizer is not None
        and Gemini is not None
    ):
        summarizer_llm = Gemini(model=summarizer_model)
        summarizer = LlmEventSummarizer(llm=summarizer_llm)
        return EventsCompactionConfig(
            compaction_interval=compaction_interval,
            overlap_size=overlap_size,
            summarizer=summarizer,
        )
    return {
        "type": "EventsCompactionConfig",
        "compaction_interval": compaction_interval,
        "overlap_size": overlap_size,
        "summarizer_model": summarizer_model,
    }


def build_context_filter_plugin(num_invocations_to_keep: int = 8) -> Any:
    """Builds the ADK `ContextFilterPlugin` to bound active context turns."""
    if ContextFilterPlugin is not None:
        return ContextFilterPlugin(num_invocations_to_keep=num_invocations_to_keep)
    return {
        "type": "ContextFilterPlugin",
        "num_invocations_to_keep": num_invocations_to_keep,
    }


def build_context_cache_config(
    min_tokens: int = 2048,
    ttl_seconds: int = 3600,
    cache_intervals: int = 5,
) -> Any:
    """Builds the ADK `ContextCacheConfig` to cache constitutional instructions."""
    if ContextCacheConfig is not None:
        return ContextCacheConfig(
            min_tokens=min_tokens,
            ttl_seconds=ttl_seconds,
            cache_intervals=cache_intervals,
        )
    return {
        "type": "ContextCacheConfig",
        "min_tokens": min_tokens,
        "ttl_seconds": ttl_seconds,
        "cache_intervals": cache_intervals,
    }
