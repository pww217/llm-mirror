# Mirror Chat MVP — Implementation Plan

- Design (ground truth, all decisions final): `docs/design/mirror-chat-design.md`
- Roadmap ticket: `roadmap/features/mirror-chat-mvp.md`
- Plan type: standalone, 6 phases, tasks ordered by dependency

## Executor contract (read first)

1. Read `docs/design/mirror-chat-design.md` fully before starting. Do not re-litigate, reinterpret, or "improve" any decision in it. If source and this plan appear to conflict, the design doc wins; stop and flag instead of improvising.
2. Where a task says "copy VERBATIM from the design doc, section X", open the file, find the section, and copy the text exactly — no paraphrasing, no reflowing, no reordering. Byte-exact prompts are the core of this project (KV cache correctness depends on them).
3. No code comments unless a later task explicitly asks for one. No docstrings beyond one line per public function. Type hints on all functions.
4. No new dependencies beyond `httpx` and `rich` (runtime) and `ruff`/`pytest` (dev). No network calls in tests — use `httpx.MockTransport` and fake objects.
5. Logging writes to file only, never stdout (the TUI owns the terminal).
6. Run the gates after every task: `uv run ruff check .` and `uv run pytest` — both must pass before a task is "done".
7. Do not run sessions against the oMLX server except in Task 12 (smoke test), which requires the live server.

### Environment facts (verified)

| Fact | Value |
|---|---|
| Server | oMLX 0.7.0rc1 at `http://localhost:8000` (OpenAI-compatible; `/health`, `/v1/models`, `/v1/chat/completions`) |
| Default model | `mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit` — but always read `default_model` from `GET /health` at runtime; fall back to first `/v1/models` entry if `/health` fails |
| `max_model_len` | 262144 for chat models — read per-model from `/v1/models` at runtime |
| Cache telemetry | `usage.prompt_tokens_details.cached_tokens` in every chat response; treat missing field as `0` |
| Toolchain | `uv` 0.12.19 provisions Python 3.13; macOS arm64 |
| Unknown (verify in Task 12) | whether the default model emits `<think>...</think>` blocks in `content` — the client must strip them regardless |

---

## Phase 1 — Scaffold and prompt contract (pure core, no I/O)

### Task 01 — Project scaffold

**File:** `pyproject.toml`, `.python-version`, `.gitignore`, `src/llm_mirror/__init__.py`, `tests/__init__.py`

**What:** Create exactly this project shape. `pyproject.toml` content (verbatim):

```toml
[project]
name = "llm-mirror"
version = "0.1.0"
description = "Two personas of one local model, talking to each other"
requires-python = ">=3.13"
dependencies = ["httpx>=0.28", "rich>=13"]

[project.scripts]
llm-mirror = "llm_mirror.main:main"

[dependency-groups]
dev = ["ruff", "pytest"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/llm_mirror"]
```

`.python-version` content: `3.13` (one line).
`.gitignore` entries (one per line): `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `dist/`, `sessions/`, `logs/`.
Both `__init__.py` files: empty.

**Why:** Everything else depends on a runnable package with lint/test gates.

**Validation:** `uv sync` succeeds and provisions Python 3.13; `uv run python -c "import llm_mirror"` exits 0; `uv run ruff check .` reports no findings.

### Task 02 — Persona and scenario constants

**File:** `src/llm_mirror/personas.py`, `tests/test_personas.py`

**What:** Define:

```python
ECHO_CARD: str
MIRROR_CARD: str
GROUNDING_CLAUSES: tuple[str, str]
SCENARIO_GROUNDED: str
SCENARIO_FREE: str
SEED_TOPICS: list[str]
```

- `ECHO_CARD` and `MIRROR_CARD`: the exact card paragraphs from the design doc section "Prompt contract (exact text)" (the lines starting `Echo: warm, curious...` and `Mirror: skeptical and precise...`). Copy VERBATIM, including the "Not hostile — rigorous." em-dash sentence.
- `GROUNDING_CLAUSES`: the two sentences `"Stay on the conversation's topic."` and `"Do not comment on being an AI, on the format, or on the conversation itself."`
- Build `SCENARIO_GROUNDED` by string composition from the design doc's exact scenario text; `SCENARIO_FREE` MUST equal `SCENARIO_GROUNDED` with both `GROUNDING_CLAUSES` sentences removed (compose from shared parts so this holds by construction).
- `SEED_TOPICS`: exactly 30 unique strings, each a constrained-but-open discussion topic in this style: `"whether cities should ban private cars downtown"`, `"whether chess is a solved game in principle"`, `"what makes a scientific instrument trustworthy"`, `"whether remote work weakens mentorship"`, `"whether analog synthesizers still matter"`. Draft the remaining 25 in the same register: concrete, debatable, two-sided, never open-ended like "anything you want".

**Why:** These constants are the byte-stable content the prompt renderer composes; the cache contract depends on them never varying mid-session.

**Validation:** `uv run pytest` — tests assert: `SCENARIO_FREE == SCENARIO_GROUNDED` with each grounding clause removed; `len(SEED_TOPICS) == 30`; no duplicates; `ECHO_CARD.startswith("Echo:")` and `MIRROR_CARD.startswith("Mirror:")`.

### Task 03 — Prompt renderer (pure functions)

**File:** `src/llm_mirror/prompt.py`, `tests/test_prompt.py`

**What:** Implement exactly these public definitions:

```python
@dataclass(frozen=True)
class Message:
    speaker: str  # "echo" | "mirror" | "user"
    content: str

