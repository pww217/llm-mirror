from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto

from llm_mirror.client import ChatRequest, OmlxClient, TransientOmlxError
from llm_mirror.packages import Package
from llm_mirror.prompt import (
    Message,
    speaker_label,
    strip_reply,
)
from llm_mirror.session import SessionState, SessionStore

logger = logging.getLogger(__name__)


class AppStatus(Enum):
    RUNNING = auto()
    PAUSED = auto()
    STOPPED = auto()


@dataclass
class SessionStats:
    turns: int
    per_speaker: dict[str, int]
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cache_hit_pct: float
    mean_latency_ms: float
    duration_s: float = 0.0


class MirrorApp:
    def __init__(
        self,
        client: OmlxClient,
        store: SessionStore,
        state: SessionState,
        package: Package,
        max_turns: int = 0,
        ctx_guard_pct: float = 0.9,
        turn_delay: float = 3.0,
    ) -> None:
        self._client = client
        self._store = store
        self._state = state
        self._package = package
        self._max_turns = max_turns
        self._ctx_guard_pct = ctx_guard_pct
        self._turn_delay = turn_delay
        self._status = AppStatus.RUNNING
        self._paused = threading.Event()
        self._paused.set()  # not paused initially
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._turn_count = 0
        self._per_speaker: dict[str, int] = {}
        self._total_prompt = 0
        self._total_completion = 0
        self._total_cached = 0
        self._total_latency = 0
        self._worker: threading.Thread | None = None
        self._on_state_change: callable | None = None
        self._injection_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._last_turn: SessionStats | None = None
        self._started_at: float | None = None

    @property
    def status(self) -> AppStatus:
        return self._status

    def _emit_state_change(self) -> None:
        if self._on_state_change:
            self._on_state_change(self._status)

    def _pause(self) -> None:
        self._status = AppStatus.PAUSED
        self._paused.clear()
        self._emit_state_change()

    def start(self) -> None:
        self._status = AppStatus.RUNNING
        self._paused.set()
        self._worker = threading.Thread(target=self._run, daemon=True, name="mirror-worker")
        self._worker.start()
        self._store.append_event({"type": "control", "action": "startup", "detail": "app started"})
        logger.info("app started: model=%s scenario=%s", self._state.meta.model, self._state.meta.package_name)

    def pause(self) -> None:
        self._status = AppStatus.PAUSED
        self._paused.clear()
        self._store.append_event({"type": "control", "action": "pause", "detail": "user requested"})
        logger.info("app paused")
        self._emit_state_change()

    def resume(self) -> None:
        self._status = AppStatus.RUNNING
        self._paused.set()
        self._store.append_event({"type": "control", "action": "resume", "detail": "user requested"})
        logger.info("app resumed")
        self._emit_state_change()

    def quit(self) -> None:
        self._status = AppStatus.STOPPED
        self._stop.set()
        self._paused.set()  # unblock wait
        if self._worker:
            self._worker.join(timeout=5)
        self._store.append_event({"type": "control", "action": "quit", "detail": "user requested"})
        logger.info("app stopped")
        self._emit_state_change()

    def save(self) -> None:
        self._store.write_markdown(self._state)
        self._store.append_event({"type": "control", "action": "save", "detail": "manual save"})
        logger.info("session saved")

    def inject(self, text: str, target: str = "ambient") -> None:
        self._store.append_event({"type": "injection", "target": target, "content": text})
        if self._status == AppStatus.PAUSED:
            self._state.messages.append(Message("user", text))
            if target in ("echo", "mirror"):
                self._state.next_speaker = target
            logger.info("injection applied (paused): target=%s", target)
        else:
            self._injection_queue.put((target, text))
            logger.info("injection queued: target=%s", target)

    def stats(self) -> SessionStats:
        with self._lock:
            turns = self._turn_count
            per_speaker = dict(self._per_speaker)
            prompt = self._total_prompt
            completion = self._total_completion
            cached = self._total_cached
            pct = 100.0 * cached / prompt if prompt > 0 else 0.0
            mean_lat = self._total_latency / turns if turns > 0 else 0.0
            duration = (time.monotonic() - self._started_at) if self._started_at else 0.0
            return SessionStats(
                turns=turns,
                per_speaker=per_speaker,
                prompt_tokens=prompt,
                completion_tokens=completion,
                cached_tokens=cached,
                cache_hit_pct=pct,
                mean_latency_ms=mean_lat,
                duration_s=duration,
            )

    @property
    def last_turn(self) -> SessionStats | None:
        with self._lock:
            return self._last_turn

    def _run(self) -> None:
        self._injection_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        while True:
            if self._stop.is_set():
                break
            if not self._paused.is_set():
                self._paused.wait()
                if self._stop.is_set():
                    break
            # Drain injection queue
            while True:
                try:
                    target, msg = self._injection_queue.get_nowait()
                    from llm_mirror.prompt import Message
                    self._state.messages.append(Message("user", msg))
                    if target in ("echo", "mirror"):
                        self._state.next_speaker = target
                except queue.Empty:
                    break
            # Build request
            opening = not any(m.speaker in ("echo", "mirror") for m in self._state.messages)
            system = self._package.system_prompt
            transcript = self._package.render_transcript(self._state.messages)
            first_speaker = next(iter(self._package.personas)) if opening else self._state.next_speaker
            tail = self._package.render_tail(first_speaker, opening)
            if opening:
                parts = []
                if self._state.meta.seed:
                    parts.append(f"Topic: {self._state.meta.seed}")
                if transcript:
                    parts.append(transcript)
                parts.append(tail)
                user = "\n\n".join(parts)
            else:
                user = transcript + "\n\n" + tail if transcript else tail
            req = ChatRequest(
                model=self._state.meta.model,
                system=system,
                user=user,
                temperature=self._state.meta.sampling.temperature,
                max_tokens=self._state.meta.sampling.max_tokens,
                frequency_penalty=self._state.meta.sampling.frequency_penalty,
                presence_penalty=self._state.meta.sampling.presence_penalty,
                thinking=getattr(self._state.meta, "thinking", True),
            )
            # Call model
            try:
                result = self._client.chat(req)
                content = strip_reply(result.content, self._state.next_speaker)
                if not content:
                    logger.warning("empty reply, retrying once")
                    result = self._client.chat(req)
                    content = strip_reply(result.content, self._state.next_speaker)
                if not content:
                    self._store.append_event({
                        "type": "control", "action": "empty_reply",
                        "detail": "model returned empty content after retry",
                    })
                    self._pause()
                    continue
                from llm_mirror.prompt import Message
                self._state.messages.append(Message(self._state.next_speaker, content))
                self._store.append_event({
                    "type": "turn",
                    "speaker": self._state.next_speaker,
                    "model": self._state.meta.model,
                    "content": content,
                    "usage": {
                        "prompt_tokens": result.usage.prompt_tokens,
                        "completion_tokens": result.usage.completion_tokens,
                        "cached_tokens": result.usage.cached_tokens,
                    },
                    "latency_ms": result.latency_ms,
                    "sampling": {
                        "temperature": self._state.meta.sampling.temperature,
                        "max_tokens": self._state.meta.sampling.max_tokens,
                        "frequency_penalty": self._state.meta.sampling.frequency_penalty,
                        "presence_penalty": self._state.meta.sampling.presence_penalty,
                    },
                })
                self._store.write_markdown(self._state)
                with self._lock:
                    self._turn_count += 1
                    spk = self._state.next_speaker
                    self._per_speaker[spk] = self._per_speaker.get(spk, 0) + 1
                    self._total_prompt += result.usage.prompt_tokens
                    self._total_completion += result.usage.completion_tokens
                    self._total_cached += result.usage.cached_tokens
                    self._total_latency += result.latency_ms
                # Flip speaker
                self._state.next_speaker = self._package.next_speaker(self._state.next_speaker)
                # Context guard
                if result.usage.prompt_tokens >= self._ctx_guard_pct * self._state.meta.max_model_len:
                    self._store.append_event({
                        "type": "control", "action": "auto_pause_context",
                        "detail": f"prompt tokens {result.usage.prompt_tokens} >= {self._ctx_guard_pct * self._state.meta.max_model_len:.0f}",
                    })
                    self._pause()
                    continue
                # Max turns
                if self._max_turns > 0 and self._turn_count >= self._max_turns:
                    self._store.append_event({
                        "type": "control", "action": "auto_pause_max_turns",
                        "detail": f"reached {self._max_turns} turns",
                    })
                    self._pause()
                    continue
                logger.info(
                    "turn %d: %s [%d/%d/%d cached %.0f%% %dms]",
                    self._turn_count,
                    speaker_label(self._state.next_speaker),
                    result.usage.cached_tokens,
                    result.usage.prompt_tokens,
                    result.usage.completion_tokens,
                    100 * result.usage.cached_tokens / result.usage.prompt_tokens if result.usage.prompt_tokens > 0 else 0,
                    result.latency_ms,
                )
                time.sleep(self._turn_delay)
            except TransientOmlxError as exc:
                logger.exception("transient error")
                self._store.append_event({
                    "type": "control", "action": "error",
                    "detail": str(exc)[:300],
                })
                self._pause()
            except Exception as exc:
                logger.exception("unexpected error")
                self._store.append_event({
                    "type": "control", "action": "error",
                    "detail": str(exc)[:300],
                })
                self._pause()
