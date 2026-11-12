"""Vertex AI Agent Engine (`ReasoningEngine`) & A2A Protocol Entrypoint.

Exposes:
1. `KiwiCampAgentEngineApp(AdkApp)`: Production Vertex AI Agent Runtime wrapper
   implementing `set_up()`, streaming `stream_query()` with `yield from`,
   `register_operations()`, `VertexAiSessionService`, and `VertexAiMemoryBankService`.
2. `build_a2a_application()`: Exposes the KiwiCamp Coordinator Agent over the
   Agent2Agent (A2A) protocol (`google.adk.a2a.utils.agent_to_a2a.to_a2a`).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator, List, Optional

from app.agent import adk_app, root_agent
from app.memory.async_memory_bank import AsyncMemoryBankManager
from app.memory.session_and_rag import build_persistent_session_service
from app.observability.telemetry import configure_observability, get_tracer

try:
    from vertexai.preview.reasoning_engines import AdkApp
except ImportError:  # pragma: no cover - offline compatibility shim
    class AdkApp:  # type: ignore[no-redef]
        def __init__(self, *, app: Any = None, enable_tracing: bool = True, **kwargs: Any) -> None:
            self.app = app
            self.enable_tracing = enable_tracing
            self.kwargs = kwargs

        def set_up(self) -> None:
            pass

        def stream_query(self, **kwargs: Any) -> Iterator[Dict[str, Any]]:
            yield {"status": "streaming", "input": kwargs}


try:
    from google.adk.a2a.utils.agent_to_a2a import to_a2a
except ImportError:  # pragma: no cover
    to_a2a = None  # type: ignore[assignment]


class KiwiCampAgentEngineApp(AdkApp):
    """Production Vertex AI Agent Runtime (`ReasoningEngine`) wrapper for KiwiCamp."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "us-central1",
    ) -> None:
        super().__init__(
            app=adk_app,
            enable_tracing=True,
        )
        self.project_id = project_id or os.environ.get(
            "GOOGLE_CLOUD_PROJECT", "kiwicamp-prod"
        )
        self.location = location
        self.session_service: Optional[Any] = None
        self.memory_bank_manager: Optional[AsyncMemoryBankManager] = None

    def set_up(self) -> None:
        """Initializes OpenTelemetry tracing, persistent session store, and Memory Bank on container startup."""
        super().set_up()
        configure_observability(service_name="kiwicamp-reasoning-engine")
        self.session_service = build_persistent_session_service(
            project_id=self.project_id,
            location=self.location,
        )
        self.memory_bank_manager = AsyncMemoryBankManager(
            project_id=self.project_id,
            location=self.location,
        )

    def stream_query(  # type: ignore[override]
        self,
        *,
        message: str,
        user_id: str = "traveler-default",
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        """Streams events from the KiwiCamp multi-agent hierarchy using `yield from`."""
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("reasoning_engine.stream_query") as span:
            span.set_attribute("kiwicamp.user_id", user_id)
            if session_id:
                span.set_attribute("kiwicamp.session_id", session_id)
            yield from super().stream_query(
                message=message,
                user_id=user_id,
                session_id=session_id,
                **kwargs,
            )

    def register_operations(self) -> Dict[str, List[str]]:
        """Registers synchronous and streaming operations for Vertex AI Agent Runtime."""
        return {
            "": ["query", "create_session", "get_session", "list_sessions"],
            "stream": ["stream_query", "streaming_agent_run_with_events"],
        }


def build_a2a_application(host: str = "0.0.0.0", port: int = 8001) -> Any:
    """Exposes `root_agent` as an A2A-compliant Starlette/FastAPI service (`/.well-known/agent.json`)."""
    if to_a2a is not None:
        return to_a2a(root_agent, host=host, port=port)
    return {
        "protocol": "A2A",
        "agent_name": root_agent.name,
        "host": host,
        "port": port,
        "well_known_card_path": "/.well-known/agent.json",
    }


agent_engine = KiwiCampAgentEngineApp()