def speaker_label(speaker: str) -> str: ...
def render_system(echo_card: str, mirror_card: str, free: bool) -> str: ...
def render_transcript(messages: Sequence[Message]) -> str: ...
def render_tail(speaker: str, opening: bool) -> str: ...
def render_user_message(messages: Sequence[Message], opening: bool) -> str: ...
def strip_reply(content: str, speaker: str) -> str: ...
```

Exact semantics:

- `speaker_label`: `"echo"→"Echo"`, `"mirror"→"Mirror"`, `"user"→"User"`; anything else raises `ValueError`.
- `render_system(echo_card, mirror_card, free)`: the design doc's scenario text (VERBATIM copy from section "Prompt contract (exact text)") with the card paragraphs swapped for the two card arguments, and with both grounding clauses removed when `free=True`. Card arguments land exactly where the built-in cards sit; all other lines unchanged.
- `render_transcript`: `"\n".join(f"{speaker_label(m.speaker)}: {m.content}" for m in messages)`; empty sequence → `""`.
- `render_tail`: verbatim from the design doc:
  - regular: `f"The next message is from {label}. Write only {label}'s next message text (no name label), in character."`
  - opening (`opening=True`): `"This is the opening of the conversation. The next message is from Echo. Write only Echo's message text (no name label), in character."`
- `render_user_message`: `render_transcript(messages) + "\n\n" + render_tail(next_speaker, opening)`. Empty transcript and `opening=True` → just the tail.
- `strip_reply(content, speaker)`: apply in order — (1) remove any `<think>...</think>` block (non-greedy, DOTALL; also the degenerate case of a lone opening `<think>` with no close: drop everything before a closing `</think>` if present, else if `<think>` occurs, drop from it to the end of content if no closing tag exists); (2) strip leading whitespace; (3) remove a leading `f"{label}:"` or `f"{label} —"` prefix if present, then leading whitespace again; (4) strip matching surrounding double quotes; (5) strip trailing whitespace. Return the result (possibly `""`).

**Why:** This module is the cache-critical contract; everything downstream composes it. It must be pure (no I/O) so tests prove byte-identity.

**Validation:** `uv run pytest` — tests must cover: byte-identity (same inputs → identical strings, twice); `free` variant differs from grounded by exactly the two clauses; card override replaces only the card paragraphs; transcript joining incl. seed line `"User: Topic: {seed}."`; both tails verbatim; `strip_reply` cases: think block, think-only, leading `Echo:` label, surrounding quotes, whitespace, empty string.

---

## Phase 2 — Session persistence (pure-ish I/O, no network)

### Task 04 — Session store, events, resume

**File:** `src/llm_mirror/session.py`, `tests/test_session.py`

**What:** Implement exactly:

```python
@dataclass(frozen=True)
class Sampling:
    temperature: float = 0.8
    max_tokens: int = 300
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

@dataclass
class SessionMeta:
    model: str
    base_url: str
    scenario: str  # "grounded" | "free"
    echo_card: str
    mirror_card: str
    sampling: Sampling
    seed: str | None
    max_model_len: int

