from pathlib import Path
from time import monotonic

import questionary
import typer
from rich.console import Console
from typer.core import TyperGroup

from . import __version__
from .about import AboutAction, run_about_menu
from .activity import (
    ActivityState,
    ExecutionActivity,
    activity_status,
    run_first_time_onboarding,
    select_standard_approval,
)
from .codex_auth import login_codex_interactively, logout_codex_interactively
from .config import load_config
from .diagnostics import display_doctor, run_doctor
from .event_log import SessionLogger
from .executor import execute_command, result_error_message
from .llm import generate_command, generate_recovery_command
from .models import (
    ExecutionRequest,
    PermissionAction,
    PermissionMode,
    RecoveryContext,
    RiskAssessment,
    WorkspaceContext,
)
from .os_detect import detect_environment
from .recovery import build_recovery_context
from .repl import InteractiveState, run_interactive_session
from .safety import assess_command, decide_permission
from .setup import run_setup_wizard
from .ux import (
    UXSettings,
    display_execution_failure,
    display_execution_result,
    display_proposal_review,
    display_recovery_heading,
    display_session_greeting,
    load_ux_settings,
    play_startup_reveal,
    questionary_style,
)
from .workspace import detect_workspace, format_provider_workspace_summary
from .workspace_ui import display_workspace_context, display_workspace_identity


class NaturalLanguageGroup(TyperGroup):
    """Route unknown first words to `run` for backward-compatible queries."""

    def get_command(self, ctx, cmd_name):
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        fallback = super().get_command(ctx, "run")
        if fallback is not None:
            ctx.meta["shellpa_query_head"] = cmd_name
        return fallback


