# TUI Threading and Rendering Fix — Implementation Plan

- Design (ground truth, all decisions final): `docs/design/tui-threading-fix-design.md`
- Roadmap ticket: `roadmap/bugs/tui-threading-fix.md`
- Plan type: standalone, 1 phase, 4 tasks

## Executor contract (read first)

1. Read `docs/design/tui-threading-fix-design.md` fully before starting. Do not re-litigate, reinterpret, or "improve" any decision in it.
2. No code comments unless a later task explicitly asks for one. No docstrings beyond one line per public function. Type hints on all functions.
3. No new dependencies. `textual>=1.0` is already in `pyproject.toml`.
4. Logging writes to file only, never stdout (the TUI owns the terminal).
5. Run the gates after every task: `uv run ruff check .` and `uv run pytest` — both must pass before a task is "done".
6. Do not run sessions against the oMLX server — this is a pure TUI fix, no network calls needed.

### Environment facts (verified)

| Fact | Value |
|---|---|
| TUI framework | Textual (migrated from Rich, `textual>=1.0` in `pyproject.toml`) |
| TUI file | `src/llm_mirror/tui.py` — `Tui` class, currently broken |
| App file | `src/llm_mirror/app.py` — `MirrorApp` class, unchanged |
| Lock discipline | Worker thread acquires `MirrorApp._lock` for reads; main thread never acquires it |
| RichLog | `textual.widgets.RichLog`, `auto_scroll=True`, defers writes until `_size_known` is True |
| Reactive variables | `status`, `_total_prompt`, `_total_cached`, `_total_completion`, `_total_latency`, `_last_turn_text` |

---

## Phase 1 — Rewrite TUI threading model (single file: `tui.py`)

### Task 01 — Remove raw threading, add worker method and UI callback

**File:** `src/llm_mirror/tui.py`

**What:** Replace the raw `threading.Thread` + `self.run_async()` pattern with Textual's `@work(thread=True)` worker system.

Changes:
- Remove `import threading` (no longer needed — worker lifecycle is managed by Textual)
- Remove `import time` (no longer needed — worker uses `@work` loop)
- Remove `self._lock` from `__init__` (no longer needed — lock discipline moved to worker)
- Remove `self._refresh_thread: threading.Thread | None` from `__init__`
- Remove `on_unmount()` (worker auto-cancels, no manual join needed)
- Replace `on_mount()` body: `self.run_worker(self.refresh_worker())` instead of raw thread start
- Add `refresh_worker()` method: decorated with `@work(thread=True)`, replaces `_refresh_loop()`
- Add `_schedule_ui_update(data_dict: dict)` method: main-thread callback, replaces `_update_display()`
- Remove `_refresh_loop()` and `_on_refresh()` (superseded by `refresh_worker()`)

Interface contract for new methods:

```python
@work(thread=True)
async def refresh_worker(self) -> None
```

```python
def _schedule_ui_update(self, data: dict) -> None
```

**Why:** The design doc identifies 3 critical blockers: raw threads violate Textual's thread safety, reactive variables are assigned from a background thread, and RichLog writes happen from the wrong thread. This task establishes the correct threading foundation.

**Validation:**
- `uv run ruff check .` passes (no new errors)
- `uv run pytest` passes (109 tests, all unchanged `parse_input`/`ParsedInput` tests)
- No import errors when importing `Tui` class
- `on_mount()` calls `self.run_worker(self.refresh_worker())`
- `on_unmount()` is removed
- `_refresh_loop()`, `_on_refresh()`, `_update_display()` are removed
- `refresh_worker()` and `_schedule_ui_update()` exist with correct signatures

### Task 02 — Implement refresh_worker data collection with lock discipline

**File:** `src/llm_mirror/tui.py`

**What:** Implement `refresh_worker()` body following the design's lock discipline: worker acquires app locks, collects data into local dict, releases locks, then schedules UI update.

Changes to `refresh_worker()`:
- Infinite `while True` loop with `await asyncio.sleep(0.5)` (use `asyncio`, not `time.sleep`, since this is an async worker)
- Call `self._app.stats()` — acquires `MirrorApp._lock` internally, returns `SessionStats`
- Call `self._app.last_turn` — acquires `MirrorApp._lock` internally, returns `SessionStats | None`
- Read `self._app.status` — no lock needed (property, thread-safe read)
- Build local dict `data` with keys: `status`, `prompt_tokens`, `cached_tokens`, `completion_tokens`, `latency_ms`, `last_turn_text`, `messages`
- Read `self._app._state.messages` under `self._app._lock` (not `self._lock` from `__init__` — that lock is removed)
- Format messages into `Text` objects using `_format_message()` (unchanged helper)
- Call `self.call_from_thread(self._schedule_ui_update, data)` — schedules main-thread callback

Interface contract:

```python
@work(thread=True)
async def refresh_worker(self) -> None:
    # Pseudocode:
    # while True:
    #     await asyncio.sleep(0.5)
    #     stats = self._app.stats()
    #     last = self._app.last_turn
    #     status = self._app.status
    #     with self._app._lock:
    #         msgs = list(self._app._state.messages) if self._app._state else []
    #     data = {
    #         "status": status,
    #         "prompt_tokens": stats.prompt_tokens,
    #         "cached_tokens": stats.cached_tokens,
    #         "completion_tokens": stats.completion_tokens,
    #         "latency_ms": stats.mean_latency_ms,
    #         "last_turn_text": f"last: {last.turns}toks in {last.duration_s:.1f}s" if last and last.turns > 0 else "",
    #         "messages": msgs,
    #     }
    #     self.call_from_thread(self._schedule_ui_update, data)
```

