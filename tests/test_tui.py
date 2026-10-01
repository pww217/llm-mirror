from __future__ import annotations

from llm_mirror.tui import parse_input


class TestParseInput:
    def test_empty(self) -> None:
        result = parse_input("")
        assert result.command is None
        assert result.injection_target == ""
        assert result.content == ""

    def test_whitespace_only(self) -> None:
        result = parse_input("   ")
        assert result.command is None
        assert result.injection_target == ""
        assert result.content == ""

    def test_pause_command(self) -> None:
        result = parse_input("/pause")
        assert result.command == "pause"
        assert result.injection_target == ""
        assert result.content == ""

    def test_resume_command(self) -> None:
        result = parse_input("/resume")
        assert result.command == "resume"

    def test_quit_command(self) -> None:
        result = parse_input("/quit")
        assert result.command == "quit"

    def test_save_command(self) -> None:
        result = parse_input("/save")
        assert result.command == "save"

    def test_stats_command(self) -> None:
        result = parse_input("/stats")
        assert result.command == "stats"

    def test_transcript_command(self) -> None:
        result = parse_input("/transcript")
        assert result.command == "transcript"

    def test_help_command(self) -> None:
        result = parse_input("/help")
        assert result.command == "help"

    def test_unknown_command(self) -> None:
        result = parse_input("/foobar")
        assert result.command == "unknown"
        assert result.content == "foobar"

    def test_ambient_injection(self) -> None:
        result = parse_input("hello world")
        assert result.command is None
        assert result.injection_target == "ambient"
        assert result.content == "hello world"

    def test_targeted_echo(self) -> None:
        result = parse_input("@Echo: my point")
        assert result.command is None
        assert result.injection_target == "echo"
        assert result.content == "my point"

    def test_targeted_mirror(self) -> None:
        result = parse_input("@mirror: counter")
        assert result.command is None
        assert result.injection_target == "mirror"
        assert result.content == "counter"

    def test_targeted_echo_with_space(self) -> None:
        result = parse_input("@Echo:  my point")
        assert result.command is None
        assert result.injection_target == "echo"
        assert result.content == "my point"

    def test_stripped_whitespace(self) -> None:
        result = parse_input("  hello  ")
        assert result.content == "hello"
