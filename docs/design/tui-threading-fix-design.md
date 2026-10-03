# TUI Threading and Rendering Fix

---
status: implemented
reviewed_at: 2026-10-01
review_verdict: accepted (all blockers auto-fixed)
review_blockers: 3 critical (lock contention, reactive thread safety, RichLog deferred rendering)
review_auto_fixed: 7 (all blockers + ambiguities resolved)
review_ambiguities: 0
---

## Problem

The Textual TUI (`tui.py`) does not render conversation messages, does not update the transcript, and most commands appear non-functional. The oMLX backend processes conversations correctly (visible in logs), but the UI layer is completely disconnected from the rendering pipeline.

## Root Cause Analysis

### 1. Thread Safety Violation (Critical)

The `_refresh_loop()` method runs in a raw `threading.Thread` and calls `self.run_async(self._update_display)` from that thread. This violates Textual's thread safety rules:

- `run_async()` is not designed to be called from background threads
- `_update_display()` calls `transcript.write()` directly, which is not thread-safe
- Textual documentation explicitly states: "avoid calling methods on your UI directly from a threaded worker"

The correct pattern is:
- Use `@work(thread=True)` decorator for threaded workers, OR
- Use `self.call_from_thread(widget.method, args)` to schedule UI updates from threads, OR
- Use `post_message()` with custom messages (thread-safe) and let message handlers update the UI

### 2. Shared State Lock Contention (Critical)

`MirrorApp.stats()` (`app.py:136`) acquires `self._lock` to read token counters. `_update_display()` (`tui.py:151`) also acquires `self._lock` to copy `self._app._state.messages`. Both methods are called from different threads (worker thread vs. main thread via `call_from_thread`). If the worker holds the lock while calling `call_from_thread()`, and the main thread's `call_from_thread` callback tries to acquire the lock, the UI will hang. The design must serialize all shared-state access through a single thread (the main thread) or use a separate lock for UI reads.

### 3. Reactive Variable Thread Safety (Critical)

Textual reactive variables (`status`, `_total_prompt`, etc.) must be updated from the main thread only. `_on_refresh()` runs in the background thread and currently assigns to them directly (`tui.py:139-148`). This is undefined behavior. All reactive updates must be scheduled on the main thread via `self.call_from_thread()` or by posting a custom message.

### 4. RichLog Deferred Rendering (Critical)

RichLog has a `_size_known` flag that defers all `write()` calls until the widget is sized (Textual source: `_rich_log.py:147-152`). If the worker thread calls `call_from_thread(transcript.write, ...)` before the DOM is fully laid out, writes are silently queued in `_deferred_renders` and never appear. The worker must wait for layout completion, or the design must accept that the first N writes may be deferred until the first `on_resize`.

### 5. Worker Lifecycle Management

The current implementation uses a raw `threading.Thread` with no integration with Textual's worker lifecycle. This means:
- No cancellation on app exit
- No error handling through Textual's worker system
- No state change notifications

### 6. Command Handling

Commands handled in `on_input_submitted()` call `self._app.pause()`, `self._app.resume()`, etc. directly. These should work, but the UI never updates to reflect state changes because the refresh loop is broken.

## Target State

### Architecture

```
MirrorApp (background thread: mirror-worker)
    |
    | _state.messages (shared, protected by self._lock)
    | stats() (acquires self._lock)
    |
Tui App (main thread: Textual event loop)
    |
    | @work(thread=True) refresh_worker()
    |   - Polls MirrorApp.stats() (acquires self._lock on app)
    |   - Reads MirrorApp._state.messages (acquires self._lock on app)
    |   - Collects data into local dict
    |   - Releases all locks before scheduling UI update
    |
    | _schedule_ui_update(data_dict) (main thread, called via call_from_thread)
    |   - Updates reactive variables (main thread only)
    |   - Updates RichLog via transcript.write() (main thread only)
    |
    | on_input_submitted() (main thread)
    |   - Handles commands
    |   - Calls MirrorApp methods directly (safe, no lock contention)
```

**Lock discipline:** The `self._lock` on `MirrorApp` is acquired by the worker thread for reads. The main thread never acquires it. All UI updates happen in `call_from_thread()` callbacks on the main thread, which read from the local data dict (not from shared state). This eliminates lock contention between the worker and the UI.

### Key Design Decisions

**DECISION 1: Use Textual's worker system instead of raw threads**

Replace the raw `threading.Thread` with `@work(thread=True)` decorator. This integrates with Textual's lifecycle, provides cancellation, and follows documented patterns.

**DECISION 2: Use call_from_thread for all UI updates**

All RichLog updates and reactive variable assignments must happen on the main thread. The worker thread collects data into a local dict, then calls `self.call_from_thread(self._schedule_ui_update, data_dict)` to schedule a main-thread callback. This callback updates reactives and calls `transcript.write()`.

**DECISION 3: Keep input handling synchronous**

The `on_input_submitted()` handler runs on the main thread and can call MirrorApp methods directly. No threading changes needed here.

**DECISION 4: Collect data in worker, update UI on main thread**

