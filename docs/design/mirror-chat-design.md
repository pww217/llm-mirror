# Mirror Chat — MVP Design

- Type: feature (greenfield; repo `llm-mirror` contains no code today)
- Status: final — all decisions resolved with the user; no open questions
- Design doc: this file. Roadmap ticket: `roadmap/features/mirror-chat-mvp.md`

## Problem

Nothing exists in this repo. The goal is an experiment tool: two personas of one locally served LLM hold an autonomous, unending conversation. The user observes, pauses, reads back, and injects messages. The hard constraint the user named: the conversation must not waste prefill work — the KV prefix cache must cover the full history on every turn, even though each turn is a different "speaker".

Secondary goal, grounded in research: the tool must actively resist the documented failure modes of LLM↔LLM self-play (repetition loops, identity mirroring, premature agreement).

## Verified environment facts

| Fact | Value | How verified |
|---|---|---|
| Server | oMLX 0.7.0rc1 (`jundot/omlx`) at `http://localhost:8000` | `pgrep`, `/v1/models`, `/health` |
| Port 8080 | Unrelated ("FIRE Dashboard") — do not use | HTTP probe |
| API | OpenAI-compatible (`/v1/chat/completions`, `/v1/models`); `/health` reports `default_model` and engine-pool state | curl |
| Served models | 9 loaded; server default `mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit`; `max_model_len` 262144 | `/v1/models`, `/health` |
| Prefix cache | Block-based, 256-token blocks, hash-deduplicated, Copy-on-Write, hot RAM + cold SSD tiers; blocks persist across requests **and server restarts** | oMLX source (`omlx/cache/prefix_cache.py`) |
| KV sharing scope | Per model only — two different models never share blocks, even in one EnginePool | oMLX architecture |
| Cache telemetry | Responses include `usage.prompt_tokens_details.cached_tokens` | live test: 17-token repeat → 12 cached, 1.09s → 0.38s |
| Toolchain | macOS arm64, `uv` 0.12.19; Python 3.13 provisioned by uv | shell |

## Research basis (anti-collapse design)

Every mitigation below maps to a cited finding from 2025–26 studies of exactly this setup.

1. **Repetition collapse is the default outcome.** Two LLMs replying to each other from a seed sentence: 35/50 runs locked into a repeated phrase within 25 turns; once a loop starts, both models feed it (arXiv:2512.06256). → novelty pressure in the rules; 2–6 sentence turns; injections.
2. **Homogeneous pairs collapse more than mixed pairs** (720-run, 40-turn study; collapse = adjacent-turn cosine ≥ 0.92 sustained ≥ 3 turns). → embedding-based collapse detector is a reach goal (embedding model is already served).
3. **Echoing / identity drift.** Agents abandon their persona and mirror their partner in 55–70% of agent-to-agent conversations, onset ~turn 8 — but a **structured role declaration on every turn cut echoing to 9%** (arXiv:2511.09710). → per-turn tail directive names the speaker; persona cards live in the shared preamble.
4. **Inter-agent sycophancy.** Same-model debaters converge to premature consensus (conformity up to 85%); the best-performing configuration mixes a "peacemaker" with a "troublemaker"; a single dissenting voice cuts correct→incorrect flips by 54–73pp (arXiv:2509.23055, 2509.05396, 2605.00914). → Echo (constructive) vs Mirror (skeptical) persona tension; user injection is the dissent channel.
5. **Attractor drift.** Iterated LLM chains drift to attractor states, and *open-ended* tasks drift faster than constrained ones (GAME, ICLR 2025). → default seed topics are constrained-but-open; `--no-seed` raw mode is supported deliberately.
6. **"Non-dual register."** Closed self-play of chat-tuned models — including Qwen3-30B-A3B, same family as the served default — slides into repetitive, quasi-mystical self-reference; any outside input slows it (Claude 4 System Card §5.5; Bergel 2026 replication). → grounding on by default; `--free` escape hatch; injections are a documented anti-collapse lever.
7. **Multi-turn unreliability.** All models degrade ~39% in multi-turn vs single-turn settings; periodic instruction recap helps modestly (ICLR 2026). → resumable sessions; `/stats` visibility.

## Target state

