"""Terminal-native ShellPa identity primitives.

The graphical mark is intentionally translated into portable characters rather
than terminal image protocols or font-specific glyphs.  These helpers contain
no terminal I/O, which keeps capability fallbacks and motion deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from itertools import groupby

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
    styled_lines: tuple[tuple[LogoSpan, ...], ...]


class LogoTone(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ACCENT = "accent"
    WORDMARK = "wordmark"


@dataclass(frozen=True)
class LogoSpan:
    text: str
    tone: LogoTone


P = LogoTone.PRIMARY
S = LogoTone.SECONDARY
A = LogoTone.ACCENT
W = LogoTone.WORDMARK


UNICODE_LOGO_MASK = (
    "                          NNNNNNNNNNNNNNNNNNN",
    "                        NNNNNNNNNNNNNNNNNNNNNNN",
    "BBBB                   NNNN                 NNNN",
    "BBBBBB                 NNN     BBBBBBBBBBB   NNN",
    "   BBBBB               NNNN    BBBBBBBBBBB   NNN",
    "     BBBBB              NNNNN  BBB          NNNN",
    "    BBBBB                 NNNN BBB   BNNNNNNNNN",
    "  BBBBB                    NNN BBB BBBNNNNNNNN",
    "BBBBB   BBBBBBBBBBBBBBBBBBBBNN BBB BBB",
    "BBB     BBBBBBBBBBBBBBBBBBBB   BBB BBB",
    "                               BBBBBBB GGGGGGGGGGG",
    "                                BBBBB   GGGGGGGGGG",
)


def _mask_to_spans(row: str) -> tuple[LogoSpan, ...]:
    tones = {"B": P, "N": S, "G": A, " ": P}
    return tuple(
        LogoSpan(
            " " * len(cells) if key == " " else "█" * len(cells),
            tones[key],
        )
        for key, grouped in groupby(row)
        if (cells := tuple(grouped))
    )


UNICODE_LOGO_SPANS = tuple(_mask_to_spans(row) for row in UNICODE_LOGO_MASK) + (
    (LogoSpan("", P),),
    (LogoSpan("                S H E L L P A", W),),
)


ASCII_LOGO_SPANS = (
    (LogoSpan("       +--------+", S),),
    (LogoSpan(">------/  +--+  ", P), LogoSpan("|", S)),
    (LogoSpan("          +--+  ", P), LogoSpan("+--+", S)),
    (LogoSpan("          +--------/", P), LogoSpan("_", A)),
    (LogoSpan("", P),),
    (LogoSpan("          S H E L L P A", W),),
)


def _logo_frame(
    styled_lines: tuple[tuple[LogoSpan, ...], ...],
    variant: LogoVariant,
) -> LogoFrame:
    return LogoFrame(
        tuple("".join(span.text for span in line) for line in styled_lines),
        variant,
        styled_lines,
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
        return _logo_frame(((LogoSpan(">", P), LogoSpan("_", A)),), variant)
    if variant is LogoVariant.COMPACT:
        return _logo_frame(
            (
                (LogoSpan(">", P), LogoSpan("_", A)),
                (LogoSpan("S H E L L P A", W),),
            ),
            variant,
        )
    return _logo_frame(
        UNICODE_LOGO_SPANS if unicode else ASCII_LOGO_SPANS,
        variant,
    )


def reveal_logo(frame: LogoFrame, progress: float) -> LogoFrame:
    """Reveal a logo from left to right while keeping its layout stable."""
    bounded = min(max(progress, 0.0), 1.0)
    if bounded >= 1.0 or frame.variant is not LogoVariant.FULL:
        return frame

    art_lines = frame.styled_lines[:-1]
    width = max(
        (len("".join(span.text for span in line)) for line in art_lines), default=0
    )
    art_progress = min(bounded / 0.82, 1.0)
    wordmark_progress = max((bounded - 0.82) / 0.18, 0.0)
    art_cutoff = math.ceil(width * art_progress)

    revealed: list[tuple[LogoSpan, ...]] = []
    for line in art_lines:
        column = 0
        visible_line: list[LogoSpan] = []
        for span in line:
            visible = max(min(art_cutoff - column, len(span.text)), 0)
            text = span.text[:visible] + (" " * (len(span.text) - visible))
            visible_line.append(LogoSpan(text, span.tone))
            column += len(span.text)
        revealed.append(tuple(visible_line))

    wordmark = frame.styled_lines[-1]
    wordmark_width = sum(len(span.text) for span in wordmark)
    wordmark_cutoff = math.ceil(wordmark_width * wordmark_progress)
    revealed_wordmark: list[LogoSpan] = []
    column = 0
    for span in wordmark:
        visible = max(min(wordmark_cutoff - column, len(span.text)), 0)
        text = span.text[:visible] + (" " * (len(span.text) - visible))
        revealed_wordmark.append(LogoSpan(text, span.tone))
        column += len(span.text)
    revealed.append(tuple(revealed_wordmark))

    return _logo_frame(tuple(revealed), frame.variant)


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