@dataclass
class SessionState:
    meta: SessionMeta
    messages: list[Message]  # from prompt.py
    next_speaker: str       # "echo" | "mirror"

@dataclass(frozen=True)
class TurnUsage:
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int

class SessionStore:
    def __init__(self, path: Path) -> None: ...
    def append_event(self, event: dict) -> None: ...
    def write_markdown(self, state: SessionState) -> None: ...

def new_session_path(session_dir: Path, seed: str | None) -> Path: ...
def load_session(path: Path) -> SessionState: ...
```

Exact rules:

- `append_event`: append one `json.dumps(event)` line + `"\n"` immediately, flush. Event shapes are FINAL from the design doc section "JSONL event schema" — common envelope `{"ts": ISO-8601 UTC, "type": ...}` plus per-type fields. `type: "session"` also carries `participants: {"echo": {"card": ...}, "mirror": {"card": ...}}`, `sampling`, `seed`, `model`, `base_url`, `scenario`, `max_model_len`. `type: "turn"` carries `speaker`, `model`, `content`, `usage`, `latency_ms`, `sampling`. `type: "injection"` carries `target` (`"ambient"|"echo"|"mirror"`) and `content`. `type: "control"` carries `action` and `detail`.
- `write_markdown`: header block (session metadata as a small key-value list), then per message one paragraph `f"**{speaker_label(m.speaker)}:** {m.content}"` separated by blank lines and a `---` rule between turns. Derived from state only. Path = JSONL path with suffix `.md`.
- `new_session_path`: `session_dir / f"{YYYYMMDD-HHMMSS}-{slug}.jsonl"`, UTC timestamp; slug from seed: lowercase, non-alphanumerics → `-`, collapse repeats, max 6 dash-separated words, `"unseeded"` when seed is `None`.
- `load_session`: replay events in order into `SessionState`. Reconstruction rules: `session` event → meta; `turn` → append `Message(speaker, content)`; `injection` → append `Message("user", content)` and — if target is `"echo"` or `"mirror"` — set `next_speaker` to it; `control` events are ignored for state. After replay, if no injection set it: `next_speaker` = `"mirror"` if last model message is Echo, `"echo"` otherwise (covers empty transcripts). Malformed JSON line → raise `SessionCorruptedError` (subclass of `Exception`) with the line number.

**Why:** JSONL is the single source of truth; resume correctness is an acceptance criterion.

**Validation:** `uv run pytest` — round-trip (build events → `load_session` → identical messages/meta/next_speaker); next-speaker rule cases (empty, echo-last, mirror-last, ambient injection preserves rotation, targeted injection overrides); MD golden-file comparison; slug rule cases; corrupted-file error.

---

## Phase 3 — oMLX client (isolated HTTP)

### Task 05 — Client with retries and telemetry

**File:** `src/llm_mirror/client.py`, `tests/test_client.py`

**What:** Implement exactly:

```python
class TransientOmlxError(Exception): ...
class OmlxClientError(Exception): ...

@dataclass(frozen=True)
class ChatRequest:
    model: str
    system: str
    user: str
    temperature: float
    max_tokens: int
    frequency_penalty: float
    presence_penalty: float

@dataclass(frozen=True)
class TurnResult:
    content: str
    usage: TurnUsage  # from session.py
    latency_ms: int

class OmlxClient:
    def __init__(self, base_url: str, timeout: httpx.Timeout, sleep=time.sleep) -> None: ...
    def health(self) -> dict: ...
    def models(self) -> list[dict]: ...
    def chat(self, req: ChatRequest) -> TurnResult: ...
