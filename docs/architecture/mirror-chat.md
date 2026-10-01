# Mirror Chat — Architecture

## Pipeline flow

```
User input ──→ parse_input() ──→ app.inject() ──→ injection queue
                                                          │
                                                          ▼
  TUI render ◄─── stats / state ◄─── worker loop ◄─── app._run()
       │                              │
       │                              ▼
       │                         render_system()
       │                         render_user_message()
       │                              │
       │                              ▼
       │                         OmlxClient.chat()
       │                              │
       │                              ▼
       │                         oMLX server (KV cache)
       │                              │
       │                              ▼
       │                         strip_reply()
       │                              │
       │                              ▼
       │                         store.append_event()
       │                         store.write_markdown()
       │                              │
       └──────────────────────────────┘
```

## JSONL event data shapes

### session event

```json
{
  "type": "session",
  "ts": "2025-01-01T00:00:00+00:00",
  "model": "mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit",
  "base_url": "http://localhost:8000/v1",
  "scenario": "grounded",
  "participants": {"echo": {"card": "..."}, "mirror": {"card": "..."}},
  "sampling": {"temperature": 0.8, "max_tokens": 300, "frequency_penalty": 0.0, "presence_penalty": 0.0},
  "seed": "whether cities should ban private cars downtown",
  "max_model_len": 262144
}
```

### turn event

```json
{
  "type": "turn",
  "ts": "2025-01-01T00:00:01+00:00",
  "speaker": "echo",
  "model": "mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit",
  "content": "I think cities should...",
  "usage": {"prompt_tokens": 1200, "completion_tokens": 150, "cached_tokens": 1000},
  "latency_ms": 450,
  "sampling": {"temperature": 0.8, "max_tokens": 300, "frequency_penalty": 0.0, "presence_penalty": 0.0}
}
```

### control event

```json
{
  "type": "control",
  "ts": "2025-01-01T00:00:00+00:00",
  "action": "startup" | "pause" | "resume" | "quit" | "auto_pause_max_turns" | "auto_pause_context" | "error" | "empty_reply",
  "detail": "optional context string"
}
```

## Stage contracts

### personas.py → prompt.py

`ECHO_CARD`, `MIRROR_CARD`, `SCENARIO_GROUNDED`, `SCENARIO_FREE` are byte-stable constants. `render_system()` swaps card paragraphs into the scenario text verbatim. No variation mid-session.

### prompt.py → client.py

`render_user_message()` produces the user message string for the chat API. `strip_reply()` cleans the model response (think tags, speaker labels, surrounding quotes). The pair forms the cache-critical contract: same session state → same request → full KV cache hit.

### client.py → app.py

`OmlxClient.chat()` returns `TurnResult` with content, usage stats, and latency. `TransientOmlxError` triggers retry (up to 3 attempts with exponential backoff). Other errors pause the app.

### app.py → session.py

`MirrorApp._run()` appends turn events via `SessionStore.append_event()` and writes the Markdown render after each turn. `load_session()` reconstructs `SessionState` from a JSONL file for resume.

### app.py → tui.py

`Tui.run()` polls `MirrorApp.status` and `MirrorApp.stats()` every 0.5s via `rich.live.Live`. User input is parsed by `parse_input()` and dispatched to `MirrorApp.inject()`, `MirrorApp.pause()`, etc.

### main.py

`main()` wires all modules: health check → session init/resume → `MirrorApp` + `Tui` → `app.start()` + `tui.run()` → save on exit. Logging goes to `logs/mirror.log` only (RotatingFileHandler, 1 MB, 3 backups).
