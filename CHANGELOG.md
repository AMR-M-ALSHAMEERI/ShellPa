# Changelog

All notable user-facing changes to ShellPa are recorded here.

## 0.3.0 - 2026-07-29

- Added privacy-conscious workspace awareness with explicit project boundaries,
  project-type and tool detection, bounded Git state, and Python environment
  detection.
- Added `shellpa context` and `/context` so users can inspect local workspace
  facts and the smaller provider-safe summary separately.
- Added bounded workspace metadata to initial generation and recovery without
  reading source files, `.env` files, credentials, or arbitrary filenames.
- Added the optional embedded Codex provider for eligible ChatGPT subscriptions
  without requiring a separate Codex CLI installation or an OpenAI API key.
- Added interactive Codex SDK installation, browser/device-code authentication,
  existing-session protection, safe-default logout confirmation, and
  privacy-preserving account diagnostics.
- Added empty, detached, large, missing-Git, non-repository, Unicode-path, and
  unusual-path hardening across Windows, Linux, and macOS.
- Added automated wheel and source-archive inspection to prevent private plans,
  local environments, credentials, or cache files from entering a package.

## 0.2.0 - 2026-07-29

- Added deterministic, cross-platform command risk assessment and permission modes.
- Added structured execution results, timeouts, cancellation, bounded output capture,
  and safer recovery context.
- Redesigned the interactive experience with themes, mode identities, activity
  animation, onboarding, and a persistent About hub.
- Added first-class `run`, `config`, `doctor`, `about`, `help`, and `version`
  commands while retaining natural-language invocation.
- Added secret-free diagnostics and local metadata logging with an explicit opt-out.
- Added automated tests, formatting, linting, type checking, package builds, and
  Windows, Linux, and macOS continuous integration.