app = typer.Typer(
    name="shellpa",
    cls=NaturalLanguageGroup,
    help="ShellPa: A cross-platform CLI Agent for natural language system execution.",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


def request_execution_permission(
    action: PermissionAction,
    assessment: RiskAssessment,
    confirmation_phrase: str | None,
    *,
    force: bool,
    ux_settings: UXSettings | None = None,
) -> bool:
    """Collect the authorization required by a permission decision."""
    prompt_theme = questionary_style(ux_settings or UXSettings())
    if action is PermissionAction.AUTO_EXECUTE:
        if force:
            console.print(
                "[bold yellow]--force accepted for this known "
                f"{assessment.risk_level.value} command.[/bold yellow]"
            )
        else:
            console.print("[dim]Trusted mode: known read-only command approved.[/dim]")
        return True

    if action is PermissionAction.TYPED_CONFIRM:
        phrase = confirmation_phrase or "CONFIRM HIGH RISK"
        console.print(
            "[bold red]High-risk operation. Review every target before continuing.[/bold red]"
        )
        answer = questionary.text(
            f"Type exactly: {phrase}",
            qmark="ShellPa ",
            style=prompt_theme,
        ).ask()
        return bool(answer is not None and answer.strip() == phrase)

    if console.is_terminal:
        return select_standard_approval(ux_settings or UXSettings())

    return bool(
        questionary.confirm(
            "Do you want to execute this command?",
            qmark="ShellPa ",
            style=prompt_theme,
            default=False,
        ).ask()
    )


def process_query(
    query: str,
    env_info: dict,
    force: bool,
    dry_run: bool,
    mode: PermissionMode = PermissionMode.ASK,
    timeout_seconds: float | None = None,
    passthrough: bool = False,
    ux_settings: UXSettings | None = None,
    event_logger: SessionLogger | None = None,
    workspace_context: WorkspaceContext | None = None,
):
    """Processes a single intent-to-command operation natively with Auto-Recovery."""
    active_settings = ux_settings or UXSettings()
    workspace_summary = (
        format_provider_workspace_summary(workspace_context)
        if workspace_context is not None
        else None
    )
    is_recovery = False
    recovery_context: RecoveryContext | None = None
    max_attempts = 4  # Initial try + 3 retries

    for attempt in range(max_attempts):
        activity_state = (
            ActivityState.RECOVERING if is_recovery else ActivityState.GENERATING
        )
        generation_started = monotonic()
        with activity_status(console, activity_state, active_settings):
            try:
                if is_recovery:
                    if recovery_context is None:
                        raise RuntimeError("Recovery context is unavailable.")
                    response = generate_recovery_command(
                        recovery_context,
                        env_info,
                        workspace_summary,
                    )
                else:
                    response = generate_command(query, env_info, workspace_summary)
            except Exception as e:
                console.print(f"[bold red]Failed to generate command:[/] {e}")
                raise typer.Exit(code=1) from e
        if event_logger is not None:
            event_logger.emit(
                "generation_completed",
                attempt=attempt + 1,
                recovery=is_recovery,
                duration_ms=round((monotonic() - generation_started) * 1000),
            )

        proposed_command = response.command

        if not is_recovery:
            console.print(
                f"[bold magenta]Detected Environment:[/bold magenta] {env_info['os']} ({env_info['shell']})\n"
            )
        else:
            display_recovery_heading(
                console,
                attempt,
                max_attempts - 1,
                active_settings,
            )

        with activity_status(
            console,
            ActivityState.REVIEWING,
            active_settings,
        ):
            assessment = assess_command(proposed_command, Path.cwd())
        if event_logger is not None:
            event_logger.emit(
                "risk_assessed",
                risk_level=assessment.risk_level,
                matched_policy_rules=assessment.matched_policy_rules,
                requires_network=assessment.requires_network,
                requires_privilege=assessment.requires_privilege,
            )
        display_proposal_review(
            console,
            response,
            assessment,
            env_info["shell"],
            active_settings,
        )
        active_mode = PermissionMode.PLAN if dry_run else mode
        decision = decide_permission(assessment, active_mode, force=force)

        if decision.action is PermissionAction.PLAN_ONLY:
            label = "Dry-run" if dry_run else "Plan"
            console.print(
                f"[yellow]{label} mode active. Exiting without execution.[/yellow]"
            )
            return

        if decision.action is PermissionAction.BLOCK:
            console.print(
                "[bold red]Manual-only operation:[/bold red] "
                f"{decision.reason}\n"
                "[yellow]ShellPa will not execute this command. "
                "If you still intend to run it, copy it and execute it directly "
                "after independent review.[/yellow]"
            )
            return

        execute = request_execution_permission(
            decision.action,
            assessment,
            decision.confirmation_phrase,
            force=force,
            ux_settings=active_settings,
        )

        if execute:
            request = ExecutionRequest(
                command=proposed_command,
                operating_system=env_info["os"],
                shell=env_info["shell"],
                working_directory=Path.cwd(),
                timeout_seconds=timeout_seconds,
                interactive=passthrough,
                attempt=attempt + 1,
            )
            result = execute_command(
                request,
                observer=ExecutionActivity(console, active_settings),
            )
            if event_logger is not None:
                event_logger.emit(
                    "execution_completed",
                    success=result.success,
                    exit_code=result.exit_code,
                    duration_ms=round(result.duration_seconds * 1000),
                    timed_out=result.timed_out,
                    cancelled=result.cancelled,
                    output_truncated=result.output_truncated,
                    partial_effect_possible=result.partial_effect_possible,
                )

            if result.success:
                display_execution_result(console, result, active_settings)
                return

            output_err = result_error_message(result)
            display_execution_failure(
                console,
                result,
                output_err,
                active_settings,
            )

            if result.cancelled:
                console.print(
                    "[yellow]Recovery skipped because execution was cancelled.[/yellow]"
                )
                return
            if result.timed_out:
                timeout_label = (
                    f"{timeout_seconds:g}-second"
                    if timeout_seconds is not None
                    else "configured"
                )
                console.print(
                    f"[yellow]The command exceeded its {timeout_label} timeout.[/yellow]"
                )
            if result.output_truncated:
                console.print(
                    "[yellow]Diagnostic capture was truncated to its configured limit.[/yellow]"
                )
            if result.partial_effect_possible:
                console.print(
                    "[bold yellow]The failed command may have partially completed. "
                    "Any correction must inspect the current state before retrying."
                    "[/bold yellow]"
                )

            if attempt < max_attempts - 1:
                recover = questionary.confirm(
                    "Would you like me to try and fix this automatically?",
                    qmark="ShellPa ",
                    style=questionary_style(active_settings),
                    default=True,
                ).ask()

                if recover:
                    is_recovery = True
                    recovery_context = build_recovery_context(query, request, result)
                    continue
                console.print("[yellow]Auto-recovery aborted by user.[/yellow]")
                return

            console.print(
                "[bold red]Max recovery attempts reached. Returning to terminal.[/bold red]"
            )
            return
        else:
            console.print("[yellow]Execution cancelled by user.[/yellow]")
            return


def _run_shellpa(
    query: str | None,
    *,
    force: bool,
    dry_run: bool,
    mode: PermissionMode,
    timeout_seconds: float | None,
    passthrough: bool,
) -> None:
    config_status = load_config()
    env_info = detect_environment()
    ux_settings = load_ux_settings()
    event_logger = SessionLogger()
    event_logger.emit(
        "session_start",
        version=__version__,
        provider=config_status.provider,
        model=config_status.model_name,
        os=env_info["os"],
        shell=env_info["shell"],
        mode=mode,
    )

    try:
        workspace_context = detect_workspace()
        if query is not None:
            process_query(
                query,
                env_info,
                force,
                dry_run,
                mode,
                timeout_seconds,
                passthrough,
                ux_settings,
                event_logger,
                workspace_context,
            )
            return

        play_startup_reveal(
            console,
            ux_settings,
            env_info,
            config_status.model_name,
        )
        display_session_greeting(console, ux_settings)
        display_workspace_identity(console, workspace_context)
        run_first_time_onboarding(console, ux_settings)
        state = InteractiveState(
            mode=mode,
            model_name=config_status.model_name,
            env_info=env_info,
            settings=ux_settings,
            workspace=workspace_context,
        )

        def process_interactive(user_input: str, active_mode: PermissionMode) -> None:
            try:
                process_query(
                    user_input,
                    env_info,
                    force,
                    dry_run,
                    active_mode,
                    timeout_seconds,
                    passthrough,
                    ux_settings,
                    event_logger,
                    state.workspace,
                )
            except typer.Exit:
                pass
            finally:
                try:
                    state.workspace = detect_workspace()
                except OSError:
                    # Keep the last valid identity if a command removed or made
                    # the active working directory temporarily unavailable.
                    pass

        run_interactive_session(console, state, process_interactive)
    finally:
        event_logger.emit("session_end", outcome="closed")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip approval only for known read-only or normal-risk commands.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the generated command without executing it."
    ),
    mode: PermissionMode = typer.Option(
        PermissionMode.ASK,
        "--mode",
        help="Permission mode: ask, plan, or trusted.",
        case_sensitive=False,
    ),
    timeout_seconds: float | None = typer.Option(
        None,
        "--timeout",
        min=0.1,
        help="Stop a command after this many seconds.",
    ),
    passthrough: bool = typer.Option(
        False,
        "--passthrough",
        help="Attach interactive child commands directly to this terminal.",
    ),
) -> None:
    """
    Translate English into a shell command and execute it.
    If no query is provided, starts an interactive REPL session.
    """
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "force": force,
            "dry_run": dry_run,
            "mode": mode,
            "timeout_seconds": timeout_seconds,
            "passthrough": passthrough,
        }
    )
    if ctx.invoked_subcommand is None:
        _run_shellpa(None, **ctx.obj)


