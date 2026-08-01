"""Terminal-native ShellPa identity primitives.

The graphical mark is intentionally translated into portable characters rather
than terminal image protocols or font-specific glyphs.  These helpers contain
no terminal I/O, which keeps capability fallbacks and motion deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

MICRO_MARK = ">_"
IDLE_SIGNAL_START = 2.8
IDLE_SIGNAL_INTERVAL = 2.8
IDLE_SIGNAL_DURATION = 0.72


class LogoVariant(str, Enum):
    FULL = "full"
    COMPACT = "compact"
    NARROW = "narrow"


@dataclass(frozen=True)
class LogoFrame:
    lines: tuple[str, ...]
    variant: LogoVariant


UNICODE_LOGO = (
    "       ╭────────╮",
    ">──────┘  ╭──╮  │",
    "          ╰──╯  ╰──╮",
    "          ╭────────╯_",
    "          S H E L L P A",
)

ASCII_LOGO = (
    "       +--------+",
    ">------/  +--+  |",
    "          +--+  +--+",
    "          +--------/_",
    "          S H E L L P A",
)


def logo_variant(width: int) -> LogoVariant:
    if width < 28:
        return LogoVariant.NARROW
    if width < 58:
        return LogoVariant.COMPACT
    return LogoVariant.FULL


def terminal_logo(width: int, *, unicode: bool = True) -> LogoFrame:
    """Return a width-aware logo with a reliable ASCII fallback."""
    variant = logo_variant(width)
    if variant is LogoVariant.NARROW:
        return LogoFrame((MICRO_MARK,), variant)
    if variant is LogoVariant.COMPACT:
        return LogoFrame((MICRO_MARK, "S H E L L P A"), variant)
    return LogoFrame(UNICODE_LOGO if unicode else ASCII_LOGO, variant)


def prompt_mark_frame(
    elapsed: float,
    *,
    has_input: bool,
    motion_enabled: bool,
    unicode: bool = True,
) -> str:
    """Return the current prompt mark without performing background output."""
    if has_input or not motion_enabled:
        return MICRO_MARK
    if elapsed < 0.14:
        return "> "
    if elapsed < 0.28:
        return ">·" if unicode else ">."
    if elapsed < IDLE_SIGNAL_START:
        return MICRO_MARK
    position = (elapsed - IDLE_SIGNAL_START) % IDLE_SIGNAL_INTERVAL
    if position < 0.18:
        return MICRO_MARK
    if position < 0.36:
        return ">‾" if unicode else ">-"
    if position < 0.54:
        return MICRO_MARK
    if position < 0.72:
        return ">·" if unicode else ">."
    return MICRO_MARK


def signal_sweep_active(elapsed: float, *, motion_enabled: bool) -> bool:
    """Use a brief sweep after assembly and once per restrained idle interval."""
    if not motion_enabled or elapsed < 0.28:
        return False
    if elapsed < 0.72:
        return True
    if elapsed < IDLE_SIGNAL_START:
        return False
    position = (elapsed - IDLE_SIGNAL_START) % IDLE_SIGNAL_INTERVAL
    return position < IDLE_SIGNAL_DURATION


def prompt_breath_level(
    elapsed: float,
    *,
    has_input: bool,
    motion_enabled: bool,
) -> float:
    """Return a smooth bounded 0..1 breath that stops while the user types."""
    if has_input or not motion_enabled:
        return 0.0
    phase = (elapsed % IDLE_SIGNAL_INTERVAL) / IDLE_SIGNAL_INTERVAL
    return (1.0 - math.cos(phase * math.tau)) / 2.0


def input_caret_frame(
    elapsed: float,
    *,
    has_input: bool,
    motion_enabled: bool,
    unicode: bool = True,
) -> str:
    """Animate the ready indicator without changing its display width."""
    resting = "›" if unicode else ">"
    if has_input or not motion_enabled or elapsed < IDLE_SIGNAL_START:
        return resting
    position = (elapsed - IDLE_SIGNAL_START) % IDLE_SIGNAL_INTERVAL
    if position < 0.18:
        return resting
    if position < 0.36:
        return "»" if unicode else "+"
    if position < 0.54:
        return resting
    if position < 0.72:
        return "·" if unicode else "."
    return resting
