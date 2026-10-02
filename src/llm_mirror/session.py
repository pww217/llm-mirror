from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import llm_mirror.prompt as P


class SessionCorruptedError(Exception):
    """Raised when a session JSONL file contains malformed data."""


class Sampling:
    __slots__ = ("frequency_penalty", "max_tokens", "presence_penalty", "temperature")

    def __init__(
        self,
        temperature: float = 0.8,
        max_tokens: int = 300,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty


class TurnUsage:
    __slots__ = ("cached_tokens", "completion_tokens", "prompt_tokens")

    def __init__(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cached_tokens = cached_tokens


class SessionMeta:
    __slots__ = (
        "base_url",
        "echo_card",
        "max_model_len",
        "mirror_card",
        "model",
        "package_name",
        "sampling",
        "seed",
        "thinking",
    )

    def __init__(
        self,
        model: str,
        base_url: str,
        package_name: str,
        echo_card: str,
        mirror_card: str,
        sampling: Sampling,
        seed: str | None,
        max_model_len: int,
        thinking: bool = True,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.package_name = package_name
        self.echo_card = echo_card
        self.mirror_card = mirror_card
        self.sampling = sampling
        self.seed = seed
        self.max_model_len = max_model_len
        self.thinking = thinking


class SessionState:
    __slots__ = ("messages", "meta", "next_speaker")

    def __init__(self, meta: SessionMeta, messages: list[P.Message], next_speaker: str) -> None:
        self.meta = meta
        self.messages = messages
        self.next_speaker = next_speaker


class SessionStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._fh = open(path, "a", encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def append_event(self, event: dict) -> None:
        event["ts"] = datetime.now(UTC).isoformat()
        self._fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._fh.flush()

    def write_markdown(self, state: SessionState) -> None:
        md_path = self._path.with_suffix(".md")
        lines: list[str] = []
        m = state.meta
        lines.append(f"# Session: {self._path.stem}")
        lines.append("")
        lines.append(f"- **Model:** {m.model}")
        lines.append(f"- **Base URL:** {m.base_url}")
        lines.append(f"- **Scenario:** {m.package_name}")
        lines.append(f"- **Seed:** {m.seed or 'none'}")
        lines.append(f"- **Max tokens:** {m.sampling.max_tokens}")
        lines.append(f"- **Temperature:** {m.sampling.temperature}")
        lines.append(f"- **Frequency penalty:** {m.sampling.frequency_penalty}")
        lines.append(f"- **Presence penalty:** {m.sampling.presence_penalty}")
        lines.append(f"- **Thinking:** {m.thinking}")
        lines.append("")
        lines.append("---")
        lines.append("")
        for msg in state.messages:
            label = P.speaker_label(msg.speaker)
            lines.append(f"**{label}:** {msg.content}")
            lines.append("")
            lines.append("---")
            lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")

    def close(self) -> None:
        self._fh.close()


def slugify(seed: str | None) -> str:
    if seed is None:
        return "unseeded"
    slug = seed.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    words = slug.split("-")
    words = words[:6]
    return "-".join(words) or "unseeded"


def new_session_path(session_dir: Path, seed: str | None) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    slug = slugify(seed)
    return session_dir / f"{ts}-{slug}.jsonl"


def load_session(path: Path) -> SessionState:
    lines = path.read_text(encoding="utf-8").splitlines()
    meta: SessionMeta | None = None
    messages: list[P.Message] = []
    next_speaker = "echo"

    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SessionCorruptedError(f"line {i}: {exc}") from exc

        etype = event.get("type", "")
        if etype == "session":
            sampling = Sampling(
                temperature=event.get("sampling", {}).get("temperature", 0.8),
                max_tokens=event.get("sampling", {}).get("max_tokens", 300),
                frequency_penalty=event.get("sampling", {}).get("frequency_penalty", 0.0),
                presence_penalty=event.get("sampling", {}).get("presence_penalty", 0.0),
            )
            # Map legacy scenario values to package names
            legacy_scenario = event.get("scenario", "grounded")
            if legacy_scenario == "grounded" or legacy_scenario == "free":
                package_name = "debate"
            else:
                package_name = legacy_scenario or "debate"
            meta = SessionMeta(
                model=event.get("model", ""),
                base_url=event.get("base_url", ""),
                package_name=package_name,
                echo_card=event.get("participants", {}).get("echo", {}).get("card", ""),
                mirror_card=event.get("participants", {}).get("mirror", {}).get("card", ""),
                sampling=sampling,
                seed=event.get("seed"),
                max_model_len=event.get("max_model_len", 262144),
                thinking=event.get("thinking", True),
            )
        elif etype == "turn":
            speaker = event["speaker"]
            messages.append(P.Message(speaker, event["content"]))
            next_speaker = "mirror" if speaker == "echo" else "echo"
        elif etype == "injection":
            messages.append(P.Message("user", event["content"]))
            target = event.get("target", "ambient")
            if target in ("echo", "mirror"):
                next_speaker = target
        # control events ignored for state reconstruction

    if meta is None:
        raise SessionCorruptedError("no session event found")

    return SessionState(meta, messages, next_speaker)