One command, `llm-mirror`, runs a rich TUI in which two personas — **Echo** and **Mirror** — of one oMLX-served model converse autonomously. The conversation runs until the user pauses or quits. The user can inject a message at any time (typed text; `@Echo:`/`@Mirror:` to target). Every session is fully persisted (JSONL event log + live Markdown render) and resumable. Per-turn cache telemetry is recorded and summarized. Prompt-level anti-collapse pressure is built into every turn. Zero wasted prefill: the entire history is a cache hit on every request.

## Final decisions

### D1 — One model, two personas (Echo, Mirror)

Both participants are the same served model with different personas. `--model` overrides (default: read `default_model` from `GET /health`, fallback: first entry of `/v1/models`).

Rejected: two different models — per-model KV blocks mean zero cross-model cache sharing; a second model adds ~20 GB load and cold-start latency. The participant data model carries a per-participant `model` field from day one, so the two-model reach goal needs no schema change.

Rejected: same model, no personas — pure self-mirror collapses into repetition fastest (finding 2).

### D2 — Canonical prompt contract (byte-identical shared prefix)

Every request is exactly two messages: one `system` message (scenario + persona cards + rules) and one `user` message (rendered transcript + tail directive). The transcript is plain text inside the single user message — **not** an alternating `user`/`assistant` message list.

Within a session, the system message and the transcript-prefix of the user message are byte-identical on every request. Per-turn *new* (uncached) tokens = the latest message + the tail directive + at most one 256-token partial block. This is the theoretical minimum for a stateless API: the model must attend to the new message, and oMLX/vLLM expose no stateful continuation endpoint.

Rejected: native alternating roles (Echo owns `assistant`, Mirror owns `user`) — role tokens diverge at the first turn, so each participant's view re-prefills the entire history; ~2× prompt compute, alternating forever. Also rejected: one request generating both speakers' turns — saves only the tail's ~20 tokens while breaking pause/inject granularity and speaker attribution.

Cache acceptance check (implementer must verify, not assume): from turn ≥ 3, `cached_tokens ≥ prompt_tokens − tokens(last message) − tokens(tail) − 256`.

### D3 — Persona prompts are public cards in the shared preamble

Both participants see both persona cards. `--echo-prompt` / `--mirror-prompt` override the default card text. Cards are part of the session's recorded metadata and are replayed byte-identically on resume.

Rejected: private persona prompts placed in the tail (cache-safe, since the tail is new tokens anyway, but it re-prefills the prompt every turn and invites hidden-goal complexity). Future option, not MVP.

### D4 — Turn protocol

Strict rotation Echo → Mirror → Echo…; Echo opens. Target length 2–6 sentences per turn (the 50-token-cap study found ultra-short turns accelerate loops). The rules forbid concluding, summarizing, or signing off. Seed topic, when used, is the first transcript line as a `User:` turn. Response parsing strips an optional leading `Name:` label, surrounding quotes, and whitespace; empty output after one retry is an error (pause, surface, await user).

### D5 — Grounding: on by default, `--free` to lift

The grounded system prompt keeps the conversation on its topic and forbids meta/existential spiraling. `--free` removes exactly two clauses (topic grounding; the no-meta clause) while keeping sentence limits and novelty pressure — degenerate loops are never interesting, even in observation mode. No runtime toggle (rejected: research shows mid-run identity refreshes disorder the conversation).

### D6 — Sampling defaults

`temperature 0.8`, `max_tokens 300`, `frequency_penalty 0.0`, `presence_penalty 0.0` for both participants. CLI flags override all. Rationale: anti-repetition relies on prompt-level novelty pressure (research-supported) rather than sampling-penalty guesses; evidence on temperature in debate settings is mixed and task-specific.

### D7 — Injection semantics

Typed non-command text is a `User:` line in the canonical transcript. Ambient text does not change the rotation (whoever is next responds). `@Echo:`/`@Mirror:` prefix forces that participant as the next speaker; rotation continues from them. While RUNNING, input is queued and applied at the next turn boundary (transcript atomicity); while PAUSED, applied immediately. All injections are visible in the TUI and logged.

### D8 — Control commands; default state RUNNING

`/pause`, `/resume`, `/quit` (also Ctrl+C: save and exit cleanly), `/save`, `/stats`, `/transcript` (page the rendered Markdown), `/help`. Unknown `/x` → error line, no side effects. Pause takes effect at the turn boundary; an in-flight request is allowed to finish and its turn is kept.

