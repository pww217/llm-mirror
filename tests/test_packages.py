from __future__ import annotations

from llm_mirror.packages.debate import DebatePackage
from llm_mirror.packages.improv import ImprovPackage
from llm_mirror.packages.roleplay import RoleplayPackage
from llm_mirror.prompt import Message


class TestDebatePackage:
    def test_name(self) -> None:
        assert DebatePackage().name == "debate"

    def test_personas(self) -> None:
        p = DebatePackage()
        personas = p.personas
        assert "echo" in personas
        assert "mirror" in personas
        assert len(personas) == 2
        assert personas["echo"] == "warm, curious, and generative. Proposes ideas, explores possibilities, builds on what others said, asks interesting questions."
        assert personas["mirror"] == "skeptical and precise. Examines claims, points out weaknesses and hidden assumptions, offers counterexamples, disagrees when warranted. Not hostile — rigorous."

    def test_system_prompt_grounded(self) -> None:
        p = DebatePackage(free=False)
        sp = p.system_prompt
        assert "This is an ongoing conversation" in sp
        assert "warm, curious" in sp
        assert "skeptical and precise" in sp
        assert "Stay on the conversation's topic" in sp
        assert "Do not comment on being an AI" in sp
        assert "Never conclude, sign off, or say goodbye" in sp

    def test_system_prompt_free(self) -> None:
        p = DebatePackage(free=True)
        sp = p.system_prompt
        assert "This is an ongoing conversation" in sp
        assert "warm, curious" in sp
        assert "skeptical and precise" in sp
        assert "Stay on the conversation's topic" not in sp
        assert "Do not comment on being an AI" not in sp
        assert "Never conclude, sign off, or say goodbye" in sp

    def test_render_transcript_empty(self) -> None:
        p = DebatePackage()
        assert p.render_transcript([]) == ""

    def test_render_transcript_single(self) -> None:
        p = DebatePackage()
        msg = Message("echo", "hello")
        assert p.render_transcript([msg]) == "Echo: hello"

    def test_render_transcript_multiple(self) -> None:
        p = DebatePackage()
        msgs = [
            Message("user", "Topic: cars."),
            Message("echo", "I think cars are fine."),
            Message("mirror", "But traffic?"),
        ]
        result = p.render_transcript(msgs)
        assert "User: Topic: cars." in result
        assert "Echo: I think cars are fine." in result
        assert "Mirror: But traffic?" in result

    def test_render_tail_opening(self) -> None:
        p = DebatePackage()
        result = p.render_tail("echo", opening=True)
        assert result == "This is the opening of the conversation. Write only Echo's message text (no name label), in character."

    def test_render_tail_regular(self) -> None:
        p = DebatePackage()
        result = p.render_tail("mirror", opening=False)
        assert result == "Write only Mirror's next message text (no name label), in character."

    def test_next_speaker_echo_to_mirror(self) -> None:
        p = DebatePackage()
        assert p.next_speaker("echo") == "mirror"

    def test_next_speaker_mirror_to_echo(self) -> None:
        p = DebatePackage()
        assert p.next_speaker("mirror") == "echo"

    def test_seed_topics_count(self) -> None:
        p = DebatePackage()
        assert len(p.seed_topics) == 30

    def test_seed_topics_unique(self) -> None:
        p = DebatePackage()
        assert len(set(p.seed_topics)) == 30

    def test_byte_identity_system_prompt_grounded(self) -> None:
        p = DebatePackage(free=False)
        a = p.system_prompt
        b = DebatePackage(free=False).system_prompt
        assert a == b

    def test_byte_identity_system_prompt_free(self) -> None:
        p = DebatePackage(free=True)
        a = p.system_prompt
        b = DebatePackage(free=True).system_prompt
        assert a == b


