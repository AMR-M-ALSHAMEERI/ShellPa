"""Privacy-safe local event logging for troubleshooting ShellPa sessions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from .recovery import redact_sensitive_text

LOGGING_ENV = "SHELLPA_LOGGING"
DEFAULT_LOG_PATH = Path.home() / ".shellpa" / "logs" / "shellpa.jsonl"
DISABLED_VALUES = {"0", "false", "no", "off"}
FORBIDDEN_FIELDS = {
    "api_key",
    "command",
    "credential",
    "env",
    "query",
    "stderr",
    "stdout",
    "token",
}
EVENT_FIELDS = {
    "session_start": {"version", "provider", "model", "os", "shell", "mode"},
    "generation_completed": {"attempt", "recovery", "duration_ms"},
    "risk_assessed": {
        "risk_level",
        "matched_policy_rules",
        "requires_network",
        "requires_privilege",
    },
    "execution_completed": {
        "success",
        "exit_code",
        "duration_ms",
        "timed_out",
        "cancelled",
        "output_truncated",
        "partial_effect_possible",
    },
    "session_end": {"outcome"},
}


def logging_enabled(environ: dict[str, str] | None = None) -> bool:
    """Return whether local metadata logging is enabled."""
    values = os.environ if environ is None else environ
    return values.get(LOGGING_ENV, "1").strip().lower() not in DISABLED_VALUES


def _safe_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    return redact_sensitive_text(str(value))


class SessionLogger:
    """Append allowlisted, secret-free session metadata as JSON Lines."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        enabled: bool | None = None,
    ) -> None:
        self.path = path or DEFAULT_LOG_PATH
        self.enabled = logging_enabled() if enabled is None else enabled
        self.session_id = uuid4().hex
        self.last_error: OSError | None = None

    def emit(self, event: str, **fields: Any) -> bool:
        """Write one event; logging errors never interrupt the CLI."""
        if not self.enabled or event not in EVENT_FIELDS:
            return False

        permitted = EVENT_FIELDS[event]
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "session_id": self.session_id,
        }
        payload.update(
            {
                key: _safe_value(value)
                for key, value in fields.items()
                if key in permitted and key.lower() not in FORBIDDEN_FIELDS
            }
        )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError as error:
            self.last_error = error
            return False
        return True