**Why:** The design's lock discipline requires the worker to acquire `MirrorApp._lock` for reads, copy data into a local dict, then release the lock before scheduling UI updates. This eliminates lock contention between worker and main thread.

**Validation:**
- `uv run ruff check .` passes
- `uv run pytest` passes
- `refresh_worker()` uses `await asyncio.sleep(0.5)` (not `time.sleep`)
- `refresh_worker()` calls `self._app.stats()`, `self._app.last_turn`, `self._app.status`
- `refresh_worker()` accesses `self._app._state.messages` under `self._app._lock`
- `refresh_worker()` calls `self.call_from_thread(self._schedule_ui_update, data)`
- `asyncio` imported at top of file

### Task 03 — Implement _schedule_ui_update with RichLog deferred rendering handling

**File:** `src/llm_mirror/tui.py`

**What:** Implement `_schedule_ui_update(data_dict)` as a main-thread callback that updates reactive variables and writes to RichLog.

Changes to `_schedule_ui_update()`:
- Query `transcript = self.query_one("#transcript", RichLog)`
- Check `transcript._size_known` — if False, return early (RichLog not ready, will flush deferred renders on first resize)
- Update reactive variables from `data` dict: `self.status = data["status"]`, `self._total_prompt = data["prompt_tokens"]`, etc.
- Format messages from `data["messages"]` using `_format_message()` (unchanged helper)
- Write only the last 10 messages (same logic as current `_update_display()`)
- Write status line using formatted text with token counts and status
- All writes happen on main thread, no lock acquisition needed

Interface contract:

```python
def _schedule_ui_update(self, data: dict) -> None:
    # Pseudocode:
    #     transcript = self.query_one("#transcript", RichLog)
    #     if not transcript._size_known:
    #         return
    #     self.status = data["status"]
    #     self._total_prompt = data["prompt_tokens"]
    #     self._total_cached = data["cached_tokens"]
    #     self._total_completion = data["completion_tokens"]
    #     self._total_latency = data["latency_ms"]
    #     self._last_turn_text = data["last_turn_text"]
    #     msgs = data["messages"]
    #     start = max(0, len(msgs) - 10)
    #     for msg in msgs[start:]:
    #         formatted = _format_message(msg)
    #         if formatted.plain:
    #             transcript.write(formatted)
    #     status_text = Text(f"\n[prompt {data['prompt_tokens']} · cached {data['cached_tokens']} · {data['completion_tokens']} toks · {data['status'].value}]")
    #     transcript.write(status_text)
```

**Why:** This is the main-thread callback scheduled via `call_from_thread()`. It updates reactive variables (main-thread-only) and writes to RichLog (main-thread-only). The `_size_known` check handles RichLog's deferred rendering behavior.

**Validation:**
- `uv run ruff check .` passes
- `uv run pytest` passes
- `_schedule_ui_update()` queries RichLog widget
- `_schedule_ui_update()` checks `transcript._size_known` before writing
- `_schedule_ui_update()` updates all reactive variables from data dict
- `_schedule_ui_update()` writes last 10 messages to RichLog
- `_schedule_ui_update()` writes status line with token counts

### Task 04 — Verify threading model end-to-end

**File:** `src/llm_mirror/tui.py`

**What:** Final verification pass. Ensure all threading-related code follows the design's lock discipline and Textual patterns.

Checks:
- No `threading.Thread` usage in `Tui` class
- No `self.run_async()` calls
- No reactive variable assignment outside `_schedule_ui_update()`
- No `RichLog.write()` calls outside `_schedule_ui_update()`
- `refresh_worker()` uses `@work(thread=True)` decorator
- `refresh_worker()` uses `await asyncio.sleep()` (not `time.sleep()`)
- `refresh_worker()` acquires `self._app._lock` (not `self._lock`) for message reads
- `on_mount()` starts worker via `self.run_worker(self.refresh_worker())`
- `on_unmount()` is removed
- `_refresh_loop()`, `_on_refresh()`, `_update_display()` are removed
- `_format_message()` helper is unchanged
- `parse_input()`, `ParsedInput` are unchanged
- `compose()`, `on_input_submitted()`, `action_*` methods are unchanged
- `import threading` removed (no longer needed)
- `import time` removed (no longer needed)
- `import asyncio` added (needed for `await asyncio.sleep()`)

**Why:** This is the final verification step. No code changes beyond what's required by the previous tasks — just ensure correctness.

**Validation:**
- `uv run ruff check .` passes (no new errors, no removed imports causing issues)
- `uv run pytest` passes (109 tests)
- Manual verification: all threading patterns match design doc
- No `threading.Thread`, `self.run_async()`, `time.sleep()` in `Tui` class
- `asyncio` imported, `await asyncio.sleep()` used in `refresh_worker()`
- Lock discipline: worker uses `self._app._lock`, main thread never acquires it

---

## Status

completed
