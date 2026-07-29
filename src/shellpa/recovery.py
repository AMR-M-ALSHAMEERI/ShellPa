"""Build privacy-conscious context for command recovery."""

from __future__ import annotations

import re
from pathlib import Path

from .executor import result_error_message
from .models import ExecutionRequest, ExecutionResult, RecoveryContext

SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN|SECRET|PASSWORD))\s*=\s*"
        r"([^\s;&]+)"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|"
        r"github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9_-]{8,})\b"
    ),
    re.compile(r"(https?://[^/\s:@]+:)[^@\s/]+@"),
)


def redact_sensitive_text(text: str) -> str:
    """Redact common secret shapes without destroying diagnostic structure."""
    redacted = text
    redacted = SECRET_PATTERNS[0].sub(
        lambda match: f"{match.group(1)}=<REDACTED>", redacted
    )
    redacted = SECRET_PATTERNS[1].sub("Bearer <REDACTED>", redacted)
    redacted = SECRET_PATTERNS[2].sub("<REDACTED_TOKEN>", redacted)
    redacted = SECRET_PATTERNS[3].sub(r"\1<REDACTED>@", redacted)

    home = str(Path.home())
    if home:
        redacted = redacted.replace(home, "~")
        redacted = redacted.replace(home.replace("\\", "/"), "~")
    return redacted


def build_recovery_context(
    original_query: str,
    request: ExecutionRequest,
    result: ExecutionResult,
) -> RecoveryContext:
    """Create redacted, structured facts for a correction request."""
    return RecoveryContext(
        original_query=original_query,
        failed_command=request.command,
        error_message=redact_sensitive_text(result_error_message(result)),
        exit_code=result.exit_code,
        working_directory=request.working_directory,
        attempt=request.attempt,
        timed_out=result.timed_out,
        cancelled=result.cancelled,
        output_truncated=result.output_truncated,
        partial_effect_possible=result.partial_effect_possible,
    )
