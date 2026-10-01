from __future__ import annotations

import llm_mirror.personas as P
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


class TestRenderSystem:
    def test_grounded_contains_intro(self) -> None:
        sys_text = U.render_system(P.ECHO_CARD, P.MIRROR_CARD, free=False)
        assert P.SCENARIO_INTRO in sys_text

    def test_free_excludes_clauses(self) -> None:
        sys_text = U.render_system(P.ECHO_CARD, P.MIRROR_CARD, free=True)
        for clause in P.GROUNDING_CLAUSES:
            assert clause not in sys_text

    def test_grounded_contains_clauses(self) -> None:
        sys_text = U.render_system(P.ECHO_CARD, P.MIRROR_CARD, free=False)
        for clause in P.GROUNDING_CLAUSES:
            assert clause in sys_text

    def test_card_override(self) -> None:
        sys_text = U.render_system("custom echo", "custom mirror", free=False)
        assert "custom echo" in sys_text
        assert "custom mirror" in sys_text
        assert P.ECHO_CARD not in sys_text
        assert P.MIRROR_CARD not in sys_text

    def test_byte_identity(self) -> None:
        a = U.render_system(P.ECHO_CARD, P.MIRROR_CARD, free=False)
        b = U.render_system(P.ECHO_CARD, P.MIRROR_CARD, free=False)
        assert a == b


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
        assert result == "The next message is from Echo. Write only Echo's next message text (no name label), in character."

    def test_regular_mirror(self) -> None:
        result = U.render_tail("mirror", opening=False)
        assert result == "The next message is from Mirror. Write only Mirror's next message text (no name label), in character."

    def test_opening(self) -> None:
        result = U.render_tail("echo", opening=True)
        assert result == "This is the opening of the conversation. The next message is from Echo. Write only Echo's message text (no name label), in character."


class TestRenderUserMessage:
    def test_opening_no_messages(self) -> None:
        result = U.render_user_message([], opening=True)
        assert result == "This is the opening of the conversation. The next message is from Echo. Write only Echo's message text (no name label), in character."

    def test_with_messages(self) -> None:
        msgs = [U.Message("user", "Topic: cars.")]
        result = U.render_user_message(msgs, opening=True)
        assert "User: Topic: cars." in result
        assert "\n\n" in result
        assert "The next message is from Echo." in result

    def test_byte_identity(self) -> None:
        msgs = [U.Message("user", "Topic: cars.")]
        a = U.render_user_message(msgs, opening=True)
        b = U.render_user_message(msgs, opening=True)
        assert a == b


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