The worker thread reads `MirrorApp.stats()` and `MirrorApp._state.messages` under the app's lock, copies all data into a local dict, then releases the lock. It then calls `self.call_from_thread()` with the dict. The main-thread callback updates reactive variables and writes to RichLog. This eliminates lock contention because the main thread never acquires the app's lock.

**DECISION 5: Handle RichLog deferred rendering**

RichLog defers `write()` calls until `_size_known` is True. The worker thread must not call `call_from_thread()` until the RichLog widget is sized. This is handled by checking `transcript._size_known` in the first refresh cycle, and if not ready, deferring the first write until the next cycle (RichLog will flush deferred renders on first resize).

## Implementation Scope

### Files Changed

- `src/llm_mirror/tui.py` — Complete rewrite of threading model

### Files Unchanged

- `src/llm_mirror/app.py` — No changes needed
- `src/llm_mirror/main.py` — No changes needed
- `src/llm_mirror/client.py` — No changes needed
- `src/llm_mirror/session.py` — No changes needed
- `src/llm_mirror/prompt.py` — No changes needed
- `src/llm_mirror/personas.py` — No changes needed

### What Gets Removed

- Raw `threading.Thread` usage in `Tui`
- `self.run_async()` calls from background threads
- Direct UI updates from non-main threads

### What Gets Added

- `@work(thread=True)` decorated `refresh_worker()` method to replace `_refresh_loop()`
- `_schedule_ui_update(data_dict)` main-thread callback called via `self.call_from_thread()`
- Local data dict in worker to avoid holding app locks during UI updates
- RichLog `_size_known` check in first refresh cycle to handle deferred rendering
- Proper worker lifecycle management (`on_mount`, `on_unmount`)
- Custom message class for thread-safe state updates (optional, if `call_from_thread` proves insufficient)

## Interface Contracts

### Tui Class

**Constructor**: No changes
```python
def __init__(self, app: MirrorApp, store: SessionStore, session_id: str, model: str) -> None
```

**Methods**:
- `compose()` — No changes (already correct)
- `on_mount()` — Start worker: `self.run_worker(self.refresh_worker())`
- `on_unmount()` — Worker auto-cancels, no manual join needed
- `refresh_worker()` — NEW: `@work(thread=True)` decorated method, replaces `_refresh_loop()`. Polls app state into local dict, calls `self.call_from_thread(self._schedule_ui_update, data_dict)`
- `_schedule_ui_update(data_dict)` — NEW: main-thread callback. Updates reactive variables and calls `transcript.write()` from local data dict
- `_on_refresh()` — REMOVED (replaced by `refresh_worker()`)
- `_update_display()` — REMOVED (replaced by `_schedule_ui_update()`)
- `on_input_submitted()` — No changes
- `action_*` methods — No changes

### RichLog Widget

- All `write()` calls must happen on main thread via `_schedule_ui_update()` callback
- Worker thread collects data into local dict, releases app locks, then calls `call_from_thread()`
- First refresh cycle checks `transcript._size_known`; if False, skips write and retries next cycle

## Rejected Alternatives

### Alternative 1: Use post_message with custom messages

**Rejected because**: Adds unnecessary complexity. `call_from_thread()` is simpler for direct widget updates and is the recommended pattern for this use case per Textual documentation.

### Alternative 2: Use async workers instead of thread workers

**Rejected because**: The MirrorApp uses synchronous HTTP calls via `httpx` (not `httpx.AsyncClient`). Converting to async would require changes to `client.py`, `app.py`, and `main.py` — out of scope for this fix.

### Alternative 3: Keep raw threading.Thread but fix call_from_thread usage

**Rejected because**: Raw threads bypass Textual's worker lifecycle management. The `@work(thread=True)` decorator provides built-in cancellation, error handling, and state tracking that raw threads lack.

## Open Questions

[OPEN: Should we use RichLog or TextLog for the transcript?]

- `RichLog` supports Rich `Text` objects with styling (required for speaker color coding)
- `TextLog` is simpler but doesn't support rich styling
- Decision: Keep `RichLog` for styling support

[OPEN: Should we batch RichLog updates or update per-message?]

- Per-message updates are simpler but may cause excessive rendering
- Batch updates (collect messages in worker, update once on main thread) are more efficient
- Decision: Batch updates per refresh cycle — worker collects all new messages into local list, main thread writes them in a single `call_from_thread()` callback

## Testing Strategy

1. Unit tests: `test_tui.py` — `parse_input` and `ParsedInput` unchanged, existing tests pass
2. Integration test: Run TUI with mocked MirrorApp, verify messages appear in transcript (manual)
3. Manual test: Run with oMLX backend, verify streaming conversation renders correctly, auto-scroll works, commands respond
4. Threading verification: Confirm no deadlocks after 10+ turns, no hung UI, no lost messages

## References

- Textual Workers Guide: https://textual.textualize.io/guide/workers/
- Thread Workers Pattern: Use `@work(thread=True)` + `call_from_thread()`
- RichLog Widget: https://textual.textualize.io/widgets/rich_log/
- Thread Safety: "avoid calling methods on your UI directly from a threaded worker"
- Minimum Textual version: 1.0 (per `pyproject.toml`)
