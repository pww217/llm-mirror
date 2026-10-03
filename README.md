# llm-mirror

An experiment in self-dialogue: run a local LLM as two personas debating, roleplaying, or improvising — fully offline, zero API keys, terminal-based TUI.

## What it does

`llm-mirror` runs an autonomous conversation between two personas — **Echo** and **Mirror** — served by a local oMLX (or any OpenAI-compatible) server. The user observes, pauses, reads back, and injects messages at any time.

Every request reuses the full KV-cache prefix: the entire history appears as a single system message plus a single user message, so prefill work is zero on every turn.

## Quick start

```bash
uv sync
make run
```

Requires a running oMLX server (default `http://localhost:8000`).

## Packages

| Package | Command | Description |
|---|---|---|
| Debate | `make run` | Two personas explore a topic in alternating turns |
| Roleplay | `--scenario roleplay` | Two personas inhabit characters in a fictional setting |
| Improv | `--scenario improv` | Two personas collaboratively build a story |

## Modes

| Mode | Command | Description |
|---|---|---|
| TUI | `make run` | Rich terminal UI with live transcript, commands, injection |
| Headless | `make headless` | Prints turns to stdout; no terminal UI |
| Free (no context) | `make headless-free` | Empty system prompt, no seed — model generates freely |
| Thinking | `make headless-thinking` | Enables thinking mode (longer reasoning) |
| Resume | `make resume` | Reloads the latest session from disk |

## CLI reference

```
llm-mirror [OPTIONS]
```

| Option | Type | Default | Description |
|---|---|---|---|
| `--prompt TEXT` | str | — | Session seed topic |
| `--no-seed` | flag | off | No seed topic |
| `--scenario TEXT` | str | `debate` | Package name (`debate`, `roleplay`, `improv`) |
| `--free` | flag | off | **[deprecated]** Use `--scenario debate` with `--no-seed` |
| `--resume [PATH\|latest]` | str | — | Resume a session |
| `--model TEXT` | str | from `/health` | Model name |
| `--session-dir PATH` | str | `sessions` | Session file directory |
| `--echo-prompt TEXT` | str | built-in card | Custom Echo persona card |
| `--mirror-prompt TEXT` | str | built-in card | Custom Mirror persona card |
| `--temp FLOAT` | float | 0.8 | Sampling temperature |
| `--max-tokens INT` | int | 300 | Max tokens per turn |
| `--frequency-penalty FLOAT` | float | 0.0 | Frequency penalty |
| `--presence-penalty FLOAT` | float | 0.0 | Presence penalty |
| `--max-turns INT` | int | 0 | Max turns (0 = unlimited) |
| `--log-level TEXT` | str | INFO | Logging level |
| `--base-url TEXT` | str | `http://localhost:8000` | oMLX base URL |
| `--thinking` | flag | off | Enable thinking mode |
| `--headless` | flag | off | Print turns to stdout, no TUI |
| `--turn-delay FLOAT` | float | 3.0 | Seconds between turns |

## TUI commands

| Command | Description |
|---|---|
| `/pause` | Pause the conversation |
| `/resume` | Resume a paused conversation |
| `/quit` | Stop and save |
| `/save` | Save current session |
| `/stats` | Show turn statistics (tokens, cache hit %, latency) |
| `/transcript` | Show full Markdown transcript |
| `/help` | Show available commands |
| `Escape` | Quit |
| `p` | Pause |
| `r` | Resume |
| `s` | Save |

Typed text (non-command) is injected into the conversation. Use `@Echo:` or `@Mirror:` to target a specific persona.

## Session storage

- `sessions/{YYYYMMDD-HHMMSS}-{slug}.jsonl` — append-only event log (crash-safe).
- `sessions/{same-stem}.md` — derived human-readable Markdown render.
- `logs/mirror.log` — file-only logging (RotatingFileHandler, 1 MB, 3 backups).

Sessions are resumable purely from the JSONL file: transcript, rotation position, persona prompts, sampling config are all reconstructed.

## Architecture

```
src/llm_mirror/
  main.py      → CLI flags, startup, shutdown
  app.py       → MirrorApp: state machine (RUNNING/PAUSED/STOPPED), worker thread, injection queue
  client.py    → OmlxClient: HTTP chat with retry taxonomy, telemetry, think-tag stripping
  prompt.py    → Message, speaker_label, strip_reply, render_transcript, render_tail
  session.py   → SessionMeta, SessionState, SessionStore, load_session, new_session_path
  tui.py       → Tui: Textual app with RichLog transcript, command dispatch, refresh worker
  packages/
    debate/    → DebatePackage: Echo vs Mirror topic exploration
    roleplay/  → RoleplayPackage: fictional character roleplay
    improv/    → ImprovPackage: collaborative story-building
```

Tests mirror source structure: `tests/test_<module>.py`.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

## License

Licensed under the [Apache License 2.0](LICENSE).