### D9 — Persistence and resume

`sessions/{YYYYMMDD-HHMMSS}-{slug}.jsonl` is the append-only single source of truth — one record per event (session meta, turn, injection, control), written immediately (crash-safe). `sessions/{same-stem}.md` is a derived human-readable render, rewritten per event. `--resume [PATH|latest]` rebuilds state purely from the JSONL: transcript, rotation position, persona prompts, sampling config. System prompts are reconstructed from recorded session metadata, byte-identical. Expected (verify): oMLX's SSD tier makes even a post-restart resume warm.

### D10 — Context guard, no silent truncation

`max_model_len` is read at startup from `/v1/models`. At 90% of it the app auto-pauses with a warning; the user may resume anyway (warns again each subsequent turn). There is never silent history truncation or summarization in MVP.

### D11 — Robustness

Transient failures (`ConnectError`, timeouts, 5xx, 429): 3 retries, backoff 1s/2s/4s, then pause with the error surfaced in the TUI — the app never crashes and always returns to the input loop. 4xx (non-429): no retry; model-not-found suggests `--model` with the `/v1/models` list. Server unreachable at startup: friendly message, exit code 1.

### D12 — Tooling

uv project, `requires-python >= 3.13` (uv provisions the interpreter). Runtime deps: `httpx`, `rich` — nothing else. Dev deps: `ruff` (default config, PEP 8 + import sorting), `pytest`. Quality gates: `ruff check .` and `pytest` pass.

### D13 — Module boundaries (one responsibility each)

```
src/llm_mirror/
  main.py      # CLI flags, startup, shutdown
  app.py       # state machine (RUNNING/PAUSED/STOPPED), threads, injection queue
  client.py    # oMLX HTTP client: health/models/chat, retries, telemetry extraction
  prompt.py    # pure prompt-contract rendering (system, transcript, tail) — no IO
  session.py   # state, JSONL append, MD render, resume reconstruction
  tui.py       # rich layout, Live panel, command dispatch, pager
  personas.py  # default persona cards, rules, seed topics
```

Tests target the pure modules (`prompt`, `session`, command parsing); no network in tests.

## Interface contracts

### Prompt contract (exact text)

System message — `SCENARIO_GROUNDED` (default):

```
This is an ongoing conversation between two AI participants, Echo and Mirror,
occasionally joined by a human, "User". They take turns in strict rotation:
Echo, Mirror, Echo, Mirror, and so on. Each transcript line is one speaker's
message, labeled with their name. There is no moderator; the conversation
never ends and is never summarized or wrapped up.

Echo: warm, curious, and generative. Proposes ideas, explores possibilities,
builds on what others said, asks interesting questions.

Mirror: skeptical and precise. Examines claims, points out weaknesses and
hidden assumptions, offers counterexamples, disagrees when warranted. Not
hostile — rigorous.

Rules for every message: 2-6 sentences. Stay in character as the named
speaker. Advance the topic: introduce a new idea, question, perspective, or
example rather than restating or agreeing with what was already said. Stay on
the conversation's topic. Do not comment on being an AI, on the format, or on
the conversation itself. Never conclude, sign off, or say goodbye.
```

`SCENARIO_FREE` (`--free`) is identical minus two clauses: "Stay on the conversation's topic." and "Do not comment on being an AI, on the format, or on the conversation itself."

When `--echo-prompt` / `--mirror-prompt` are given, they replace the Echo/Mirror card text, positions and all other lines unchanged.

User message = transcript + `"\n\n"` + tail:

- Transcript lines: `"{Name}: {text}"` joined by `"\n"` (names: `Echo`, `Mirror`, `User`).
- Seeded session's first line: `"User: Topic: {seed}."`
- Tail (regular turns): `"The next message is from {Name}. Write only {Name}'s next message text (no name label), in character."`
- Tail (unseeded opening turn): `"This is the opening of the conversation. The next message is from Echo. Write only Echo's message text (no name label), in character."`

Request: `POST {base_url}/chat/completions` with `{model, messages: [system, user], temperature, max_tokens, frequency_penalty, presence_penalty}` — non-streaming. `base_url` default `http://localhost:8000/v1`.