```

Exact rules:

- Default `timeout = httpx.Timeout(connect=5.0, read=600.0, write=10.0, pool=5.0)`. `sleep` is injectable for tests.
- `health()` → `GET {base_url}/health` JSON body. `models()` → `GET {base_url}/models` → `data` list. Both: no retry (startup checks fail fast with `OmlxClientError`).
- `chat()` → `POST {base_url}/chat/completions` with JSON body `{"model", "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": req.user}], "temperature", "max_tokens", "frequency_penalty", "presence_penalty"}`.
- Retry policy: on `httpx.ConnectError`, `httpx.TimeoutException`, HTTP 5xx, or HTTP 429 → retry, max 3 attempts total, backoff 1s, 2s, 4s via `sleep`; after the 3rd failure raise `TransientOmlxError` chained to the last exception. Any other 4xx → `OmlxClientError` immediately, no retry.
- Success: `content = data["choices"][0]["message"]["content"]`; apply `prompt.strip_reply`'s think-tag removal (step 1 only, label/quote stripping stays in the app); `usage` from `data["usage"]` with `prompt_tokens_details.cached_tokens` defaulting to `0`; `latency_ms` measured around the request. Missing/malformed fields → `OmlxClientError`.

**Why:** The retry taxonomy (transient vs fatal) drives whether the app pauses-and-resumes or surfaces a hard error.

**Validation:** `uv run pytest` with `httpx.MockTransport`: success (usage + latency extracted, think block stripped); 429-then-200 with recorded sleep calls; connect-error ×3 → `TransientOmlxError`; 500 ×3 → same; 400 → `OmlxClientError` with no sleep calls; missing `prompt_tokens_details` → `cached_tokens == 0`; truncated body → `OmlxClientError`.

---

## Phase 4 — App orchestration (state machine, threads)

### Task 06 — MirrorApp

**File:** `src/llm_mirror/app.py`, `tests/test_app.py`

**What:** Implement exactly:

```python
class AppStatus(Enum):
    RUNNING, PAUSED, STOPPED  # auto(): RUNNING=1, PAUSED=2, STOPPED=3

@dataclass
class SessionStats:
    turns: int
    per_speaker: dict[str, int]
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cache_hit_pct: float
    mean_latency_ms: float

