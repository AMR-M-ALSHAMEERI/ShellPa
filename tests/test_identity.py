from shellpa.identity import (
    MICRO_MARK,
    LogoVariant,
    input_caret_frame,
    prompt_breath_level,
    prompt_mark_frame,
    signal_sweep_active,
    terminal_logo,
)


def test_terminal_logo_uses_width_aware_variants() -> None:
    assert terminal_logo(20).variant is LogoVariant.NARROW
    assert terminal_logo(40).variant is LogoVariant.COMPACT
    full = terminal_logo(90)
    assert full.variant is LogoVariant.FULL
    assert full.lines[-1].strip() == "S H E L L P A"


def test_terminal_logo_has_ascii_fallback() -> None:
    frame = terminal_logo(90, unicode=False)

    assert frame.variant is LogoVariant.FULL
    assert all(line.isascii() for line in frame.lines)
    assert MICRO_MARK in terminal_logo(20, unicode=False).lines


def test_prompt_assembly_stops_as_soon_as_typing_starts() -> None:
    assert prompt_mark_frame(0.0, has_input=False, motion_enabled=True) == "> "
    assert prompt_mark_frame(0.2, has_input=False, motion_enabled=True) == ">·"
    assert prompt_mark_frame(0.5, has_input=False, motion_enabled=True) == MICRO_MARK
    assert prompt_mark_frame(3.0, has_input=False, motion_enabled=True) == ">‾"
    assert prompt_mark_frame(0.1, has_input=True, motion_enabled=True) == MICRO_MARK
    assert prompt_mark_frame(0.1, has_input=False, motion_enabled=False) == MICRO_MARK


def test_signal_sweep_is_brief_and_periodic() -> None:
    assert signal_sweep_active(0.3, motion_enabled=True)
    assert not signal_sweep_active(1.0, motion_enabled=True)
    assert signal_sweep_active(3.0, motion_enabled=True)
    assert not signal_sweep_active(3.0, motion_enabled=False)


def test_prompt_breath_is_smooth_bounded_and_static_during_typing() -> None:
    assert prompt_breath_level(0.0, has_input=False, motion_enabled=True) == 0.0
    assert prompt_breath_level(1.4, has_input=False, motion_enabled=True) == 1.0
    assert prompt_breath_level(2.8, has_input=False, motion_enabled=True) == 0.0
    assert prompt_breath_level(1.4, has_input=True, motion_enabled=True) == 0.0
    assert prompt_breath_level(1.4, has_input=False, motion_enabled=False) == 0.0


def test_input_caret_animates_at_fixed_width_and_stops_during_typing() -> None:
    frames = [
        input_caret_frame(
            elapsed,
            has_input=False,
            motion_enabled=True,
        )
        for elapsed in (2.82, 3.0, 3.18, 3.36)
    ]

    assert frames == ["›", "»", "›", "·"]
    assert all(len(frame) == 1 for frame in frames)
    assert input_caret_frame(3.0, has_input=True, motion_enabled=True) == "›"
    assert (
        input_caret_frame(
            3.0,
            has_input=False,
            motion_enabled=True,
            unicode=False,
        )
        == "+"
    )
