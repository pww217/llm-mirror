from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import llm_mirror.prompt as U
import llm_mirror.session as S
from llm_mirror.packages.debate import DebatePackage


def _event(etype: str, **fields: object) -> dict:
    return {"ts": datetime.now(UTC).isoformat(), "type": etype, **fields}


def _session_event(**fields: object) -> dict:
    debate = DebatePackage()
    personas = debate.personas
    return _event(
        "session",
        model="test-model",
        base_url="http://localhost:8000/v1",
        participants={"echo": {"card": personas["echo"]}, "mirror": {"card": personas["mirror"]}},
        sampling={"temperature": 0.8, "max_tokens": 300, "frequency_penalty": 0.0, "presence_penalty": 0.0},
        max_model_len=262144,
        **fields,
    )


def _turn_event(speaker: str, content: str, **fields: object) -> dict:
    return _event("turn", speaker=speaker, model="test-model", content=content, usage={"prompt_tokens": 100, "completion_tokens": 50, "cached_tokens": 80}, latency_ms=500, **fields)


def _injection_event(content: str, target: str = "ambient") -> dict:
    return _event("injection", target=target, content=content)


def _control_event(action: str, detail: str | None = None) -> dict:
    return _event("control", action=action, detail=detail)


class TestSessionStore:
    def test_append_and_read(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event())
        store.append_event(_turn_event("echo", "hello"))
        store.close()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "session"
        assert json.loads(lines[1])["type"] == "turn"

    def test_markdown_render(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event())
        store.append_event(_turn_event("echo", "hello"))
        store.append_event(_turn_event("mirror", "hi"))
        store.close()
        meta = S.SessionMeta(
            model="test-model",
            base_url="http://localhost:8000/v1",
            package_name="debate",
            echo_card=DebatePackage().personas["echo"],
            mirror_card=DebatePackage().personas["mirror"],
            sampling=S.Sampling(),
            seed="test",
            max_model_len=262144,
        )
        state = S.SessionState(meta, [U.Message("echo", "hello"), U.Message("mirror", "hi")], "echo")
        store.write_markdown(state)
        md_path = path.with_suffix(".md")
        assert md_path.exists()
        md = md_path.read_text()
        assert "**Echo:** hello" in md
        assert "**Mirror:** hi" in md
        assert "test-model" in md

    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event(seed="my-seed"))
        store.append_event(_turn_event("echo", "echo msg"))
        store.append_event(_injection_event("user injection", "ambient"))
        store.append_event(_turn_event("mirror", "mirror msg"))
        store.close()
        state = S.load_session(path)
        assert state.meta.seed == "my-seed"
        assert len(state.messages) == 3
        assert state.messages[0].speaker == "echo"
        assert state.messages[1].speaker == "user"
        assert state.messages[2].speaker == "mirror"
        assert state.next_speaker == "echo"


class TestLoadSession:
    def test_empty_transcript(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event())
        store.close()
        state = S.load_session(path)
        assert state.next_speaker == "echo"

    def test_echo_last(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event())
        store.append_event(_turn_event("echo", "msg"))
        store.close()
        state = S.load_session(path)
        assert state.next_speaker == "mirror"

    def test_mirror_last(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event())
        store.append_event(_turn_event("mirror", "msg"))
        store.close()
        state = S.load_session(path)
        assert state.next_speaker == "echo"

    def test_ambient_injection_preserves_rotation(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event())
        store.append_event(_turn_event("echo", "msg"))
        store.append_event(_injection_event("ambient", "ambient"))
        store.close()
        state = S.load_session(path)
        assert state.next_speaker == "mirror"

    def test_targeted_injection_echo(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event())
        store.append_event(_turn_event("echo", "msg"))
        store.append_event(_injection_event("targeted", "echo"))
        store.close()
        state = S.load_session(path)
        assert state.next_speaker == "echo"

    def test_targeted_injection_mirror(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event())
        store.append_event(_turn_event("echo", "msg"))
        store.append_event(_injection_event("targeted", "mirror"))
        store.close()
        state = S.load_session(path)
        assert state.next_speaker == "mirror"

    def test_corrupted_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        path.write_text("not json\n")
        try:
            S.load_session(path)
            assert False, "Should have raised"
        except S.SessionCorruptedError:
            pass

    def test_missing_session_event(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_turn_event("echo", "msg"))
        store.close()
        try:
            S.load_session(path)
            assert False, "Should have raised"
        except S.SessionCorruptedError:
            pass

    def test_legacy_scenario_grounded_maps_to_debate(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event(scenario="grounded"))
        store.close()
        state = S.load_session(path)
        assert state.meta.package_name == "debate"

    def test_legacy_scenario_free_maps_to_debate(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        store = S.SessionStore(path)
        store.append_event(_session_event(scenario="free"))
        store.close()
        state = S.load_session(path)
        assert state.meta.package_name == "debate"


class TestNewSessionPath:
    def test_with_seed(self, tmp_path: Path) -> None:
        path = S.new_session_path(tmp_path, "my seed")
        assert path.suffix == ".jsonl"
        assert "my-seed" in path.name

    def test_no_seed(self, tmp_path: Path) -> None:
        path = S.new_session_path(tmp_path, None)
        assert "unseeded" in path.name

    def test_long_seed_truncated(self, tmp_path: Path) -> None:
        path = S.new_session_path(tmp_path, "a b c d e f g h")
        path.stem.split("-")
        # timestamp is 15 chars (YYYYMMDD-HHMMSS), so stem is ts + slug
        path.stem[:15]
        slug_part = path.stem[16:]
        slug_words = slug_part.split("-")
        assert len(slug_words) <= 6


class TestSlugify:
    def test_none(self) -> None:
        assert S.slugify(None) == "unseeded"

    def test_simple(self) -> None:
        assert S.slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert S.slugify("what's this?") == "what-s-this"

    def test_max_words(self) -> None:
        assert len(S.slugify("a b c d e f g h i").split("-")) <= 6

    def test_empty_result(self) -> None:
        assert S.slugify("!!!") == "unseeded"

    def test_thinking_default_false(self) -> None:
        debate = DebatePackage()
        meta = S.SessionMeta(
            model="test",
            base_url="http://localhost:8000/v1",
            package_name="debate",
            echo_card=debate.personas["echo"],
            mirror_card=debate.personas["mirror"],
            sampling=S.Sampling(),
            seed="test",
            max_model_len=262144,
        )
        assert meta.thinking is True