@app.command("run")
def run_command(
    ctx: typer.Context,
    words: list[str] = typer.Argument(
        None,
        help="Natural-language request. The explicit form handles reserved words.",
    ),
    force: bool | None = typer.Option(
        None,
        "--force",
        "-f",
        help="Skip approval only for known read-only or normal-risk commands.",
    ),
    dry_run: bool | None = typer.Option(
        None,
        "--dry-run",
        help="Print the generated command without executing it.",
    ),
    mode: PermissionMode | None = typer.Option(
        None,
        "--mode",
        help="Permission mode: ask, plan, or trusted.",
        case_sensitive=False,
    ),
    timeout_seconds: float | None = typer.Option(
        None,
        "--timeout",
        min=0.1,
        help="Stop a command after this many seconds.",
    ),
    passthrough: bool | None = typer.Option(
        None,
        "--passthrough",
        help="Attach interactive child commands directly to this terminal.",
    ),
) -> None:
    """Execute a natural-language request."""
    root_options = dict(ctx.find_root().obj or {})
    query_head = ctx.meta.get("shellpa_query_head")
    query_parts = ([query_head] if query_head else []) + list(words or [])
    query = " ".join(str(part) for part in query_parts).strip()
    if not query:
        raise typer.BadParameter("Provide a natural-language request.")
    overrides = {
        "force": force,
        "dry_run": dry_run,
        "mode": mode,
        "timeout_seconds": timeout_seconds,
        "passthrough": passthrough,
    }
    for key, value in overrides.items():
        if value is not None:
            root_options[key] = value
    _run_shellpa(query, **root_options)


@app.command("config")
def config_command() -> None:
    """Configure the provider, model, and credential."""
    if not run_setup_wizard():
        raise typer.Exit(code=1)


@app.command("login")
def login_command(
    device_code: bool = typer.Option(
        False,
        "--device-code",
        help="Use a one-time device code instead of the browser callback.",
    ),
) -> None:
    """Connect ShellPa's Codex provider to a ChatGPT account."""
    if not login_codex_interactively(console, device_code=device_code):
        raise typer.Exit(code=1)


@app.command("logout")
def logout_command() -> None:
    """Review and clear the Codex-managed account session."""
    if not logout_codex_interactively(console):
        raise typer.Exit(code=1)


@app.command("doctor")
def doctor_command(
    online: bool = typer.Option(
        False,
        "--online",
        help="Check provider-host reachability without sending a model request.",
    ),
) -> None:
    """Diagnose the local ShellPa environment without revealing secrets."""
    report = run_doctor(online=online)
    display_doctor(console, report)
    if report.exit_code:
        raise typer.Exit(code=report.exit_code)


@app.command("context")
def context_command() -> None:
    """Show detected workspace facts and the provider-safe summary."""
    display_workspace_context(console, detect_workspace())


@app.command("about")
def about_command(ctx: typer.Context) -> None:
    """Show ShellPa identity, developers, and repository links."""
    console.print()
    action = run_about_menu(
        console,
        load_ux_settings(),
        return_label="Launch ShellPa Interactive",
    )
    if action is AboutAction.RETURN:
        root_options = dict(ctx.find_root().obj or {})
        _run_shellpa(None, **root_options)


@app.command("help")
def help_command(ctx: typer.Context) -> None:
    """Show ShellPa command help."""
    parent = ctx.parent
    if parent is not None:
        console.print(parent.get_help())


@app.command("version")
def version_command() -> None:
    """Show the installed ShellPa version."""
    console.print(f"ShellPa {__version__}")


if __name__ == "__main__":
    app()
