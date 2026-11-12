"""KiwiCamp: 4-Week New Zealand Campervan Odyssey Agent package.

Exposes the root ADK `agent` (`root_agent`) and `app` (`adk_app`) for Vertex AI
Agent Engine (`ReasoningEngine`), ADK Web UI, and A2A interoperability.
"""

from app.agent import adk_app as app
from app.agent import root_agent as agent

__all__ = ["agent", "app"]
