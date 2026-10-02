from __future__ import annotations

import llm_mirror.prompt as U


class TestSpeakerLabel:
    def test_echo(self) -> None:
        assert U.speaker_label("echo") == "Echo"

    def test_mirror(self) -> None:
        assert U.speaker_label("mirror") == "Mirror"

    def test_user(self) -> None:
        assert U.speaker_label("user") == "User"

    def test_unknown_raises(self) -> None:
        try:
            U.speaker_label("unknown")
            assert False, "Should have raised"
        except (ValueError, KeyError):
            pass

class TestRenderTranscript:
    def test_empty(self) -> None:
        assert U.render_transcript([]) == ""

    def test_single_message(self) -> None:
        msg = U.Message("echo", "hello")
        assert U.render_transcript([msg]) == "Echo: hello"

    def test_multiple_messages(self) -> None:
        msgs = [
            U.Message("user", "Topic: cars."),
            U.Message("echo", "I think cars are fine."),
            U.Message("mirror", "But traffic?"),
        ]
        result = U.render_transcript(msgs)
        assert "User: Topic: cars." in result
        assert "Echo: I think cars are fine." in result
        assert "Mirror: But traffic?" in result

    def test_seed_line_format(self) -> None:
        msg = U.Message("user", "Topic: whether cities should ban private cars downtown.")
        assert U.render_transcript([msg]) == "User: Topic: whether cities should ban private cars downtown."


class TestRenderTail:
    def test_regular(self) -> None:
        result = U.render_tail("echo", opening=False)
        assert result == "Write only Echo's next message text (no name label), in character."

    def test_regular_mirror(self) -> None:
        result = U.render_tail("mirror", opening=False)
        assert result == "Write only Mirror's next message text (no name label), in character."

    def test_opening(self) -> None:
        result = U.render_tail("echo", opening=True)
        assert result == "This is the opening of the conversation. Write only Echo's message text (no name label), in character."

class TestStripReply:
    def test_empty_string(self) -> None:
        assert U.strip_reply("", "echo") == ""

    def test_whitespace_only(self) -> None:
        assert U.strip_reply("   \n  ", "echo") == ""

    def test_clean_content(self) -> None:
        assert U.strip_reply("I think cars are fine.", "echo") == "I think cars are fine."

    def test_leading_echo_label(self) -> None:
        result = U.strip_reply("Echo: I think cars are fine.", "echo")
        assert result == "I think cars are fine."

    def test_leading_mirror_label(self) -> None:
        result = U.strip_reply("Mirror: But traffic?", "mirror")
        assert result == "But traffic?"

    def test_leading_emdash_label(self) -> None:
        result = U.strip_reply("Echo — I think cars are fine.", "echo")
        assert result == "I think cars are fine."

    def test_surrounding_quotes(self) -> None:
        result = U.strip_reply('"I think cars are fine."', "echo")
        assert result == "I think cars are fine."

    def test_no_matching_quotes(self) -> None:
        result = U.strip_reply('"I think cars are fine.', "echo")
        assert result == '"I think cars are fine.'

    def test_think_block_markdown(self) -> None:
        content = "```thinking\n17 times 23 is 391.\n```\nI think cars are fine."
        result = U.strip_reply(content, "echo")
        assert result == "I think cars are fine."

    def test_think_block_plain(self) -> None:
        content = "<thinking>17 times 23 is 391.</thinking>\nI think cars are fine."
        result = U.strip_reply(content, "echo")
        assert result == "I think cars are fine."

    def test_think_only_no_close(self) -> None:
        content = "<thinking>17 times 23 is 391."
        result = U.strip_reply(content, "echo")
        assert result == ""

    def test_think_block_then_label(self) -> None:
        content = "<thinking>thinking</thinking>\nEcho: I think cars are fine."
        result = U.strip_reply(content, "echo")
        assert result == "I think cars are fine."

    def test_label_then_think(self) -> None:
        content = "Echo: <thinking>thinking</thinking>\nI think cars are fine."
        result = U.strip_reply(content, "echo")
        assert result == "I think cars are fine."

    def test_leading_trailing_whitespace(self) -> None:
        result = U.strip_reply("  \n  I think cars.\n  ", "echo")
        assert result == "I think cars."