class MirrorApp:
    def __init__(self, client, store, state: SessionState, max_turns: int = 0,
                 ctx_guard_pct: float = 0.9) -> None: ...
    def start(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def quit(self) -> None: ...
    def save(self) -> None: ...
    def inject(self, text: str) -> None: ...
    def stats(self) -> SessionStats: ...
    @property
    def status(self) -> AppStatus: ...
```

Exact rules:

- Threading: `start()` spawns one daemon worker thread. `inject()`/commands are called from the main thread only. Pause = `threading.Event` cleared; the worker checks it at the top of each turn iteration and blocks on it while PAUSED. `quit()` sets STOPPED and joins the worker with timeout 5s.
- Injection queue: `queue.Queue`. `inject(text)` parses a leading `@Echo:`/`@Mirror:`/`@echo:`/`@mirror:` prefix → target, else `"ambient"`; text without target → `Message("user", text)`; appends an `injection` event to the JSONL immediately; if PAUSED, applies to `state.messages` immediately (and sets `next_speaker` when targeted); if RUNNING, enqueues — the worker drains the queue at each turn boundary and applies before building the next request. Input is never lost.
- Worker turn (single iteration, in order): (1) if STOPPED → exit loop; wait while paused; (2) drain injection queue into `state.messages`; (3) build request via `prompt.render_system/render_user_message` from meta + messages (opening flag = no model messages yet); (4) `client.chat(...)`; (5) `content = prompt.strip_reply(result.content, next_speaker)`; if empty → one retry of step 4; if still empty → append `control` event `action="empty_reply"`, set PAUSED, return to wait; (6) append `Message(next_speaker, content)` to state, append `turn` event (speaker, model, content, usage, latency_ms, sampling), `store.write_markdown(state)`; (7) flip `next_speaker`; (8) context guard: if `sum of prompt_tokens of last turn >= ctx_guard_pct * meta.max_model_len` → append `control` event `action="auto_pause_context"` and set PAUSED; (9) `max_turns > 0` and turn count ≥ max_turns → append `control` event `action="auto_pause_max_turns"` and set PAUSED.
- Error handling: worker catches `TransientOmlxError`/`OmlxClientError`/any `Exception` → log (module logger, `logger.exception`), append `control` event `action="error"` with `detail=str(e)[:300]`, set PAUSED. The worker thread never dies from an exception; PAUSED waits are interruptible by `quit()`.
- `stats()` computed from the in-memory turn records (keep a `list[TurnResult]`-shaped history alongside state): totals, per-speaker counts, `cache_hit_pct = 100 * cached / prompt` (0 when prompt is 0), mean latency.
- Every state transition and command appends its `control` event (`startup`, `pause`, `resume`, `save`, `quit`).

**Why:** The turn loop is the product; its ordering rules (drain → build → call → persist → flip) keep the transcript atomic and the rotation correct.

**Validation:** `uv run pytest` with a `FakeClient` (scripted results incl. empty-then-good, transient error, and a usage sequence) and a temp-dir store: rotation echo→mirror→echo; queued injection lands between turns and in order; targeted injection forces speaker; ambient injection preserves rotation; empty reply retries once then pauses; transient error pauses with control event; context guard triggers at threshold; max_turns stops; `quit()` from PAUSED exits cleanly; no exception escapes the worker.

---

## Phase 5 — TUI, entry point, live smoke test

### Task 07 — TUI

**File:** `src/llm_mirror/tui.py`, `tests/test_tui.py`

**What:** Implement:

```python
@dataclass(frozen=True)
class ParsedInput:
    command: str | None   # lowercase name without "/", e.g. "pause", or None
    injection_target: str  # "ambient" | "echo" | "mirror" | "" when command is not None
    content: str

def parse_input(raw: str) -> ParsedInput: ...
```

`parse_input` exact rules: `raw.strip()`; if empty → command `None`, content `""` (caller ignores); if starts with `/` → split first token, lowercase → `command`, rest (if any) → `content`; command must be one of `{"pause","resume","quit","save","stats","transcript","help"}` else `command="help"` with a note? NO — unknown `/x` → `command=None`, `content=raw` (it flows to injection as ordinary text is wrong — see design D8: "Unknown /x → error line, no side effects"). So: unknown slash-command → `command="unknown"`, content = the token; the caller prints an error line and does nothing. Non-slash text → injection: leading `@Echo:`/`@Mirror:` (case-insensitive, optional space after colon) → target, remainder → content.

Then the TUI class:

```python
class Tui:
    def __init__(self, app: MirrorApp, store, session_id: str, model: str) -> None: ...
    def run(self) -> None: ...
```

- `rich.live.Live` with a `Layout`: header line (status chip `[RUNNING]`/`[PAUSED]`, turn count, model, session id); transcript viewport showing the last 10 messages, colors: Echo cyan, Mirror magenta, User yellow bold, prefix `Name:`; footer: last turn `prompt {p} · cached {c} ({pct}%) · {ms}ms` + totals. Input line is printed BELOW the Live area by the main loop (`input()` with prompt `> `), then the Live refreshes.
- Main loop: read line → `parse_input` → dispatch: commands call app methods (`/stats` prints the stats table via `rich.table`, `/transcript` pages the stored markdown via `rich.console.Console().pager()`, `/help` prints the command list); injections call `app.inject(...)`; unknown command → red error line. `KeyboardInterrupt` → call `app.quit()`, save, exit. Every dispatch re-renders.
- On app status changes visible only via polling between inputs: when the worker pauses/errors, it sets a thread-safe callback the Tui registered (`app.on_state_change = callback`) — simplest mechanism: the app exposes `status` and the Tui refreshes the Live panel on a 0.5s `rich` timer thread; worker side does NOT print.

**Why:** The TUI must stay alive and readable while the worker streams turns; input handling must never block the worker.

**Validation:** `uv run pytest` — `parse_input` table tests (all 7 commands, unknown slash, @Echo:/@mirror: with/without space, ambient, empty). `uv run ruff check .` clean. Live behavior verified in Task 09.

### Task 08 — CLI entry point

**File:** `src/llm_mirror/main.py`

**What:** `main()` with `argparse` exactly per design doc section "CLI" (flag names, types, defaults — copy the table; `--prompt` is `str`, `--no-seed`/`--free` are store-true flags, `--resume` choices-free str). Logic in order:

1. If `--resume` and `--prompt` → print error "`--prompt conflicts with --resume`", exit code 2.
2. Build `OmlxClient(base_url)`; startup checks: `health()` → default model (unless `--model`); `models()` → `max_model_len` for the chosen model. On `OmlxClientError`/connection failure → friendly one-line message ("Is oMLX running on {base_url}?"), exit 1. Log every choice at INFO.
3. Session setup: `--resume PATH|latest` → `load_session()` (`latest` = newest `*.jsonl` in `--session-dir`; none → same exit-1 path with message). New session → seed = `--prompt` if given, else `random.choice(SEED_TOPICS)` unless `--no-seed` (seed `None`); if seed is not None, prepend `Message("user", f"Topic: {seed}.")`. Build `SessionMeta` from flags (`--echo-prompt`/`--mirror-prompt` default to the built-in cards; `--temp`/`--max-tokens`/penalties into `Sampling`), `new_session_path()`, `SessionStore`, write the `session` event.
4. Wire `MirrorApp` + `Tui`, `app.start()`, `Tui.run()`. On exit: `save` control event, `write_markdown`, exit 0. Top-level `except Exception` → log + stderr one-liner + exit 1 (but the TUI loop should have caught everything already).
5. File logging: `logging` root logger → `logs/mirror.log` (`RotatingFileHandler` 1 MB, 3 backups), format `%(asctime)s %(levelname)s %(name)s %(message)s`, level from `--log-level`. No console handler ever.

**Why:** This is the only module that knows all the pieces; wiring order is the contract.

**Validation:** `uv run llm-mirror --help` prints the full flag table; `uv run llm-mirror --resume latest --prompt x` exits 2 with the conflict message; with the server stopped, startup exits 1 with the friendly message.

### Task 09 — Live smoke test + cache acceptance check

**File:** none (procedure; record results in the roadmap ticket)

**What:** Requires the live oMLX server. Run in order and record outcomes:

1. `uv run llm-mirror --prompt "whether cities should ban private cars downtown" --max-turns 4` → confirm: 4 model turns alternate Echo/Mirror; TUI shows turns live; `/stats` shows cache %; `/transcript` pages; Ctrl+C exits 0 and files exist under `sessions/` (`.jsonl` + `.md`).
2. Same session: `--resume latest` → transcript continues with 4 more turns (`--max-turns 4` again) and rotation continues from the correct speaker.
3. Cache acceptance check on a 20-turn run (`--max-turns 20`, any seed): from turn ≥ 3, `cached_tokens >= prompt_tokens - tokens(last message) - tokens(tail) - 256`. Compute with: `uv run python - <check script>` reading the session JSONL (write the check script inline, print pass/fail per turn). Record numbers in the roadmap ticket.
4. Injection: start a session, type a plain line mid-conversation (queue → lands at next boundary), then `/pause`, type `@Echo: what about freight?` (immediate), `/resume`.
5. `--no-seed` (unseeded opening turn) and `--free` (spiral watch) each run 5 turns without error.

**Why:** Acceptance criteria 1–6 of the roadmap ticket are verified here; the cache check is the experiment's core claim.

**Validation:** All five steps behave as specified; `uv run ruff check .` and `uv run pytest` still green.

---

## Phase 6 — Documentation and roadmap

### Task 10 — AGENTS.md and docs

**File:** `AGENTS.md`, `docs/repomap.md`, `docs/architecture/mirror-chat.md`

**What:**
- `AGENTS.md`: build/test commands (`uv sync`, `uv run ruff check .`, `uv run pytest`, `uv run llm-mirror --help`), module map (7 modules, one line each per design D13), conventions (type hints, no comments, file-only logging, PEP 8/ruff default), and the load-bearing invariant as a warning: "The prompt contract is byte-stable — never vary `render_system` inputs mid-session; KV-cache correctness depends on it."
- `docs/repomap.md`: module boundaries + public API signatures from Tasks 02–07.
- `docs/architecture/mirror-chat.md`: pipeline flow diagram (input → parse → app queue → turn loop → prompt render → client → oMLX → JSONL/MD → TUI), JSONL event data shapes, stage contracts (one section per module boundary).

**Why:** The plan skill requires these; future sessions (and the wrap-up flow) depend on them.

**Validation:** Files exist and match the shipped code (spot-check every signature listed).

### Task 11 — Roadmap ticket closure

**File:** `roadmap/features/mirror-chat-mvp.md`

**What:** Tick all acceptance checkboxes backed by Task 09 evidence; set `status: done`; append smoke-test numbers (cache acceptance per-turn figures) under Notes.

**Validation:** Every acceptance criterion has either a checkbox tick with evidence or a written exception.

---

## Dependency order

`01 → 02 → 03` (Phase 1) → `04` → `05` → `06` → `07 → 08 → 09` → `10 → 11`. Phases 2 and 3 are independent of each other (both depend only on Phase 1); Phase 4 depends on 2+3; Phase 5 on 4; Phase 6 last.

## Out of scope (do not build)

Per design doc "Out of scope": second model per participant, metrics dashboard, embedding collapse detector, streaming, private persona prompts, runtime grounding toggle, custom names, web UI, config file, mid-request abort.
