import shellpa.icons as icons


def test_provider_and_shell_icons_have_unicode_defaults(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SHELLPA_ICONS", raising=False)
    monkeypatch.setattr(icons, "unicode_icons_supported", lambda: True)

    assert icons.provider_icon("openai") == "◉"
    assert icons.provider_icon("gemini") == "✦"
    assert icons.shell_icon("powershell") == "❯"
    assert icons.shell_icon("bash") == "$"


def test_ascii_icon_mode_never_requires_special_font(monkeypatch) -> None:
    monkeypatch.setenv("SHELLPA_ICONS", "ascii")

    assert icons.provider_icon("openai") == "[OpenAI]"
    assert icons.shell_icon("powershell") == "[PS]"
    assert icons.ui_icon("success") == "OK"


def test_model_icon_infers_provider(monkeypatch) -> None:
    monkeypatch.setattr(icons, "unicode_icons_supported", lambda: True)

    assert icons.model_icon("gpt-4o") == "◉"
    assert icons.model_icon("gemini/gemini-2.0-flash") == "✦"
    assert icons.model_icon("claude-3-haiku") == "◆"
    assert icons.model_icon("openrouter/openai/gpt-4o") == "◇"
