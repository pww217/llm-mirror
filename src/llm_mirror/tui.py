from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Console as RichConsole
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from llm_mirror.app import MirrorApp
    from llm_mirror.session import SessionStats, SessionStore

from llm_mirror.app import AppStatus


@dataclass(frozen=True)
class ParsedInput:
    command: str | None
    injection_target: str
    content: str


_COMMANDS = {"pause", "resume", "quit", "save", "stats", "transcript", "help"}


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


def _status_chip(status: AppStatus) -> Text:
    labels = {
        AppStatus.RUNNING: "[RUNNING]",
        AppStatus.PAUSED: "[PAUSED]",
        AppStatus.STOPPED: "[STOPPED]",
    }
    label = labels.get(status, "[?]")
    color = {"RUNNING": "green", "PAUSED": "yellow", "STOPPED": "red"}.get(status.value, "white")
    return Text(f" {label} ", style=f"bold {color} on dark_blue")


def _render_transcript(messages, last_stats: str = "") -> Text:
    text = Text()
    start = max(0, len(messages) - 10)
    for msg in messages[start:]:
        color = {"echo": "cyan", "mirror": "magenta", "user": "yellow bold"}.get(msg.speaker, "white")
        text.append(f"{msg.speaker.capitalize()}: ", style=f"bold {color}")
        text.append(msg.content + "\n", style=color)
    if last_stats:
        text.append(f"\n[{last_stats}]", style="dim")
    return text


class Tui:
    def __init__(self, app: MirrorApp, store: SessionStore, session_id: str, model: str) -> None:
        self._app = app
        self._store = store
        self._session_id = session_id
        self._model = model
        self._last_stats: str = ""
        self._last_turn_text: str = ""
        self._total_prompt = 0
        self._total_cached = 0
        self._total_completion = 0
        self._total_latency = 0
        self._lock = threading.Lock()
        self._console = RichConsole()
        self._live: Live | None = None

    def _render(self) -> Layout:
        with self._lock:
            msgs = list(self._app._state.messages) if self._app._state else []
        status = self._app.status
        header_parts = [_status_chip(status), Text(f" {self._model} ")]
        turn_count = len([m for m in msgs if m.speaker in ("echo", "mirror")])
        header_parts.append(Text(f" {self._session_id} | {turn_count} turns"))
        header = Text().join(header_parts)
        transcript = _render_transcript(msgs, self._last_stats)
        layout = Layout()
        layout.split(
            Layout(Panel(header, title="llm-mirror", border_style="blue"), name="header"),
            Layout(Panel(transcript, title="Transcript"), name="body"),
            Layout(name="footer"),
        )
        footer_parts = [
            Text(" prompt", style="dim"),
            Text(f" {self._total_prompt}", style="cyan"),
            Text(" · cached", style="dim"),
            Text(f" {self._total_cached}", style="cyan"),
            Text(" · ", style="dim"),
            Text(f"{self._total_completion} toks", style="cyan"),
        ]
        if self._last_turn_text:
            footer_parts.append(Text(" · ", style="dim"))
            footer_parts.append(Text(self._last_turn_text, style="yellow"))
        layout["footer"].update(Text().join(footer_parts))
        return layout

    def _refresh_loop(self) -> None:
        while True:
            time.sleep(0.5)
            if self._live is None:
                break
            self._on_refresh()
            try:
                self._live.update(self._render())
            except RuntimeError:
                break

    def _on_refresh(self) -> None:
        s = self._app.stats()
        last = self._app.last_turn
        with self._lock:
            self._total_prompt = s.prompt_tokens
            self._total_cached = s.cached_tokens
            self._total_completion = s.completion_tokens
            self._total_latency = s.mean_latency_ms
            if last and last.turns > 0:
                self._last_turn_text = f"last: {last.turns}toks in {last.duration_s:.1f}s"
            else:
                self._last_turn_text = ""

    def run(self) -> None:
        self._console.print(Text(" Starting mirror session...", style="green"))
        with Live(self._render(), console=self._console, refresh_per_second=5, screen=False) as live:
            self._live = live
            refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
            refresh_thread.start()
            try:
                while True:
                    try:
                        raw = self._console.input(Text("> ", style="bold cyan"))
                    except (EOFError, KeyboardInterrupt):
                        break
                    parsed = parse_input(raw)
                    if parsed.command == "unknown":
                        self._console.print(Text(f" Unknown command: /{parsed.content}", style="red"))
                    elif parsed.command == "help":
                        self._console.print(
                            Text(" Commands: /pause /resume /quit /save /stats /transcript /help", style="yellow")
                        )
                    elif parsed.command == "pause":
                        self._app.pause()
                    elif parsed.command == "resume":
                        self._app.resume()
                    elif parsed.command == "quit":
                        self._app.quit()
                        break
                    elif parsed.command == "save":
                        self._app.save()
                        self._console.print(Text(" Saved.", style="green"))
                    elif parsed.command == "stats":
                        s: SessionStats = self._app.stats()
                        with self._lock:
                            self._total_prompt = s.prompt_tokens
                            self._total_cached = s.cached_tokens
                            self._total_completion = s.completion_tokens
                            self._total_latency = s.mean_latency_ms
                        pct = f"{s.cache_hit_pct:.1f}%" if s.prompt_tokens > 0 else "N/A"
                        table_lines = [
                            "  │  Metric       │ Value",
                            "  ├───────────────┼──────────────────────",
                            f"  │  Turns        │ {s.turns}",
                            f"  │  Prompt toks  │ {s.prompt_tokens}",
                            f"  │  Completion   │ {s.completion_tokens}",
                            f"  │  Cached       │ {s.cached_tokens} ({pct})",
                            f"  │  Avg latency  │ {s.mean_latency_ms:.0f}ms",
                            f"  │  Duration     │ {s.duration_s:.1f}s",
                            "  └───────────────┴──────────────────────",
                        ]
                        self._console.print(Text("\n".join(table_lines), style="yellow"))
                    elif parsed.command == "transcript":
                        md_path = self._store.path.with_suffix(".md")
                        try:
                            md_text = md_path.read_text(encoding="utf-8")
                            self._console.print(Text(md_text, style="dim"))
                        except FileNotFoundError:
                            self._console.print(Text(" No transcript yet.", style="dim"))
                    elif parsed.command is None and parsed.content:
                        self._app.inject(parsed.content, target=parsed.injection_target)
                    live.update(self._render())
            finally:
                self._live = None
