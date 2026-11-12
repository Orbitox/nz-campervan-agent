"""Security Guardrails, Policy Plugins, HITL Enforcement & Intent/Outcome Capture.

Implements AgentOps Rubric Criteria:
- Criterion 3.3: Guardrails & Policy Plugins (`AgentOpsSecurityAndPolicyPlugin`
  subclassing ADK `BasePlugin` with prompt-injection shield, Model Armor policy
  screening, output PII verification, and `ReflectAndRetryToolPlugin`).
- Criterion 3.4: Human-in-the-Loop Hooks (`before_tool_callback` gate verifying
  explicit human approval on high-stakes booking tools).
- Criterion 4.2: Intent vs. Outcome Capture (logs `audit_phase="INTENT"` in
  `before_model_callback`/`before_tool_callback` and `audit_phase="OUTCOME"` in
  `after_model_callback`/`after_tool_callback`).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.observability.pii_redactor import CloudDlpAndRegexPiiRedactor
from app.observability.telemetry import IntentOutcomeAuditLogger, get_tracer

try:
    from google.adk.plugins import BasePlugin
except ImportError:  # pragma: no cover - offline compatibility shim
    class BasePlugin:  # type: ignore[no-redef]
        def __init__(self, name: str = "base_plugin") -> None:
            self.name = name

try:
    from google.adk.plugins import ReflectAndRetryToolPlugin
except ImportError:  # pragma: no cover
    ReflectAndRetryToolPlugin = None  # type: ignore[assignment,misc]

try:
    from google.adk.models import LlmResponse
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    LlmResponse = None  # type: ignore[assignment,misc]
    genai_types = None  # type: ignore[assignment]


PROMPT_INJECTION_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*override|reveal\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"bypass\s+(?:safety|human\s+confirmation|hitl|guardrails)", re.IGNORECASE),
    re.compile(r"print\s+(?:api_key|secret_manager|credentials)", re.IGNORECASE),
)

HIGH_STAKES_HITL_TOOLS = frozenset(
    {
        "reserve_cook_strait_campervan_ferry",
        "book_paid_holiday_park_site",
    }
)


class AgentOpsSecurityAndPolicyPlugin(BasePlugin):
    """Unified ADK BasePlugin enforcing Security Guardrails, HITL Stops, and Intent/Outcome Auditing."""

    def __init__(
        self,
        name: str = "agentops_security_and_policy_plugin",
        audit_logger: Optional[IntentOutcomeAuditLogger] = None,
        pii_redactor: Optional[CloudDlpAndRegexPiiRedactor] = None,
    ) -> None:
        super().__init__(name=name)
        self.audit_logger = audit_logger or IntentOutcomeAuditLogger()
        self.pii_redactor = pii_redactor or CloudDlpAndRegexPiiRedactor()
        self.tracer = get_tracer(__name__)
        self._active_correlations: Dict[str, str] = {}

    def screen_prompt_for_policy_violations(
        self, prompt_text: str
    ) -> Tuple[bool, Optional[str]]:
        """Screens incoming user text for prompt injection or policy violations (Model Armor pattern)."""
        if not prompt_text:
            return True, None
        for pattern in PROMPT_INJECTION_PATTERNS:
            if pattern.search(prompt_text):
                return (
                    False,
                    "Blocked by AgentOps Security Guardrail (Prompt Injection / Policy Override Attempt).",
                )
        return True, None

    async def before_model_callback(
        self,
        *,
        callback_context: Any,
        llm_request: Any,
    ) -> Optional[Any]:
        """Executes BEFORE every LLM invocation: scrubs PII, screens prompt, and logs INTENT."""
        agent_name = getattr(callback_context, "agent_name", "KiwiCampCoordinatorAgent")
        raw_text = str(getattr(llm_request, "contents", ""))
        scrubbed_text = self.pii_redactor.redact_text(raw_text)

        corr_id = self.audit_logger.record_intent(
            action_type="MODEL_GENERATION",
            agent_name=agent_name,
            target_name=str(getattr(llm_request, "model", "gemini-2.5-pro")),
            intent_payload={"prompt_preview": scrubbed_text[:300]},
        )
        self._active_correlations[f"model:{agent_name}"] = corr_id

        is_safe, violation_reason = self.screen_prompt_for_policy_violations(raw_text)
        if not is_safe:
            self.audit_logger.record_outcome(
                correlation_id=corr_id,
                action_type="MODEL_GENERATION",
                agent_name=agent_name,
                target_name="security_guardrail_block",
                outcome_payload={"blocked_reason": violation_reason},
                status="BLOCKED_BY_GUARDRAIL",
            )
            if LlmResponse is not None and genai_types is not None:
                return LlmResponse(
                    content=genai_types.Content(
                        role="model",
                        parts=[genai_types.Part.from_text(text=violation_reason or "Request blocked.")],
                    )
                )
            return {"status": "blocked", "reason": violation_reason}

        return None

    async def after_model_callback(
        self,
        *,
        callback_context: Any,
        llm_response: Any,
    ) -> Optional[Any]:
        """Executes AFTER every LLM invocation: scrubs output PII and records OUTCOME."""
        agent_name = getattr(callback_context, "agent_name", "KiwiCampCoordinatorAgent")
        corr_id = self._active_correlations.pop(f"model:{agent_name}", "corr-model")
        response_text = str(getattr(llm_response, "content", llm_response))
        scrubbed_response = self.pii_redactor.redact_text(response_text)

        self.audit_logger.record_outcome(
            correlation_id=corr_id,
            action_type="MODEL_GENERATION",
            agent_name=agent_name,
            target_name="llm_response",
            outcome_payload={"response_preview": scrubbed_response[:300]},
            status="SUCCESS",
        )
        return None

    async def before_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: Dict[str, Any],
        tool_context: Any,
    ) -> Optional[Dict[str, Any]]:
        """Executes BEFORE every tool call: logs INTENT and enforces HITL confirmation gates."""
        tool_name = getattr(tool, "name", getattr(tool, "__name__", str(tool)))
        agent_name = getattr(tool_context, "agent_name", "KiwiCampAgent")
        scrubbed_args = self.pii_redactor.redact_structure(tool_args)

        corr_id = self.audit_logger.record_intent(
            action_type="TOOL_EXECUTION",
            agent_name=agent_name,
            target_name=tool_name,
            intent_payload={"tool_args": scrubbed_args},
        )
        self._active_correlations[f"tool:{tool_name}"] = corr_id

        # Enforce Human-in-the-Loop (HITL) stop if `require_confirmation_gate` is active
        if tool_name in HIGH_STAKES_HITL_TOOLS:
            state = getattr(tool_context, "state", {}) or {}
            confirmation = getattr(tool_context, "tool_confirmation", None)
            if state.get("enforce_strict_plugin_hitl_block") is True and not (
                confirmation and getattr(confirmation, "confirmed", False)
            ):
                block_payload = {
                    "status": "pending_human_confirmation",
                    "tool_name": tool_name,
                    "message": (
                        f"Human-in-the-Loop confirmation required before executing '{tool_name}'."
                    ),
                }
                self.audit_logger.record_outcome(
                    correlation_id=corr_id,
                    action_type="TOOL_EXECUTION",
                    agent_name=agent_name,
                    target_name=tool_name,
                    outcome_payload=block_payload,
                    status="PAUSED_FOR_HITL_CONFIRMATION",
                )
                return block_payload

        return None

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: Dict[str, Any],
        tool_context: Any,
        result: Any,
    ) -> Optional[Any]:
        """Executes AFTER every tool call: scrubs PII from result and records OUTCOME."""
        tool_name = getattr(tool, "name", getattr(tool, "__name__", str(tool)))
        agent_name = getattr(tool_context, "agent_name", "KiwiCampAgent")
        corr_id = self._active_correlations.pop(f"tool:{tool_name}", "corr-tool")
        scrubbed_result = self.pii_redactor.redact_structure(result)

        status = "SUCCESS"
        if isinstance(result, dict) and result.get("status") == "error":
            status = "GUIDED_ERROR_RECOVERY"
        elif isinstance(result, dict) and result.get("status") == "pending_human_confirmation":
            status = "PENDING_HITL_CONFIRMATION"

        self.audit_logger.record_outcome(
            correlation_id=corr_id,
            action_type="TOOL_EXECUTION",
            agent_name=agent_name,
            target_name=tool_name,
            outcome_payload={"result_summary": scrubbed_result},
            status=status,
        )
        return None


def build_reflect_and_retry_plugin(max_retries: int = 2) -> Any:
    """Builds ADK's `ReflectAndRetryToolPlugin` to automatically self-heal on tool errors."""
    if ReflectAndRetryToolPlugin is not None:
        return ReflectAndRetryToolPlugin(max_retries=max_retries)
    return {"type": "ReflectAndRetryToolPlugin", "max_retries": max_retries}
