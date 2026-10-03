---
title: Package System MVP 0
slug: package-system-mvp-0
type: feature
status: done
priority: high
size: M
deps: none
design: docs/design/package-system-design.md
plan: plans/completed/tooling-infra/package-system-mvp-0-plan.md
---

# Package System MVP 0

## Summary

Introduce a `packages` module with a `Package` protocol that bundles persona cards, system prompt, rendering logic, and seed topics per conversation style. Packages are discovered via Python entry points under `llm_mirror.packages`. The existing debate scenario is extracted from `personas.py`/`prompt.py` into `packages/debate/`. `personas.py` is removed. CLI gains `--scenario` flag. `SessionMeta.scenario` becomes `SessionMeta.package_name`. Speaker rotation moves into the package. TUI shows package name in status bar.

## Acceptance criteria

- [x] `uv run llm-mirror` works with no flags (defaults to `--scenario debate`)
- [x] `--scenario debate` explicitly selects the debate package
- [x] `--free` still works (maps to debate package with free variant)
- [x] `--echo-prompt` and `--mirror-prompt` still override persona cards
- [x] `--resume latest` works on sessions created before and after the refactor
- [x] `packages/__init__.py` exposes `load_packages()` returning `dict[str, Package]`
- [x] `packages/debate/__init__.py` implements `DebatePackage` with all 7 protocol methods
- [x] `personas.py` is deleted; no imports of `llm_mirror.personas` remain
- [x] `prompt.py` retains only `Message`, `speaker_label()`, `strip_reply()` (plus `render_transcript` and `render_tail`)
- [x] `render_user_message()` is removed from `prompt.py`; app constructs user message directly
- [x] `app.py` calls `package.render_transcript()`, `package.render_tail()`, `package.system_prompt`, `package.next_speaker()`
- [x] `app.py` rotation logic is replaced by `package.next_speaker()`
- [x] `SessionMeta.package_name` replaces `SessionMeta.scenario`; `load_session()` maps legacy values
- [x] TUI status bar shows `package: debate`
- [x] `ruff check .` clean; `pytest` passes

## Notes

- MVP 0 ships only the `debate` package. No community plugin support, no additional scenario packages.
- Variant support: `--free` sets a `self._free` boolean on `DebatePackage`; no `variant` field on `SessionMeta`.
- `speaker_label()` stays in `prompt.py` as a global utility.
- `--scenario debate` is the explicit default.
