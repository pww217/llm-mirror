from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Header, Input, Label, RichLog

if TYPE_CHECKING:
    from llm_mirror.app import MirrorApp
    from llm_mirror.prompt import Message
    from llm_mirror.session import SessionStats, SessionStore

from llm_mirror.app import AppStatus

_COMMANDS = {"pause", "resume", "quit", "save", "stats", "transcript", "help"}


@dataclass(frozen=True)
class ParsedInput:
    command: str | None
    injection_target: str
    content: str


def parse_input(raw: str) -> ParsedInput:
    stripped = raw.strip()
    if not stripped:
        return ParsedInput(command=None, injection_target="", content="")
    if stripped.startswith("/"):
        parts = stripped.split(maxsplit=1)
        cmd_token = parts[0][1:].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if cmd_token in _COMMANDS:
            return ParsedInput(command=cmd_token, injection_target="", content=rest)
        return ParsedInput(command="unknown", injection_target="", content=cmd_token)
    target = "ambient"
    content = stripped
    lower = stripped.lower()
    for prefix, tgt in (("@echo:", "echo"), ("@mirror:", "mirror")):
        if lower.startswith(prefix):
            target = tgt
            content = stripped[len(prefix):].strip()
            break
    return ParsedInput(command=None, injection_target=target, content=content)


def _format_message(msg: Message) -> Text:
    if msg.speaker == "user" and msg.content.startswith("Topic: "):
        return Text()
    color = {"echo": "cyan", "mirror": "magenta", "user": "yellow bold"}.get(msg.speaker, "white")
    text = Text()
    text.append(f"{msg.speaker.capitalize()}: ", style=f"bold {color}")
    text.append(msg.content + "\n", style=color)
    return text


class Tui(App):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "quit", "Quit"),
        Binding("p", "pause", "Pause"),
        Binding("r", "resume", "Resume"),
        Binding("s", "save", "Save"),
    ]

    DEFAULT_CSS = """
    Tui {
        layout: vertical;
    }

    #header {
        height: 1;
    }

    #body {
        height: 1fr;
    }

    #transcript {
        width: 100%;
        height: 100%;
        background: transparent;
    }

    #input {
        height: 1;
    }

    #footer {
        height: 1;
    }

    #statusbar {
        height: 1;
    }
    """

    status = reactive(AppStatus.RUNNING, always_update=True)
    _total_prompt = reactive(0)
    _total_cached = reactive(0)
    _total_completion = reactive(0)
    _total_latency = reactive(0)
    _last_turn_text = reactive("")
    _rendered_count: int = 0

    def __init__(self, app: MirrorApp, store: SessionStore, session_id: str, model: str) -> None:
        super().__init__()
        self._app = app
        self._store = store
        self._session_id = session_id
        self._model = model

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="body"):
            yield RichLog(id="transcript", auto_scroll=True, wrap=True)
        yield Input(placeholder="Type message or /command...")
        yield Label("", id="statusbar")

    def on_mount(self) -> None:
        self.refresh_worker()

    @work(thread=True)
    def refresh_worker(self) -> None:
        while True:
            time.sleep(0.5)
            stats = self._app.stats()
            last = self._app.last_turn
            status = self._app.status
            with self._app._lock:
                msgs = list(self._app._state.messages) if self._app._state else []
            last_turn_text = f"last: {last.turns}toks in {last.duration_s:.1f}s" if last and last.turns > 0 else ""
            data = {
                "status": status,
                "prompt_tokens": stats.prompt_tokens,
                "cached_tokens": stats.cached_tokens,
                "completion_tokens": stats.completion_tokens,
                "latency_ms": stats.mean_latency_ms,
                "last_turn_text": last_turn_text,
                "messages": msgs,
            }
            self.call_from_thread(self._schedule_ui_update, data)

    def _schedule_ui_update(self, data: dict) -> None:
        transcript = self.query_one("#transcript", RichLog)
        if not transcript._size_known:
            return
        self.status = data["status"]
        self._total_prompt = data["prompt_tokens"]
        self._total_cached = data["cached_tokens"]
        self._total_completion = data["completion_tokens"]
        self._total_latency = data["latency_ms"]
        self._last_turn_text = data["last_turn_text"]
        msgs = data["messages"]
        new_count = len(msgs) - self._rendered_count
        if new_count > 0:
            start = max(0, self._rendered_count)
            for msg in msgs[start:]:
                formatted = _format_message(msg)
                if formatted.plain:
                    transcript.write(formatted)
            self._rendered_count = len(msgs)
        turn_count = len([m for m in msgs if m.speaker in ("echo", "mirror")])
        parts: list[str] = []
        parts.append(data["status"].name)
        parts.append(self._model)
        parts.append(f"{self._session_id} | {turn_count} turns")
        parts.append(f"scenario {self._app._state.meta.package_name if self._app._state else 'debate'}")
        parts.append(f"prompt {data['prompt_tokens']}")
        parts.append(f"cached {data['cached_tokens']}")
        parts.append(f"{data['completion_tokens']} toks")
        if self._last_turn_text:
            parts.append(self._last_turn_text)
        self.query_one("#statusbar", Label).update(" · ".join(parts))

    def action_pause(self) -> None:
        self._app.pause()

    def action_resume(self) -> None:
        self._app.resume()

    def action_save(self) -> None:
        self._app.save()

    def action_quit(self) -> None:
        self._app.save()
        self._store.write_markdown(self._app._state if self._app._state else None)
        self.exit()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value
        event.input.clear()
        parsed = parse_input(raw)
        if parsed.command == "unknown":
            self.notify(f"Unknown command: /{parsed.content}", severity="error")
        elif parsed.command == "help":
            self.notify("Commands: /pause /resume /quit /save /stats /transcript /help", severity="info")
        elif parsed.command == "pause":
            self._app.pause()
            self.notify("Paused.", severity="info")
        elif parsed.command == "resume":
            self._app.resume()
            self.notify("Resumed.", severity="info")
        elif parsed.command == "quit":
            self._app.save()
            self._store.write_markdown(self._app._state if self._app._state else None)
            self.exit()
        elif parsed.command == "save":
            self._app.save()
            self.notify("Saved.", severity="info")
        elif parsed.command == "stats":
            s: SessionStats = self._app.stats()
            pct = f"{s.cache_hit_pct:.1f}%" if s.prompt_tokens > 0 else "N/A"
            self.notify(
                f"Turns: {s.turns} | Prompt: {s.prompt_tokens} | Completion: {s.completion_tokens} | "
                f"Cached: {s.cached_tokens} ({pct}) | Avg latency: {s.mean_latency_ms:.0f}ms | "
                f"Duration: {s.duration_s:.1f}s",
                severity="info",
            )
        elif parsed.command == "transcript":
            md_path = self._store.path.with_suffix(".md")
            try:
                md_text = md_path.read_text(encoding="utf-8")
                self.notify(md_text[:500] + "..." if len(md_text) > 500 else md_text, severity="info")
            except FileNotFoundError:
                self.notify("No transcript yet.", severity="warning")
        elif parsed.command is None and parsed.content:
            self._app.inject(parsed.content, target=parsed.injection_target)
