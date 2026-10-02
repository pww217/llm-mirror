from __future__ import annotations

from collections.abc import Sequence

from llm_mirror.prompt import Message


class DebatePackage:
    """Debate scenario: two personas explore a topic in alternating turns."""

    def __init__(self, free: bool = False) -> None:
        self._free = free

    @property
    def name(self) -> str:
        return "debate"

    @property
    def personas(self) -> dict[str, str]:
        return {
            "echo": "warm, curious, and generative. Proposes ideas, explores possibilities, builds on what others said, asks interesting questions.",
            "mirror": "skeptical and precise. Examines claims, points out weaknesses and hidden assumptions, offers counterexamples, disagrees when warranted. Not hostile — rigorous.",
        }

    @property
    def system_prompt(self) -> str:
        intro = (
            "This is an ongoing conversation between two AI participants, Echo and Mirror, "
            "occasionally joined by a human, \"User\". They take turns in strict rotation: "
            "Echo, Mirror, Echo, Mirror, and so on. Each transcript line is one speaker's "
            "message, labeled with their name. There is no moderator; the conversation "
            "never ends and is never summarized or wrapped up.\n\n"
        )
        cards = "Echo: " + self.personas["echo"] + "\nMirror: " + self.personas["mirror"] + "\n\n"
        rules = (
            "Stay in character as the named speaker. "
            "Advance the topic: introduce a new idea, question, perspective, or example.\n"
        )
        if not self._free:
            rules += "Stay on the conversation's topic.\n"
            rules += "Do not comment on being an AI, on the format, or on the conversation itself.\n"
        rules += "Never conclude, sign off, or say goodbye.\n"
        return intro + cards + rules

    def render_transcript(self, messages: Sequence[Message]) -> str:
        return "\n".join(
            f"{msg.speaker.capitalize()}: {msg.content}" for msg in messages
        )

    def render_tail(self, speaker: str, opening: bool) -> str:
        label = speaker.capitalize()
        if opening:
            return (
                f"This is the opening of the conversation. "
                f"Write only {label}'s message text (no name label), in character."
            )
        return (
            f"Write only {label}'s next message text (no name label), in character."
        )

    @property
    def seed_topics(self) -> list[str]:
        return [
            "whether cities should ban private cars downtown",
            "whether chess is a solved game in principle",
            "what makes a scientific instrument trustworthy",
            "whether remote work weakens mentorship",
            "whether analog synthesizers still matter",
            "whether AI-generated art should be considered real art",
            "whether space mining is ethically justified",
            "whether social media has been net positive for democracy",
            "whether standardized testing measures student ability",
            "whether open-source software is more secure than proprietary",
            "whether nuclear energy is the climate solution",
            "whether the four-day workweek is economically viable",
            "whether space exploration deserves current funding levels",
            "whether universal basic income would work at scale",
            "whether online education matches in-person learning",
            "whether genetic engineering of humans should be permitted",
            "whether copyright terms are too long in the digital age",
            "whether public libraries remain essential in the internet era",
            "whether fast fashion is a moral issue",
            "whether the gig economy exploits workers",
            "whether the death penalty is ever justified",
            "whether the metaverse is a useful concept",
            "whether vaccine mandates respect bodily autonomy",
            "whether space tourism is a waste of resources",
            "whether big tech has too much power over society",
            "whether the arts deserve more public funding",
            "whether plastic bans actually help the environment",
            "whether animal testing has a place in modern science",
            "whether the military should control artificial intelligence",
            "whether the concept of privacy is dead in the digital age",
        ]

    def next_speaker(self, current: str) -> str:
        return "mirror" if current == "echo" else "echo"
