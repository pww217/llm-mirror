# llm-mirror — AGENTS.md

## Build / test

```
uv sync
uv run ruff check .
uv run pytest
uv run llm-mirror --help
```

## Module map

| Module | Purpose |
|---|---|
| `personas.py` | `ECHO_CARD`, `MIRROR_CARD`, `SCENARIO_GROUNDED`, `SCENARIO_FREE`, `SEED_TOPICS` — byte-stable persona constants |
| `prompt.py` | Pure renderer: `Message`, `speaker_label`, `render_system`, `render_transcript`, `render_tail`, `render_user_message`, `strip_reply` |
| `session.py` | `Sampling`, `TurnUsage`, `SessionMeta`, `SessionState`, `SessionStore`, `load_session`, `new_session_path`, `slugify` |
| `client.py` | `OmlxClient` — HTTP chat with retry taxonomy, telemetry, think-tag stripping |
| `app.py` | `MirrorApp` — state machine (RUNNING/PAUSED/STOPPED), worker thread, injection queue, context/max-turn guards |
| `tui.py` | `ParsedInput`, `parse_input`, `Tui` — Textual TUI with `@work(thread=True)` refresh worker, `call_from_thread()` UI updates, command dispatch, injection handling |
| `main.py` | `main()` — argparse CLI, health/model check, session init/resume, wiring MirrorApp + Tui, RotatingFileHandler logging |

## Conventions

- Type hints on every public function and class.
- No comments in code — the code is the documentation.
- File-only logging (`logs/mirror.log`, `RotatingFileHandler` 1 MB, 3 backups). No console handler.
- PEP 8 style enforced by `ruff` (default config, import sorting).
- Tests mirror source structure: `tests/test_<module>.py`.

## ⚠️ Load-bearing invariant

The prompt contract is byte-stable — never vary `render_system` inputs mid-session; KV-cache correctness depends on it.
