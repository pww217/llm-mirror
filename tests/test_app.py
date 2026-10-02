from __future__ import annotations

import time
from pathlib import Path

import pytest

from llm_mirror.app import AppStatus, MirrorApp
from llm_mirror.client import ChatRequest, OmlxClientError, TurnResult
from llm_mirror.packages import Package
from llm_mirror.session import (
    Sampling,
    SessionMeta,
    SessionState,
    SessionStore,
    TurnUsage,
)


class FakeClient:
    """Scriptable client that returns pre-set results."""

    def __init__(self, results: list[TurnResult] | None = None, error: Exception | None = None) -> None:
        self.results: list[TurnResult] = results or []
        self.error = error
        self.call_count = 0

    def chat(self, req: ChatRequest) -> TurnResult:
        if self.error:
            raise self.error
        if self.results and self.call_count < len(self.results):
            result = self.results[self.call_count]
            self.call_count += 1
            return result
        return TurnResult(content="default", usage=TurnUsage(), latency_ms=1)


def _make_state(
    tmp_path: Path,
    seed: str | None = "test",
    package_name: str = "debate",
    max_model_len: int = 262144,
) -> tuple[SessionState, SessionStore, Package]:
    from llm_mirror.packages.debate import DebatePackage
    package = DebatePackage()

    meta = SessionMeta(
        model="test",
        base_url="http://localhost:8000/v1",
        package_name=package_name,
        echo_card=package.personas["echo"],
        mirror_card=package.personas["mirror"],
        sampling=Sampling(),
        seed=seed,
        max_model_len=max_model_len,
    )
    store = SessionStore(tmp_path / "test.jsonl")
    store.append_event({
        "type": "session",
        "model": meta.model,
        "base_url": meta.base_url,
        "scenario": package_name,
        "package_name": meta.package_name,
        "participants": {"echo": {"card": meta.echo_card}, "mirror": {"card": meta.mirror_card}},
        "sampling": {"temperature": 0.8, "max_tokens": 300, "frequency_penalty": 0.0, "presence_penalty": 0.0},
        "seed": meta.seed,
        "max_model_len": meta.max_model_len,
    })
    state = SessionState(meta, [], "echo")
    return state, store, package


def _turn(content: str, prompt: int = 100, cached: int = 80, latency: int = 50) -> TurnResult:
    return TurnResult(
        content=content,
        usage=TurnUsage(prompt_tokens=prompt, completion_tokens=50, cached_tokens=cached),
        latency_ms=latency,
    )


