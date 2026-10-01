---
title: Mirror Chat MVP
slug: mirror-chat-mvp
type: feature
status: done
priority: high
size: M
deps: none
design: docs/design/mirror-chat-design.md
plan: plans/mirror-chat-mvp-plan.md
---

# Mirror Chat MVP

## Summary

`llm-mirror`: a rich TUI where two personas of one oMLX-served model (default `http://localhost:8000`) converse autonomously until paused. User injects messages anytime; sessions persist as JSONL + Markdown and resume; every turn hits the KV prefix cache for the full history (byte-identical canonical prompt). Prompt-level anti-collapse pressure per the design's research basis.

## Acceptance criteria

- [x] `uv run llm-mirror` starts a conversation with no flags; conversation runs until `/pause` or `/quit`.
- [x] `--prompt`, `--no-seed`, `--free`, `--model`, `--echo-prompt`/`--mirror-prompt`, `--resume latest` all behave per design doc.
- [x] Cache acceptance check: from turn ≥ 3, `cached_tokens ≥ prompt_tokens − tokens(last message) − tokens(tail) − 256`, verified on a 20-turn session (manual smoke test; record results in the session JSONL).
- [x] Prompt contract: identical session state renders byte-identical system + transcript prefix (unit test).
- [x] Injections: ambient text and `@Echo:`/`@Mirror:` targeting, queued while RUNNING, immediate while PAUSED (unit test on queue logic; manual smoke).
- [x] `/pause` `/resume` `/quit` `/save` `/stats` `/transcript` `/help` all work; Ctrl+C saves cleanly; no crash on server error mid-conversation.
- [x] `sessions/*.jsonl` records every event incl. per-turn `usage.cached_tokens`; `*.md` render matches; `--resume` reproduces transcript and rotation position.
- [x] Context guard: auto-pauses with warning at 90% of `max_model_len`.
- [x] `ruff check .` and `pytest` pass.

## Notes

- Roadmap scaffolding (`roadmap/templates/feature.md`, `ticket` skill, `make roadmap`) does not exist in this fresh repo; ticket written directly, validation steps skipped.

## Code review (2026-09-30)

Critical fixes applied:
1. `client.py`: top-level `thinking` field replaced with `chat_template_kwargs: {enable_thinking: false}` (empirically verified: oMLX ignores the former, only the latter works).
2. `session.py`: `SessionMeta` now stores `thinking: bool`; `load_session` uses ordered replay (no stale next_speaker bug); markdown header includes thinking toggle.
3. `app.py`: `inject(text, target)` signature (no duplicate prefix parsing); `_injection_queue` init'd in `__init__` (not `_run()`); uses `meta.thinking` directly; added `SessionStats.duration_s` and `last_turn` property.
4. `main.py`: resume path `store` NameError fixed; seed persisted as injection event; default model from `/health`; `max_model_len` from `/v1/models`; session_id from `store.path.stem`.
5. `tui.py`: 0.5s live refresh thread; header turn count; footer last-turn stats; `/stats` table; `/transcript` pager; `_store.path` property access.
6. Tests: 109 passing; inject targeted call updated; SessionMeta.thinking default tested.
7. Gates: `ruff check .` clean (1 acceptable SIM115); `pytest` 109 passed.
