"""Deterministic command-risk analysis and permission decisions."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .models import (
    ConfirmationRequirement,
    PermissionAction,
    PermissionDecision,
    PermissionMode,
    RiskAssessment,
    RiskLevel,
)


@dataclass(frozen=True)
class PolicyRule:
    """A deterministic pattern that contributes to command risk."""

    rule_id: str
    pattern: re.Pattern[str]
    risk_level: RiskLevel
    reason: str
    requires_network: bool = False
    requires_privilege: bool = False


def _rule(
    rule_id: str,
    pattern: str,
    risk_level: RiskLevel,
    reason: str,
    *,
    requires_network: bool = False,
    requires_privilege: bool = False,
) -> PolicyRule:
    return PolicyRule(
        rule_id=rule_id,
        pattern=re.compile(pattern, re.IGNORECASE | re.DOTALL),
        risk_level=risk_level,
        reason=reason,
        requires_network=requires_network,
        requires_privilege=requires_privilege,
    )


POLICY_RULES = (
    _rule(
        "high.sensitive-file-access",
        r"(?<![\w.-])(?:\.shellpa\.env|\.env(?!\.example)(?:\.[\w-]+)?|"
        r"credentials\.json|auth\.json|\.pypirc|\.npmrc|id_rsa|id_ed25519)"
        r"(?![\w.-])",
        RiskLevel.HIGH,
        "The command references a file that commonly contains credentials or secrets.",
    ),
    _rule(
        "critical.disk-management",
        r"\b(?:format-volume|clear-disk|initialize-disk|diskpart|wipefs|"
        r"mkfs(?:\.\w+)?|fdisk|parted)\b|"
        r"\bformat(?:\.com)?\s+[a-z]:|"
        r"\bdd\b[^\r\n]*\bof=/dev/",
        RiskLevel.CRITICAL,
        "The command can format, repartition, or overwrite a storage device.",
    ),
    _rule(
        "critical.boot-configuration",
        r"\b(?:bcdedit|bootrec)\b",
        RiskLevel.CRITICAL,
        "The command can modify system boot configuration.",
        requires_privilege=True,
    ),
    _rule(
        "high.remote-code-pipe",
        r"\b(?:curl|wget|invoke-webrequest|iwr)\b[^\r\n]*\|\s*"
        r"(?:sh|bash|zsh|powershell|pwsh|iex|invoke-expression)\b",
        RiskLevel.HIGH,
        "Downloaded content is piped directly into a command interpreter.",
        requires_network=True,
    ),
    _rule(
        "high.dynamic-evaluation",
        r"\b(?:invoke-expression|iex|eval)\b",
        RiskLevel.HIGH,
        "The command dynamically evaluates text as executable code.",
    ),
    _rule(
        "high.privilege-escalation",
        r"(^|[;&|]\s*)(?:sudo|runas)\b|"
        r"\bstart-process\b[^\r\n]*\s-verb\s+runas\b",
        RiskLevel.HIGH,
        "The command requests elevated operating-system privileges.",
        requires_privilege=True,
    ),
    _rule(
        "high.git-force",
        r"\bgit\s+(?:push\b[^\r\n]*(?:--force(?:-with-lease)?|-f)\b|"
        r"reset\s+--hard\b|clean\s+-[a-z]*f[a-z]*\b)",
        RiskLevel.HIGH,
        "The Git operation can discard work or rewrite shared history.",
    ),
    _rule(
        "high.registry-delete",
        r"\breg(?:\.exe)?\s+delete\b|"
        r"\bremove-item\b[^\r\n]*\bhklm:",
        RiskLevel.HIGH,
        "The command deletes Windows registry state.",
        requires_privilege=True,
    ),
    _rule(
        "high.recursive-delete-posix",
        r"(^|[;&|]\s*)rm\s+(?:[^\r\n;&|]*\s)?-[a-z]*r[a-z]*f?[a-z]*\b|"
        r"(^|[;&|]\s*)rm\s+(?:[^\r\n;&|]*\s)?-[a-z]*f[a-z]*r[a-z]*\b",
        RiskLevel.HIGH,
        "The command recursively deletes filesystem content.",
    ),
    _rule(
        "high.recursive-delete-powershell",
        r"\b(?:remove-item|ri)\b[^\r\n;&|]*\s-(?:recurse|r)\b",
        RiskLevel.HIGH,
        "The command recursively deletes filesystem content.",
    ),
    _rule(
        "high.recursive-delete-cmd",
        r"(^|[;&|]\s*)(?:rmdir|rd)\s+[^\r\n;&|]*/s\b|"
        r"(^|[;&|]\s*)del\s+[^\r\n;&|]*/s\b",
        RiskLevel.HIGH,
        "The command recursively deletes filesystem content.",
    ),
    _rule(
        "high.recursive-permissions",
        r"(^|[;&|]\s*)(?:chmod|chown)\s+-[a-z]*r\b",
        RiskLevel.HIGH,
        "The command recursively changes filesystem ownership or permissions.",
        requires_privilege=True,
    ),
    _rule(
        "high.bulk-find-delete",
        r"(^|[;&|]\s*)find\b[^\r\n;&|]*\s-delete\b",
        RiskLevel.HIGH,
        "The command can delete many filesystem entries selected by a search.",
    ),
    _rule(
        "high.find-exec",
        r"(^|[;&|]\s*)find\b[^\r\n;&|]*\s-(?:exec|execdir|ok)\b",
        RiskLevel.HIGH,
        "The search command can execute another command for every matched path.",
    ),
    _rule(
        "high.system-power",
        r"(^|[;&|]\s*)(?:shutdown|reboot|restart-computer|stop-computer)\b",
        RiskLevel.HIGH,
        "The command can stop or restart the operating system.",
        requires_privilege=True,
    ),
    _rule(
        "high.encoded-command",
        r"\b(?:powershell|pwsh)\b[^\r\n]*\s-(?:encodedcommand|enc)\b",
        RiskLevel.HIGH,
        "The command hides executable instructions inside encoded content.",
    ),
    _rule(
        "normal.filesystem-change",
        r"(^|[;&|]\s*)(?:new-item|set-content|add-content|clear-content|"
        r"copy-item|move-item|remove-item|mkdir|md|touch|cp|mv|rm|del|"
        r"erase|rmdir|rd)\b",
        RiskLevel.NORMAL,
        "The command can change filesystem content.",
    ),
    _rule(
        "normal.package-change",
        r"(^|[;&|]\s*)(?:pip|pip3|python\s+-m\s+pip|py\s+-m\s+pip)\s+"
        r"(?:install|uninstall)\b|"
        r"(^|[;&|]\s*)(?:npm|pnpm|yarn|bun)\s+(?:install|add|remove)\b",
        RiskLevel.NORMAL,
        "The command changes installed dependencies.",
        requires_network=True,
    ),
    _rule(
        "normal.git-change",
        r"\bgit\s+(?:add|commit|merge|rebase|checkout|switch|restore|"
        r"pull|push|tag|branch\s+-(?:d|D|m|M)|"
        r"remote\s+(?:add|remove|rename|set-url))\b",
        RiskLevel.NORMAL,
        "The command changes repository state or communicates with a remote.",
    ),
    _rule(
        "normal.output-redirection",
        r"(?<![<>&])>{1,2}(?!&)",
        RiskLevel.NORMAL,
        "Shell output redirection can create or overwrite a file.",
    ),
)


READ_ONLY_COMMANDS = {
    "cat",
    "dir",
    "echo",
    "find",
    "get-childitem",
    "gci",
    "get-command",
    "get-content",
    "get-date",
    "get-item",
    "get-location",
    "get-process",
    "grep",
    "head",
    "ls",
    "measure-object",
    "pwd",
    "resolve-path",
    "rg",
    "select-string",
    "select-object",
    "sort-object",
    "tail",
    "test-path",
    "type",
    "where",
    "where.exe",
    "where-object",
    "which",
    "write-host",
    "write-output",
}

READ_ONLY_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "log",
    "show",
    "blame",
    "rev-parse",
    "ls-files",
    "ls-tree",
}

FILE_TARGET_COMMANDS = {
    "add-content",
    "clear-content",
    "copy-item",
    "cp",
    "del",
    "erase",
    "md",
    "mkdir",
    "move-item",
    "mv",
    "new-item",
    "rd",
    "remove-item",
    "ri",
    "rm",
    "rmdir",
    "set-content",
    "touch",
}

PATH_PARAMETER_NAMES = {
    "-destination",
    "-literalpath",
    "-path",
    "-source",
}

IGNORED_CMD_SWITCHES = {"/f", "/q", "/s"}
NETWORK_PATTERN = re.compile(
    r"\b(?:curl|wget|invoke-webrequest|iwr|git\s+(?:fetch|pull|push)|"
    r"pip(?:3)?\s+install|npm\s+(?:install|add))\b",
    re.IGNORECASE,
)
PRIVILEGE_PATTERN = re.compile(
    r"(^|[;&|]\s*)(?:sudo|runas)\b|"
    r"\bstart-process\b[^\r\n]*\s-verb\s+runas\b",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r'"[^"]*"|\'[^\']*\'|[^\s]+')
ABSOLUTE_OR_EXPLICIT_PATH_PATTERN = re.compile(
    r'"([^"]+)"|\'([^\']+)\'|'
    r"((?:(?<![A-Za-z0-9])[a-zA-Z]:[\\/]|\\\\|\.{1,2}[\\/]|"
    r"~[\\/]|/)[^\s;&|]*)"
)

RISK_PRIORITY = {
    RiskLevel.READ_ONLY: 0,
    RiskLevel.UNKNOWN: 1,
    RiskLevel.NORMAL: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


def _highest_risk(current: RiskLevel, candidate: RiskLevel) -> RiskLevel:
    return candidate if RISK_PRIORITY[candidate] > RISK_PRIORITY[current] else current


def _strip_token(token: str) -> str:
    return token.strip().strip("\"'").rstrip(",;")


def _expand_windows_variables(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), match.group(0))

    expanded = re.sub(r"%([^%]+)%", replace, value)
    expanded = re.sub(
        r"\$env:([A-Za-z_][A-Za-z0-9_]*)",
        lambda match: os.environ.get(match.group(1), match.group(0)),
        expanded,
        flags=re.IGNORECASE,
    )
    return os.path.expandvars(os.path.expanduser(expanded))


def _looks_like_target(value: str) -> bool:
    lowered = value.lower()
    if not value or lowered in IGNORED_CMD_SWITCHES:
        return False
    if lowered.startswith(("http://", "https://")):
        return False
    if value.startswith("-"):
        return False
    if value in {"|", "&&", "||", ";"} or ">&" in value:
        return False
    return True


def _resolve_target(value: str, cwd: Path) -> str:
    expanded = _expand_windows_variables(_strip_token(value))
    if re.match(r"^[a-zA-Z]:[\\/]", expanded) or expanded.startswith("\\\\"):
        if os.name == "nt":
            return str(Path(expanded).resolve(strict=False))
        return str(PureWindowsPath(expanded))
    if expanded.startswith("/"):
        return str(PurePosixPath(expanded))
    if re.match(r"^[A-Za-z]+:\\", expanded):
        return expanded
    return str((cwd / expanded).resolve(strict=False))


def _extract_targets(command: str, cwd: Path) -> list[str]:
    candidates: list[str] = []

    for match in ABSOLUTE_OR_EXPLICIT_PATH_PATTERN.finditer(command):
        value = next((group for group in match.groups() if group is not None), "")
        prefix = command[max(0, match.start() - 8) : match.start()].lower()
        if re.search(r"https?:/?$", prefix):
            continue
        if _looks_like_target(value):
            candidates.append(value)

    for segment in re.split(r"(?:&&|\|\||[;&|])", command):
        tokens = [_strip_token(token) for token in TOKEN_PATTERN.findall(segment)]
        lowered = [token.lower() for token in tokens]
        command_index = next(
            (
                index
                for index, token in enumerate(lowered)
                if token in FILE_TARGET_COMMANDS
            ),
            None,
        )
        if command_index is None:
            continue

        command_name = lowered[command_index]
        positional_limit = (
            2
            if command_name
            in {
                "copy-item",
                "cp",
                "move-item",
                "mv",
            }
            else 1
        )
        positional_count = 0
        expect_path = False
        for token in tokens[command_index + 1 :]:
            lowered_token = token.lower()
            if lowered_token in PATH_PARAMETER_NAMES:
                expect_path = True
                continue
            if token.startswith("-") or lowered_token in IGNORED_CMD_SWITCHES:
                continue
            if expect_path:
                candidates.append(token)
                expect_path = False
                continue
            if positional_count < positional_limit and _looks_like_target(token):
                candidates.append(token)
                positional_count += 1

    resolved: list[str] = []
    for candidate in candidates:
        try:
            target = _resolve_target(candidate, cwd)
        except (OSError, RuntimeError, ValueError):
            target = _strip_token(candidate)
        if target and target not in resolved:
            resolved.append(target)
    return resolved


def _canonical_for_policy(value: str) -> str:
    return value.strip().strip("\"'").replace("\\", "/").rstrip("/").lower()


def _is_root_target(value: str) -> bool:
    stripped = value.strip().strip("\"'").replace("\\", "/")
    return bool(
        stripped == "/"
        or re.fullmatch(r"/\*+", stripped)
        or re.fullmatch(r"[a-zA-Z]:/?", stripped)
        or re.fullmatch(r"[a-zA-Z]:/\*+", stripped)
    )


def _is_within(value: str, parent: str) -> bool:
    return value == parent or value.startswith(parent + "/")


def _protected_target_reason(
    target: str,
    cwd: Path,
    *,
    broad_destructive: bool,
) -> str | None:
    canonical = _canonical_for_policy(target)
    canonical_cwd = _canonical_for_policy(str(cwd.resolve(strict=False)))
    canonical_home = _canonical_for_policy(str(Path.home().resolve(strict=False)))

    if broad_destructive and _is_root_target(target):
        return "The command targets a filesystem or drive root."
    if broad_destructive and canonical == canonical_cwd:
        return "The command targets the entire active workspace."
    if broad_destructive and canonical == canonical_home:
        return "The command targets the entire user home directory."
    if _is_within(canonical, canonical_cwd + "/.git"):
        return "The command targets protected Git repository metadata."

    protected_prefixes = (
        "c:/windows",
        "c:/program files",
        "c:/program files (x86)",
        "c:/programdata",
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/proc",
        "/sbin",
        "/sys",
        "/usr",
    )
    for prefix in protected_prefixes:
        if _is_within(canonical, prefix):
            return f"The command targets protected system path {target}."
    return None


def _is_recursive_destructive(command: str) -> bool:
    return any(
        rule.rule_id.startswith("high.recursive-delete")
        and rule.pattern.search(command)
        for rule in POLICY_RULES
    )


def _is_read_only(command: str) -> bool:
    if re.search(r"\$\(|`|\b(?:eval|invoke-expression|iex)\b", command, re.IGNORECASE):
        return False
    if re.search(r"(?<![<>&])>{1,2}(?!&)", command):
        return False

    segments = [
        segment.strip()
        for segment in re.split(r"(?:&&|\|\||[;&|])", command)
        if segment.strip()
    ]
    if not segments:
        return False

    for segment in segments:
        tokens = [
            _strip_token(token).lower() for token in TOKEN_PATTERN.findall(segment)
        ]
        if not tokens:
            continue
        executable = tokens[0]
        if executable == "git":
            if len(tokens) < 2 or tokens[1] not in READ_ONLY_GIT_SUBCOMMANDS:
                return False
            continue
        if executable in {"python", "python3", "py"}:
            if tokens[1:3] == ["-m", "pip"]:
                if len(tokens) < 4 or tokens[3] not in {
                    "check",
                    "list",
                    "show",
                    "freeze",
                }:
                    return False
                continue
            if len(tokens) == 2 and tokens[1] in {"--version", "-v"}:
                continue
            return False
        if executable not in READ_ONLY_COMMANDS:
            return False
    return True


def assess_command(command: str, cwd: Path | None = None) -> RiskAssessment:
    """Evaluate one shell command with deterministic local policy."""
    active_cwd = (cwd or Path.cwd()).resolve(strict=False)
    risk_level = RiskLevel.UNKNOWN
    reasons: list[str] = []
    matched_rules: list[str] = []
    requires_network = bool(NETWORK_PATTERN.search(command))
    requires_privilege = bool(PRIVILEGE_PATTERN.search(command))

    for rule in POLICY_RULES:
        if not rule.pattern.search(command):
            continue
        risk_level = _highest_risk(risk_level, rule.risk_level)
        if rule.reason not in reasons:
            reasons.append(rule.reason)
        matched_rules.append(rule.rule_id)
        requires_network = requires_network or rule.requires_network
        requires_privilege = requires_privilege or rule.requires_privilege

    affected_targets = _extract_targets(command, active_cwd)
    recursive_destructive = _is_recursive_destructive(command)
    destructive = recursive_destructive or any(
        rule_id
        in {
            "normal.filesystem-change",
            "high.registry-delete",
            "critical.disk-management",
        }
        for rule_id in matched_rules
    )

    if destructive:
        for target in affected_targets:
            protected_reason = _protected_target_reason(
                target,
                active_cwd,
                broad_destructive=recursive_destructive
                or bool(
                    re.search(
                        r"\b(?:remove-item|ri|rm|del|erase|rmdir|rd|clear-content)\b",
                        command,
                        re.IGNORECASE,
                    )
                ),
            )
            if protected_reason:
                risk_level = RiskLevel.CRITICAL
                if protected_reason not in reasons:
                    reasons.append(protected_reason)
                matched_rules.append("critical.protected-target")

    if not matched_rules and _is_read_only(command):
        risk_level = RiskLevel.READ_ONLY
        reasons.append("The command matches the known read-only command set.")
        matched_rules.append("readonly.known-command")

    if risk_level is RiskLevel.UNKNOWN:
        reasons.append(
            "No deterministic rule proves this command is read-only or classifies its effects."
        )

    confirmation = {
        RiskLevel.READ_ONLY: ConfirmationRequirement.STANDARD,
        RiskLevel.NORMAL: ConfirmationRequirement.STANDARD,
        RiskLevel.UNKNOWN: ConfirmationRequirement.STANDARD,
        RiskLevel.HIGH: ConfirmationRequirement.TYPED,
        RiskLevel.CRITICAL: ConfirmationRequirement.MANUAL_ONLY,
    }[risk_level]

    return RiskAssessment(
        risk_level=risk_level,
        reasons=reasons,
        affected_targets=affected_targets,
        is_reversible=True
        if risk_level is RiskLevel.READ_ONLY
        else (False if risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} else None),
        requires_network=requires_network,
        requires_privilege=requires_privilege,
        required_confirmation=confirmation,
        matched_policy_rules=list(dict.fromkeys(matched_rules)),
    )


def build_confirmation_phrase(assessment: RiskAssessment) -> str:
    """Build a target-specific phrase for a high-risk approval."""
    if assessment.affected_targets:
        return f"CONFIRM {assessment.affected_targets[0]}"
    return "CONFIRM HIGH RISK"


def decide_permission(
    assessment: RiskAssessment,
    mode: PermissionMode,
    *,
    force: bool,
) -> PermissionDecision:
    """Apply the active interaction mode without weakening safety policy."""
    if mode is PermissionMode.PLAN:
        return PermissionDecision(
            action=PermissionAction.PLAN_ONLY,
            reason="Plan mode never executes commands.",
        )
    if assessment.required_confirmation is ConfirmationRequirement.MANUAL_ONLY:
        return PermissionDecision(
            action=PermissionAction.BLOCK,
            reason="Critical commands are manual-only and cannot run through ShellPa.",
        )
    if assessment.required_confirmation is ConfirmationRequirement.TYPED:
        return PermissionDecision(
            action=PermissionAction.TYPED_CONFIRM,
            reason="High-risk commands require explicit typed confirmation.",
            confirmation_phrase=build_confirmation_phrase(assessment),
        )
    if force and assessment.risk_level in {RiskLevel.READ_ONLY, RiskLevel.NORMAL}:
        return PermissionDecision(
            action=PermissionAction.AUTO_EXECUTE,
            reason="Force mode may skip approval only for known read-only or normal commands.",
        )
    if mode is PermissionMode.TRUSTED and assessment.risk_level is RiskLevel.READ_ONLY:
        return PermissionDecision(
            action=PermissionAction.AUTO_EXECUTE,
            reason="Trusted mode auto-runs only commands proven read-only.",
        )
    return PermissionDecision(
        action=PermissionAction.STANDARD_CONFIRM,
        reason=(
            "Unknown commands still require approval."
            if assessment.risk_level is RiskLevel.UNKNOWN
            else "This command requires standard user approval."
        ),
    )