class TestRotation:
    def test_echo_then_mirror(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([_turn("echo msg"), _turn("mirror msg")])
        app = MirrorApp(fake, store, state, package, max_turns=2, turn_delay=0)
        app.start()
        time.sleep(0.5)
        app.quit()
        assert state.messages[0].speaker == "echo"
        assert state.messages[1].speaker == "mirror"

    def test_rotation_continues(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([
            _turn("e1"), _turn("m1"), _turn("e2"), _turn("m2"),
        ])
        app = MirrorApp(fake, store, state, package, max_turns=4, turn_delay=0)
        app.start()
        time.sleep(0.5)
        app.quit()
        speakers = [m.speaker for m in state.messages]
        assert speakers == ["echo", "mirror", "echo", "mirror"]


class TestInjection:
    def test_queued_injection(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([_turn("echo1"), _turn("mirror1")])
        app = MirrorApp(fake, store, state, package, max_turns=2, turn_delay=0)
        app.start()
        time.sleep(0.1)
        app.inject("user says hello")
        time.sleep(0.3)
        app.quit()
        # Injection should be in messages
        user_msgs = [m for m in state.messages if m.speaker == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "user says hello"

    def test_targeted_injection(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([_turn("echo1")])
        app = MirrorApp(fake, store, state, package, max_turns=1, turn_delay=0)
        app.start()
        time.sleep(0.1)
        app.inject("targeted msg", target="mirror")
        time.sleep(0.3)
        app.quit()
        # next_speaker should be mirror
        assert state.next_speaker == "mirror"

    def test_ambient_injection_preserves_rotation(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([_turn("echo1")])
        app = MirrorApp(fake, store, state, package, max_turns=1, turn_delay=0)
        app.start()
        time.sleep(0.3)
        app.inject("ambient msg")
        time.sleep(0.2)
        app.quit()
        # After echo turn, next should be mirror
        assert state.next_speaker == "mirror"


class TestPauseResume:
    def test_pause_stops_turns(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([_turn("echo1")])
        app = MirrorApp(fake, store, state, package, max_turns=5, turn_delay=0)
        app.start()
        time.sleep(0.3)
        app.pause()
        time.sleep(0.3)
        app.quit()
        assert state.messages[0].speaker == "echo"
        # Only 1 turn because pause stopped the loop

    def test_resume_continues(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([_turn("e1"), _turn("m1"), _turn("e2")])
        app = MirrorApp(fake, store, state, package, max_turns=3, turn_delay=0)
        app.start()
        time.sleep(0.2)
        app.pause()
        time.sleep(0.1)
        app.resume()
        time.sleep(0.3)
        app.quit()
        assert len(state.messages) >= 2

    def test_status_changes(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([_turn("e1")])
        app = MirrorApp(fake, store, state, package, turn_delay=0)
        assert app.status == AppStatus.RUNNING
        app.pause()
        assert app.status == AppStatus.PAUSED
        app.resume()
        assert app.status == AppStatus.RUNNING
        app.quit()
        assert app.status == AppStatus.STOPPED


class TestMaxTurns:
    def test_stops_at_max_turns(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([_turn(f"msg{i}") for i in range(10)])
        app = MirrorApp(fake, store, state, package, max_turns=3, turn_delay=0)
        app.start()
        time.sleep(0.5)
        app.quit()
        assert len(state.messages) == 3


class TestContextGuard:
    def test_triggers_near_max(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path, max_model_len=1000)
        fake = FakeClient([_turn("big", prompt=950)])
        app = MirrorApp(fake, store, state, package, ctx_guard_pct=0.9, turn_delay=0)
        app.start()
        time.sleep(0.3)
        assert app.status == AppStatus.PAUSED
        app.quit()


class TestErrorHandling:
    def test_transient_error(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient(error=OmlxClientError("server down"))
        app = MirrorApp(fake, store, state, package, turn_delay=0)
        app.start()
        time.sleep(0.3)
        assert app.status == AppStatus.PAUSED
        app.quit()

    def test_save_from_paused(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient(error=OmlxClientError("down"))
        app = MirrorApp(fake, store, state, package, turn_delay=0)
        app.start()
        time.sleep(0.2)
        app.pause()
        app.save()
        md_path = (tmp_path / "test.jsonl").with_suffix(".md")
        assert md_path.exists()


class TestQuit:
    def test_quit_from_paused(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient()
        app = MirrorApp(fake, store, state, package, turn_delay=0)
        app.start()
        app.pause()
        app.quit()
        assert app.status == AppStatus.STOPPED
        assert app.status == AppStatus.STOPPED


class TestStats:
    def test_stats_computed(self, tmp_path: Path) -> None:
        state, store, package = _make_state(tmp_path)
        fake = FakeClient([
            _turn("e1", prompt=100, cached=80, latency=50),
            _turn("m1", prompt=120, cached=100, latency=60),
        ])
        app = MirrorApp(fake, store, state, package, max_turns=2, turn_delay=0)
        app.start()
        time.sleep(0.5)
        app.quit()
        s = app.stats()
        assert s.turns == 2
        assert s.per_speaker["echo"] == 1
        assert s.per_speaker["mirror"] == 1
        assert s.prompt_tokens == 220
        assert s.cached_tokens == 180
        assert s.cache_hit_pct == pytest.approx(81.8, abs=0.1)
        assert s.mean_latency_ms == pytest.approx(55.0, abs=0.1)
