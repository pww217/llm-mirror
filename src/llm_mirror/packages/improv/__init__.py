from __future__ import annotations

from collections.abc import Sequence

from llm_mirror.prompt import Message


class ImprovPackage:
    """Improv scenario: two personas collaboratively build a story with no constraints."""

    def __init__(self, free: bool = False) -> None:
        self._free = free

    @property
    def name(self) -> str:
        return "improv"

    @property
    def personas(self) -> dict[str, str]:
        return {
            "echo": "generative and enthusiastic. Says 'yes, and...' to whatever Mirror introduces. Builds on ideas, adds detail, takes the story in unexpected directions, embraces surprise.",
            "mirror": "inventive and surprising. Introduces twists, complications, and novel details. Challenges Echo's directions with creative obstacles. Keeps the story fresh by avoiding predictability.",
        }

    @property
    def system_prompt(self) -> str:
        intro = (
            "This is an improvisational story-building exercise between two AI participants, "
            "Echo and Mirror. They are collaboratively writing a single story, taking turns. "
            "Each transcript line is one participant's contribution to the story. "
            "Echo says 'yes, and...' — building on whatever Mirror introduced. "
            "Mirror introduces twists and complications to keep the story interesting. "
            "They take turns in strict rotation: Echo, Mirror, Echo, Mirror, and so on. "
            "There is no moderator; the story never ends and is never wrapped up.\n\n"
        )
        cards = "Echo: " + self.personas["echo"] + "\nMirror: " + self.personas["mirror"] + "\n\n"
        rules = (
            "Stay in character as the named contributor. "
            "Write the next segment of the collaborative story. "
            "Echo should build on Mirror's last contribution. "
            "Mirror should introduce a new twist or complication.\n"
        )
        if not self._free:
            rules += "Do not comment on being an AI, on the format, or on the story itself.\n"
        rules += "Never conclude, sign off, or wrap up the story.\n"
        return intro + cards + rules

    def render_transcript(self, messages: Sequence[Message]) -> str:
        return "\n".join(
            f"{msg.speaker.capitalize()}: {msg.content}" for msg in messages
        )

    def render_tail(self, speaker: str, opening: bool) -> str:
        label = speaker.capitalize()
        if opening:
            return (
                f"This is the opening of the story. "
                f"Write only {label}'s first paragraph (no name label)."
            )
        return (
            f"Write only {label}'s next segment of the story (no name label)."
        )

    @property
    def seed_topics(self) -> list[str]:
        return [
            "a world where silence is currency",
            "the last library on Earth",
            "a city that appears only during eclipses",
            "a machine that predicts dreams before they happen",
            "the day gravity stopped working for exactly one minute",
            "a forest where every tree holds a forgotten memory",
            "a train that travels between parallel timelines",
            "the inventor of a color nobody has ever seen",
            "a village where everyone shares the same dream each night",
            "a clock that counts backward instead of forward",
            "the last letter written by a civilization that vanished",
            "a mirror that shows your life if you'd made different choices",
            "a desert where the sand is made of crushed books",
            "a lighthouse that guides ships through dreams instead of water",
            "the day everyone on Earth forgot how to lie",
            "a garden where plants grow according to emotions",
            "a city built inside a sleeping giant",
            "the architect of a bridge that connects two versions of the same town",
            "a radio station broadcasting from the future",
            "a market where people trade colors instead of money",
            "the keeper of a museum of unfinished inventions",
            "a river that flows in both directions at once",
            "a village where time moves differently for each house",
            "the last message from a satellite that went silent",
            "a library where books rewrite themselves as you read them",
        ]

    def next_speaker(self, current: str) -> str:
        return "mirror" if current == "echo" else "echo"