class TestRoleplayPackage:
    def test_name(self) -> None:
        assert RoleplayPackage().name == "roleplay"

    def test_personas(self) -> None:
        p = RoleplayPackage()
        personas = p.personas
        assert "echo" in personas
        assert "mirror" in personas
        assert len(personas) == 2

    def test_system_prompt_grounded(self) -> None:
        p = RoleplayPackage(free=False)
        sp = p.system_prompt
        assert "roleplay" in sp
        assert "imaginative and immersive" in sp
        assert "observant and nuanced" in sp
        assert "Stay on the scene and scenario" in sp
        assert "Do not comment on being an AI" in sp
        assert "Never conclude, sign off, or break character" in sp

    def test_system_prompt_free(self) -> None:
        p = RoleplayPackage(free=True)
        sp = p.system_prompt
        assert "roleplay" in sp
        assert "Stay on the scene and scenario" not in sp
        assert "Do not comment on being an AI" not in sp
        assert "Never conclude, sign off, or break character" in sp

    def test_render_transcript_empty(self) -> None:
        p = RoleplayPackage()
        assert p.render_transcript([]) == ""

    def test_render_transcript_single(self) -> None:
        p = RoleplayPackage()
        msg = Message("echo", "hello")
        assert p.render_transcript([msg]) == "Echo: hello"

    def test_render_tail_opening(self) -> None:
        p = RoleplayPackage()
        result = p.render_tail("echo", opening=True)
        assert "opening of the scene" in result
        assert "in character" in result

    def test_render_tail_regular(self) -> None:
        p = RoleplayPackage()
        result = p.render_tail("mirror", opening=False)
        assert "dialogue or action" in result
        assert "in character" in result

    def test_next_speaker_echo_to_mirror(self) -> None:
        p = RoleplayPackage()
        assert p.next_speaker("echo") == "mirror"

    def test_next_speaker_mirror_to_echo(self) -> None:
        p = RoleplayPackage()
        assert p.next_speaker("mirror") == "echo"

    def test_seed_topics_count(self) -> None:
        p = RoleplayPackage()
        assert len(p.seed_topics) == 20

    def test_seed_topics_unique(self) -> None:
        p = RoleplayPackage()
        assert len(set(p.seed_topics)) == 20

    def test_byte_identity_system_prompt_grounded(self) -> None:
        p = RoleplayPackage(free=False)
        a = p.system_prompt
        b = RoleplayPackage(free=False).system_prompt
        assert a == b

    def test_byte_identity_system_prompt_free(self) -> None:
        p = RoleplayPackage(free=True)
        a = p.system_prompt
        b = RoleplayPackage(free=True).system_prompt
        assert a == b


class TestImprovPackage:
    def test_name(self) -> None:
        assert ImprovPackage().name == "improv"

    def test_personas(self) -> None:
        p = ImprovPackage()
        personas = p.personas
        assert "echo" in personas
        assert "mirror" in personas
        assert len(personas) == 2

    def test_system_prompt_grounded(self) -> None:
        p = ImprovPackage(free=False)
        sp = p.system_prompt
        assert "improvisational" in sp
        assert "generative and enthusiastic" in sp
        assert "inventive and surprising" in sp
        assert "Do not comment on being an AI" in sp
        assert "Never conclude, sign off, or wrap up the story" in sp

    def test_system_prompt_free(self) -> None:
        p = ImprovPackage(free=True)
        sp = p.system_prompt
        assert "improvisational" in sp
        assert "Do not comment on being an AI" not in sp
        assert "Never conclude, sign off, or wrap up the story" in sp

    def test_render_transcript_empty(self) -> None:
        p = ImprovPackage()
        assert p.render_transcript([]) == ""

    def test_render_transcript_single(self) -> None:
        p = ImprovPackage()
        msg = Message("echo", "hello")
        assert p.render_transcript([msg]) == "Echo: hello"

    def test_render_tail_opening(self) -> None:
        p = ImprovPackage()
        result = p.render_tail("echo", opening=True)
        assert "opening of the story" in result
        assert "first paragraph" in result

    def test_render_tail_regular(self) -> None:
        p = ImprovPackage()
        result = p.render_tail("mirror", opening=False)
        assert "next segment of the story" in result

    def test_next_speaker_echo_to_mirror(self) -> None:
        p = ImprovPackage()
        assert p.next_speaker("echo") == "mirror"

    def test_next_speaker_mirror_to_echo(self) -> None:
        p = ImprovPackage()
        assert p.next_speaker("mirror") == "echo"

    def test_seed_topics_count(self) -> None:
        p = ImprovPackage()
        assert len(p.seed_topics) == 25

    def test_seed_topics_unique(self) -> None:
        p = ImprovPackage()
        assert len(set(p.seed_topics)) == 25

    def test_byte_identity_system_prompt_grounded(self) -> None:
        p = ImprovPackage(free=False)
        a = p.system_prompt
        b = ImprovPackage(free=False).system_prompt
        assert a == b

    def test_byte_identity_system_prompt_free(self) -> None:
        p = ImprovPackage(free=True)
        a = p.system_prompt
        b = ImprovPackage(free=True).system_prompt
        assert a == b