### CLI

| Flag | Type | Default | Meaning |
|---|---|---|---|
| `--model` | str | `/health` default_model | Override served model |
| `--prompt` | str | — | Initial user message (replaces random seed) |
| `--no-seed` | flag | off | No seed; Echo opens unseeded |
| `--free` | flag | off | Ungrounded scenario |
| `--echo-prompt` / `--mirror-prompt` | str | built-in cards | Replace persona card text |
| `--temp` | float | 0.8 | Both participants |
| `--max-tokens` | int | 300 | Per turn |
| `--frequency-penalty` / `--presence-penalty` | float | 0.0 | Pass-through |
| `--resume` | str | — | `PATH` or `latest` |
| `--max-turns` | int | 0 (unlimited) | Hard stop → auto-pause |
| `--base-url` | str | `http://localhost:8000/v1` | API root |
| `--session-dir` | str | `./sessions` | Output directory |
| `--log-level` | str | `INFO` | File logging |

### Commands (typed at the input line)

| Command | Effect |
|---|---|
| `/pause` `/resume` | Gate the conversation at turn boundaries |
| `/quit` or Ctrl+C | Save and exit cleanly |
| `/save` | Flush + confirm (JSONL is already crash-safe; rewrites MD) |
| `/stats` | Table: turns per speaker, prompt/completion/cached tokens, cache %, mean latency, duration |
| `/transcript` | Page the full rendered transcript |
| `/help` | Command list |
| *(anything else)* | Injection (queued if RUNNING; immediate if PAUSED) |

### JSONL event schema (one JSON object per line)

Common envelope: `{"ts": "ISO-8601 UTC", "type": str}` plus:

- `type: "session"` — `{model, base_url, scenario: "grounded"|"free", participants: {echo: {card: str}, mirror: {card: str}}, sampling: {...}, seed: str|null, max_model_len: int}`
- `type: "turn"` — `{speaker: "echo"|"mirror", model, content: str, usage: {prompt_tokens: int, completion_tokens: int, cached_tokens: int}, latency_ms: int, sampling: {...}}`
- `type: "injection"` — `{target: "ambient"|"echo"|"mirror", content: str}`
- `type: "control"` — `{action: "pause"|"resume"|"save"|"quit"|"auto_pause_context"|"auto_pause_max_turns"|"startup"|"shutdown", detail: str|null}`

### Markdown render

Header block (session metadata), then one paragraph per message: `**Echo:** text`, `**Mirror:** text`, `**User:** text`, with a horizontal rule between turns. Derived only from the JSONL; never edited directly.

### TUI layout

rich `Live` panel: header line (state chip, turn count, model, session id) · transcript viewport (last ~10 messages; Echo cyan, Mirror magenta, User yellow) · status line (last turn: prompt/cached tokens, cache %, latency; running totals). Input line sits below the panel. Logging goes to file only — never stdout (the TUI owns the terminal).

### Files

```
src/llm_mirror/        # per D13
tests/                 # pure-logic tests only
sessions/  logs/       # gitignored outputs
pyproject.toml .python-version
```

## Error handling & logging summary

- HTTP: retry policy per D11; all failures surface in the TUI, then PAUSED.
- Parsing: label/quote stripping per D4; one retry on empty content, then pause.
- Threads: worker exceptions are caught, logged, and converted to PAUSED + error line; the input loop is crash-proof.
- KeyboardInterrupt: caught once, saves, exits 0. Second Ctrl+C force-quits without waiting.
- `logs/mirror.log`: `RotatingFileHandler` (1 MB × 3). INFO: startup config, per-request one-liners (turn, tokens, cached, latency), commands, errors. DEBUG: truncated request/response bodies.

## Out of scope (reach goals — recorded, not built)

1. Two different models (schema already carries per-participant `model`; rendering stays canonical; cache simply won't apply cross-model).
2. Pretty in-TUI metrics dashboard (oMLX dashboard covers monitoring meanwhile).
3. Embedding-based collapse detector + auto-pause (cosine ≥ 0.92, 3 turns; embedding model already served).
4. Streaming turns; private persona prompts; runtime grounding toggle; custom persona names; web UI; config file; mid-request abort.

## Unchanged

Greenfield — no pre-existing code. Everything above is new; nothing is removed or migrated.
