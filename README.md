# llm-mirror

Two personas of one local model, talking to each other.

## Overview

`llm-mirror` runs an autonomous conversation between two personas — **Echo** (warm, curious, generative) and **Mirror** (skeptical, precise) — served by a local oMLX instance. The user observes, pauses, reads back, and injects messages at any time.

Every request reuses the full KV-cache prefix: the entire history appears as a single system message plus a single user message, so prefill work is zero on every turn.

## Quick start

```bash
uv sync
make run
```

Requires a running oMLX server (default `http://localhost:8000`).

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
| `--free` | flag | off | Free scenario (no grounding clauses, empty system prompt) |
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

Typed text (non-command) is injected into the conversation. Use `@Echo:` or `@Mirror:` to target a specific persona.

## Scenarios

- **grounded** (default): Personas + rules + grounding clauses ("Stay on topic", "No AI/meta commentary").
- **free**: Personas only, no grounding clauses, empty system prompt.

Use `--free` for the free scenario.

## Persona cards

| Persona | Trait |
|---|---|
| Echo | Warm, curious, generative. Proposes ideas, explores possibilities, builds on what others said, asks interesting questions. |
| Mirror | Skeptical and precise. Examines claims, points out weaknesses and hidden assumptions, offers counterexamples, disagrees when warranted. Not hostile — rigorous. |

Override with `--echo-prompt` and `--mirror-prompt`.

## Session storage

- `sessions/{YYYYMMDD-HHMMSS}-{slug}.jsonl` — append-only event log (crash-safe).
- `sessions/{same-stem}.md` — derived human-readable Markdown render.
- `logs/mirror.log` — file-only logging (RotatingFileHandler, 1 MB, 3 backups).

Sessions are resumable purely from the JSONL file: transcript, rotation position, persona prompts, sampling config are all reconstructed.

## Architecture

```
main.py      → argparse, health/model check, session init/resume, wiring
app.py       → MirrorApp: state machine (RUNNING/PAUSED/STOPPED), worker thread, injection queue
client.py    → OmlxClient: HTTP chat with retry taxonomy, telemetry, think-tag stripping
prompt.py    → Pure renderer: Message, render_system, render_transcript, render_tail, strip_reply
session.py   → SessionMeta, SessionState, SessionStore, load_session, new_session_path
tui.py       → Tui: Rich Live panel, command dispatch, injection handling, refresh thread
personas.py  → ECHO_CARD, MIRROR_CARD, SCENARIO_GROUNDED, SCENARIO_FREE, SEED_TOPICS
```

## Anti-collapse research

- Per-turn tail directive names the speaker; persona cards in the shared preamble — cuts echoing to 9% (arXiv:2511.09710).
- Echo (constructive) vs Mirror (skeptical) persona tension — mixing peacemaker/troublemaker cuts errors by 54–73pp (arXiv:2509.23055, 2509.05396, 2605.00914).
- Same-model debaters converge to premature consensus (85% conformity) without persona tension.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

Tests mirror source structure: `tests/test_<module>.py`.
