"""Stable domain models shared by ShellPa's generation and execution layers."""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    """Risk categories used by the future deterministic safety engine."""

    READ_ONLY = "read_only"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ConfirmationRequirement(str, Enum):
    """The level of user authorization required before execution."""

    NONE = "none"
    STANDARD = "standard"
    TYPED = "typed"
    MANUAL_ONLY = "manual_only"


class PermissionMode(str, Enum):
    """How aggressively ShellPa may proceed without prompting."""

    ASK = "ask"
    PLAN = "plan"
    TRUSTED = "trusted"


class PermissionAction(str, Enum):
    """The concrete action ShellPa should take after policy evaluation."""

    AUTO_EXECUTE = "auto_execute"
    STANDARD_CONFIRM = "standard_confirm"
    TYPED_CONFIRM = "typed_confirm"
    PLAN_ONLY = "plan_only"
    BLOCK = "block"


class WorkspaceBoundarySource(str, Enum):
    """The evidence used to choose a workspace boundary."""

    GIT = "git"
    PROJECT_MARKER = "project_marker"
    CURRENT_DIRECTORY = "current_directory"


class ProjectType(str, Enum):
    """Project ecosystems recognizable from metadata marker names."""

    PYTHON = "python"
    NODE = "node"
    DOCKER = "docker"
    RUST = "rust"
    GO = "go"
    MAVEN = "maven"
    GRADLE = "gradle"


class PermissionDecision(BaseModel):
    """A mode-aware authorization decision for one assessed command."""

    action: PermissionAction
    reason: str
    confirmation_phrase: str | None = None


class CommandProposal(BaseModel):
    """A structured command proposed by an AI provider."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    command: str = Field(min_length=1, description="The shell command to execute.")
    explanation: str = Field(
        min_length=1,
        description="A brief explanation of what the command does.",
    )
    shell: str | None = None
    intended_working_directory: Path | None = None
    expected_effect: str | None = None
    recovery_notes: str | None = None


class RiskAssessment(BaseModel):
    """A deterministic safety decision for a proposed command."""

    risk_level: RiskLevel = RiskLevel.UNKNOWN
    reasons: list[str] = Field(default_factory=list)
    affected_targets: list[str] = Field(default_factory=list)
    is_reversible: bool | None = None
    requires_network: bool = False
    requires_privilege: bool = False
    required_confirmation: ConfirmationRequirement = ConfirmationRequirement.STANDARD
    matched_policy_rules: list[str] = Field(default_factory=list)


class ExecutionRequest(BaseModel):
    """The approved, normalized inputs needed to start a command."""

    model_config = ConfigDict(str_strip_whitespace=True)

    command: str = Field(min_length=1)
    operating_system: str = Field(min_length=1)
    shell: str = Field(min_length=1)
    working_directory: Path
    timeout_seconds: float | None = Field(default=None, gt=0)
    interactive: bool = False
    capture_limit_chars: int = Field(default=20_000, ge=1_000)
    environment_allowlist: set[str] = Field(default_factory=set)
    attempt: int = Field(default=1, ge=1)


class ExecutionResult(BaseModel):
    """A structured description of a completed or interrupted process."""

    success: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = Field(default=0.0, ge=0)
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False
    partial_effect_possible: bool = False


class RecoveryContext(BaseModel):
    """Redacted execution facts safe enough to send for command correction."""

    original_query: str
    failed_command: str
    error_message: str
    exit_code: int | None
    working_directory: Path
    attempt: int = Field(ge=1)
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False
    partial_effect_possible: bool = True


class WorkspaceContext(BaseModel):
    """Bounded, read-only metadata describing the active workspace."""

    root: Path
    current_directory: Path
    boundary_source: WorkspaceBoundarySource
    project_types: list[ProjectType] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
