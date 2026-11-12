"""Active PII Redaction Pipeline via Cloud DLP + Regex Scrubbers (Criterion 4.4).

Scrubs Personally Identifiable Information (emails, phone numbers, credit cards,
passport numbers, New Zealand driver licenses) before any data reaches structured
logs, session storage, or Vertex AI Memory Bank.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from google.cloud import dlp_v2
except ImportError:  # pragma: no cover - graceful offline fallback
    dlp_v2 = None  # type: ignore[assignment]


# Deterministic regex patterns covering international & NZ-specific PII formats
PII_REGEX_RULES: Tuple[Tuple[str, re.Pattern[str], str], ...] = (
    (
        "EMAIL_ADDRESS",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "CREDIT_CARD_NUMBER",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        "[REDACTED_PAYMENT_CARD]",
    ),
    (
        "PHONE_NUMBER",
        re.compile(
            r"(?:(?:\+?64|0)[ -]?(?:2\d|3|4|6|7|9)[ -]?\d{3}[ -]?\d{3,4})"
            r"|(?:\+?1[ -]?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4})"
        ),
        "[REDACTED_PHONE]",
    ),
    (
        "NZ_DRIVER_LICENSE",
        re.compile(r"\b(?:NZDL[-:\s]*)?[A-Z]{2}\d{6}\b"),
        "[REDACTED_NZ_DRIVER_LICENSE]",
    ),
    (
        "PASSPORT_NUMBER",
        re.compile(r"\b(?:PASSPORT[-:\s#]*)[A-Z0-9]{7,9}\b", re.IGNORECASE),
        "[REDACTED_PASSPORT]",
    ),
)


@dataclass
class CloudDlpAndRegexPiiRedactor:
    """Two-stage PII redactor combining deterministic regex scrubbing and Cloud DLP.

    Stage 1 runs zero-latency deterministic regex scrubbers synchronously on every
    log record and memory payload. Stage 2 optionally invokes Google Cloud DLP
    (`google.cloud.dlp_v2.DlpServiceClient.deidentify_content`) when enabled in
    cloud environments for deep contextual entity inspection.
    """

    project_id: str = field(
        default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT", "kiwicamp-prod")
    )
    enable_cloud_dlp_rpc: bool = field(
        default_factory=lambda: os.environ.get("ENABLE_CLOUD_DLP_RPC", "false").lower()
        == "true"
    )
    info_types: List[str] = field(
        default_factory=lambda: [
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "CREDIT_CARD_NUMBER",
            "PASSPORT",
            "PERSON_NAME",
        ]
    )
    _dlp_client: Optional[object] = field(default=None, init=False, repr=False)

    def _get_dlp_client(self) -> Optional[object]:
        if self._dlp_client is None and dlp_v2 is not None and self.enable_cloud_dlp_rpc:
            try:
                self._dlp_client = dlp_v2.DlpServiceClient()
            except Exception:
                self._dlp_client = None
        return self._dlp_client

    def redact_text(self, text: str) -> str:
        """Scrubs sensitive PII tokens from a string."""
        if not text or not isinstance(text, str):
            return text

        scrubbed = text
        for _, pattern, replacement in PII_REGEX_RULES:
            scrubbed = pattern.sub(replacement, scrubbed)

        client = self._get_dlp_client()
        if client is not None:
            try:
                parent = f"projects/{self.project_id}/locations/global"
                inspect_config = {
                    "info_types": [{"name": t} for t in self.info_types],
                    "min_likelihood": "POSSIBLE",
                }
                deidentify_config = {
                    "info_type_transformations": {
                        "transformations": [
                            {
                                "primitive_transformation": {
                                    "replace_with_info_type_config": {}
                                }
                            }
                        ]
                    }
                }
                response = client.deidentify_content(
                    request={
                        "parent": parent,
                        "inspect_config": inspect_config,
                        "deidentify_config": deidentify_config,
                        "item": {"value": scrubbed},
                    }
                )
                if response and getattr(response, "item", None):
                    scrubbed = response.item.value
            except Exception:
                # Regex scrubbing already succeeded; never fail open on raw text
                pass

        return scrubbed

    def redact_structure(self, payload: Any) -> Any:
        """Recursively scrubs PII across dicts, lists, tuples, and strings."""
        if isinstance(payload, str):
            return self.redact_text(payload)
        if isinstance(payload, dict):
            return {
                str(k): self.redact_structure(v) for k, v in payload.items()
            }
        if isinstance(payload, list):
            return [self.redact_structure(item) for item in payload]
        if isinstance(payload, tuple):
            return tuple(self.redact_structure(item) for item in payload)
        return payload


class PiiRedactingLogFilter(logging.Filter):
    """Logging filter that scrubs PII from `record.msg`, `record.args`, and extras."""

    def __init__(self, redactor: Optional[CloudDlpAndRegexPiiRedactor] = None) -> None:
        super().__init__()
        self.redactor = redactor or CloudDlpAndRegexPiiRedactor()

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redactor.redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = self.redactor.redact_structure(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self.redactor.redact_structure(arg) for arg in record.args
                )

        for attr in ("intent_payload", "outcome_payload", "tool_args", "tool_result"):
            if hasattr(record, attr):
                setattr(
                    record,
                    attr,
                    self.redactor.redact_structure(getattr(record, attr)),
                )
        return True


_DEFAULT_REDACTOR = CloudDlpAndRegexPiiRedactor()


def redact_pii(payload: Any) -> Any:
    """Convenience function to scrub PII from strings or nested dicts/lists."""
    return _DEFAULT_REDACTOR.redact_structure(payload)
