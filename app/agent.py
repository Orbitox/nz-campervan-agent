"""Multi-Agent Hierarchy & ADK App Definition for KiwiCamp (Criteria 2.1-2.4, 3.1-3.4).

Constructs the complete multi-agent architecture:
- `NorthIslandPlannerAgent` (`gemini-2.5-flash`): Plans Days 1-12 (Auckland -> Cape Reinga -> Wellington).
- `SouthIslandPlannerAgent` (`gemini-2.5-flash`): Plans Days 13-28 (Cook Strait -> Milford Sound -> Bluff/Slope Point -> Christchurch).
- `ParallelIslandPlanners` (`ParallelAgent`): Runs North & South Island planners concurrently.
- `CampervanLogisticsAgent` (`gemini-2.5-flash`): Validates campsite availability, drive limits, and HITL ferry/holiday park reservations.
- `ItineraryQualityRefinementLoop` (`LoopAgent`): Iteratively runs `MediaAndWebsiteBuilderAgent` (`gemini-2.5-flash`), `ItineraryQualityJudgeAgent` (`gemini-2.5-pro`, `output_schema=ItineraryQualityEvaluation`), and `ItineraryEscalationChecker(BaseAgent)`.
- `OdysseyPlanningPipeline` (`SequentialAgent`): Chains `ParallelIslandPlanners` -> `CampervanLogisticsAgent` -> `ItineraryQualityRefinementLoop`.
- `KiwiCampCoordinatorAgent` (`root_agent`, `gemini-2.5-pro`): Root constitutional coordinator with `PreloadMemoryTool`, `after_agent_callback` async memory consolidation, and `App` history compaction / security plugins.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, List, Optional

from app.context.compaction import (
    build_context_cache_config,
    build_context_filter_plugin,
    build_events_compaction_config,
)
from app.memory.async_memory_bank import (
    AsyncMemoryBankManager,
    trigger_async_memory_consolidation_callback,
)
from app.observability.telemetry import configure_observability
from app.orchestration.model_router import select_model_for_task
from app.plugins.security_guardrails import (
    AgentOpsSecurityAndPolicyPlugin,
    build_reflect_and_retry_plugin,
)
from app.prompts.constitution import (
    CAMPERVAN_LOGISTICS_INSTRUCTION,
    COORDINATOR_SYSTEM_CONSTITUTION,
    ITINERARY_QUALITY_JUDGE_INSTRUCTION,
    MEDIA_AND_WEBSITE_BUILDER_INSTRUCTION,
    NORTH_ISLAND_PLANNER_INSTRUCTION,
    SOUTH_ISLAND_PLANNER_INSTRUCTION,
)
from app.schemas.itinerary_schemas import ItineraryQualityEvaluation
from app.tools.nz_campervan_tools import (
    ALL_CAMPERVAN_FUNCTION_TOOLS,
    book_paid_holiday_park_site_tool,
    calculate_campervan_route_segment,
    check_december_weather_and_seasonal_hazards,
    fetch_destination_media_gallery,
    generate_interactive_itinerary_website,
    reserve_cook_strait_campervan_ferry_tool,
    search_nz_holiday_parks_and_campsites,
)

try:
    from google.adk.agents import (
        BaseAgent,
        InvocationContext,
        LlmAgent,
        LoopAgent,
        ParallelAgent,
        SequentialAgent,
    )
    from google.adk.apps.app import App
    from google.adk.events import Event, EventActions
except ImportError:  # pragma: no cover - lightweight compatibility classes for offline unit tests
    class InvocationContext:  # type: ignore[no-redef]
        def __init__(self, session: Any = None) -> None:
            self.session = session

    class EventActions:  # type: ignore[no-redef]
        def __init__(self, escalate: bool = False) -> None:
            self.escalate = escalate

    class Event:  # type: ignore[no-redef]
        def __init__(self, author: str, actions: Optional[EventActions] = None) -> None:
            self.author = author
            self.actions = actions or EventActions()

    class BaseAgent:  # type: ignore[no-redef]
        def __init__(self, name: str, description: str = "", **kwargs: Any) -> None:
            self.name = name
            self.description = description
            for k, v in kwargs.items():
                setattr(self, k, v)

    class LlmAgent(BaseAgent):  # type: ignore[no-redef]
        def __init__(
            self,
            *,
            name: str,
            model: str,
            description: str = "",
            instruction: str = "",
            tools: Optional[List[Any]] = None,
            sub_agents: Optional[List[Any]] = None,
            output_key: Optional[str] = None,
            output_schema: Optional[Any] = None,
            after_agent_callback: Optional[Any] = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(name=name, description=description, **kwargs)
            self.model = model
            self.instruction = instruction
            self.tools = list(tools or [])
            self.sub_agents = list(sub_agents or [])
            self.output_key = output_key
            self.output_schema = output_schema
            self.after_agent_callback = after_agent_callback

    class ParallelAgent(BaseAgent):  # type: ignore[no-redef]
        def __init__(
            self,
            *,
            name: str,
            description: str = "",
            sub_agents: Optional[List[Any]] = None,
        ) -> None:
            super().__init__(name=name, description=description)
            self.sub_agents = list(sub_agents or [])

    class SequentialAgent(BaseAgent):  # type: ignore[no-redef]
        def __init__(
            self,
            *,
            name: str,
            description: str = "",
            sub_agents: Optional[List[Any]] = None,
        ) -> None:
            super().__init__(name=name, description=description)
            self.sub_agents = list(sub_agents or [])

    class LoopAgent(BaseAgent):  # type: ignore[no-redef]
        def __init__(
            self,
            *,
            name: str,
            description: str = "",
            max_iterations: int = 3,
            sub_agents: Optional[List[Any]] = None,
        ) -> None:
            super().__init__(name=name, description=description)
            self.max_iterations = max_iterations
            self.sub_agents = list(sub_agents or [])

    class App:  # type: ignore[no-redef]
        def __init__(
            self,
            *,
            name: str,
            root_agent: Any,
            events_compaction_config: Optional[Any] = None,
            context_cache_config: Optional[Any] = None,
            plugins: Optional[List[Any]] = None,
        ) -> None:
            self.name = name
            self.root_agent = root_agent
            self.events_compaction_config = events_compaction_config
            self.context_cache_config = context_cache_config
            self.plugins = list(plugins or [])


configure_observability()


class ItineraryEscalationChecker(BaseAgent):
    """Custom ADK `BaseAgent` that inspects `quality_evaluation` and escalates `LoopAgent` when `grade == 'pass'`."""

    def __init__(self, name: str = "ItineraryEscalationChecker") -> None:
        super().__init__(
            name=name,
            description="Checks ItineraryQualityEvaluation in session.state and escalates LoopAgent once passing.",
        )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        evaluation = ctx.session.state.get("quality_evaluation") if ctx.session else None
        grade = None
        if isinstance(evaluation, dict):
            grade = evaluation.get("grade")
        elif evaluation is not None:
            grade = getattr(evaluation, "grade", None)

        if grade == "pass":
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            yield Event(author=self.name)


# 1. Parallel Island Research Sub-Agents (Fast Flash Model Tier)
north_island_planner_agent = LlmAgent(
    name="NorthIslandPlannerAgent",
    model=select_model_for_task("island_segment_planning"),
    description="Plans Days 1-12 across the North Island (Auckland arrival -> Cape Reinga northern tip -> Wellington).",
    instruction=NORTH_ISLAND_PLANNER_INSTRUCTION,
    tools=[
        calculate_campervan_route_segment,
        search_nz_holiday_parks_and_campsites,
        check_december_weather_and_seasonal_hazards,
    ],
    output_key="north_island_plan",
)

south_island_planner_agent = LlmAgent(
    name="SouthIslandPlannerAgent",
    model=select_model_for_task("island_segment_planning"),
    description="Plans Days 13-28 across Cook Strait and the South Island (Picton -> Milford Sound -> Bluff/Slope Point southern tip -> Christchurch).",
    instruction=SOUTH_ISLAND_PLANNER_INSTRUCTION,
    tools=[
        calculate_campervan_route_segment,
        search_nz_holiday_parks_and_campsites,
        check_december_weather_and_seasonal_hazards,
    ],
    output_key="south_island_plan",
)

parallel_island_planners = ParallelAgent(
    name="ParallelIslandPlanners",
    description="Executes North Island (Days 1-12) and South Island (Days 13-28) route planning concurrently.",
    sub_agents=[north_island_planner_agent, south_island_planner_agent],
)

# 2. Campervan Logistics & HITL Booking Agent (Fast Flash Model Tier)
campervan_logistics_agent = LlmAgent(
    name="CampervanLogisticsAgent",
    model=select_model_for_task("campsite_and_ferry_logistics"),
    description="Validates daily driving limits, DOC/Holiday Park campsites, and HITL Cook Strait ferry bookings.",
    instruction=CAMPERVAN_LOGISTICS_INSTRUCTION,
    tools=[
        calculate_campervan_route_segment,
        search_nz_holiday_parks_and_campsites,
        reserve_cook_strait_campervan_ferry_tool,
        book_paid_holiday_park_site_tool,
    ],
    output_key="logistics_plan",
)

# 3. Iterative Quality Refinement Loop (Media Builder + Pro Judge + Escalation Checker)
media_and_website_builder_agent = LlmAgent(
    name="MediaAndWebsiteBuilderAgent",
    model=select_model_for_task("media_and_website_generation"),
    description="Enriches all 28 days with curated photography and YouTube video tours, and builds the interactive website.",
    instruction=MEDIA_AND_WEBSITE_BUILDER_INSTRUCTION,
    tools=[
        fetch_destination_media_gallery,
        generate_interactive_itinerary_website,
    ],
    output_key="media_website_build",
)

itinerary_quality_judge_agent = LlmAgent(
    name="ItineraryQualityJudgeAgent",
    model=select_model_for_task("quality_judge_evaluation"),
    description="Audits the 28-day itinerary and website against geographical, safety, and media completeness criteria.",
    instruction=ITINERARY_QUALITY_JUDGE_INSTRUCTION,
    output_schema=ItineraryQualityEvaluation,
    output_key="quality_evaluation",
)

itinerary_escalation_checker = ItineraryEscalationChecker()

itinerary_quality_refinement_loop = LoopAgent(
    name="ItineraryQualityRefinementLoop",
    description="Iteratively refines media curation and website generation until ItineraryQualityJudgeAgent grades 'pass'.",
    max_iterations=3,
    sub_agents=[
        media_and_website_builder_agent,
        itinerary_quality_judge_agent,
        itinerary_escalation_checker,
    ],
)

# 4. Sequential End-to-End Odyssey Pipeline
odyssey_planning_pipeline = SequentialAgent(
    name="OdysseyPlanningPipeline",
    description="End-to-end sequential workflow: Parallel Island Planners -> Campervan Logistics -> Quality Refinement Loop.",
    sub_agents=[
        parallel_island_planners,
        campervan_logistics_agent,
        itinerary_quality_refinement_loop,
    ],
)

# 5. Root Constitutional Coordinator Agent (Reasoning Pro Model Tier)
security_and_policy_plugin = AgentOpsSecurityAndPolicyPlugin()

root_agent = LlmAgent(
    name="KiwiCampCoordinatorAgent",
    model=select_model_for_task("coordinator_orchestration"),
    description="Lead New Zealand 4-Week December Campervan Expedition Architect & Interactive Website Concierge.",
    instruction=COORDINATOR_SYSTEM_CONSTITUTION,
    sub_agents=[odyssey_planning_pipeline],
    tools=[
        AsyncMemoryBankManager.build_preload_memory_tool(),
        *ALL_CAMPERVAN_FUNCTION_TOOLS,
    ],
    after_agent_callback=trigger_async_memory_consolidation_callback,
)

# 6. ADK Application with History Compaction, Context Caching & Security Plugins
adk_app = App(
    name="app",
    root_agent=root_agent,
    events_compaction_config=build_events_compaction_config(
        summarizer_model=select_model_for_task("history_summarization"),
        compaction_interval=10,
        overlap_size=2,
    ),
    context_cache_config=build_context_cache_config(
        min_tokens=2048,
        ttl_seconds=3600,
        cache_intervals=5,
    ),
    plugins=[
        security_and_policy_plugin,
        build_context_filter_plugin(num_invocations_to_keep=8),
        build_reflect_and_retry_plugin(max_retries=2),
    ],
)
