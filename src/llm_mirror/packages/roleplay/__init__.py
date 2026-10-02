from __future__ import annotations

from collections.abc import Sequence

from llm_mirror.prompt import Message


class RoleplayPackage:
    """Roleplay scenario: two personas inhabit characters in a fictional setting."""

    def __init__(self, free: bool = False) -> None:
        self._free = free

    @property
    def name(self) -> str:
        return "roleplay"

    @property
    def personas(self) -> dict[str, str]:
        return {
            "echo": "imaginative and immersive. Fully inhabits your character, speaks in character, reveals personality through action and dialogue, reacts naturally to the other character.",
            "mirror": "observant and nuanced. Plays a contrasting character that creates dramatic tension — different worldview, different goals, different voice. Challenges your character's assumptions and motivations.",
        }

    @property
    def system_prompt(self) -> str:
        intro = (
            "This is a roleplay between two AI participants, Echo and Mirror. "
            "They are playing distinct characters in a fictional scenario. "
            "They take turns in strict rotation: Echo, Mirror, Echo, Mirror, and so on. "
            "Each transcript line is one character's dialogue or action. "
            "There is no narrator; the story emerges entirely through their interaction. "
            "The roleplay never ends and is never wrapped up.\n\n"
        )
        cards = "Echo: " + self.personas["echo"] + "\nMirror: " + self.personas["mirror"] + "\n\n"
        rules = (
            "Stay in character as your named persona at all times. "
            "Advance the story through dialogue, action, and reaction. "
            "Reveal your character's personality through what they say and do, not through exposition.\n"
        )
        if not self._free:
            rules += "Stay on the scene and scenario.\n"
            rules += "Do not comment on being an AI, on the format, or on the roleplay itself.\n"
        rules += "Never conclude, sign off, or break character.\n"
        return intro + cards + rules

    def render_transcript(self, messages: Sequence[Message]) -> str:
        return "\n".join(
            f"{msg.speaker.capitalize()}: {msg.content}" for msg in messages
        )

    def render_tail(self, speaker: str, opening: bool) -> str:
        label = speaker.capitalize()
        if opening:
            return (
                f"This is the opening of the scene. "
                f"Write only {label}'s first message (no name label), in character."
            )
        return (
            f"Write only {label}'s next line of dialogue or action (no name label), in character."
        )

    @property
    def seed_topics(self) -> list[str]:
        return [
            "a detective and a suspect in an interrogation room",
            "a starship captain and first officer during a crisis",
            "two rival spies meeting at a Vienna café",
            "a mentor and apprentice on their last journey together",
            "a merchant and a traveler at a desert oasis",
            "a judge and a defendant in a closed-door hearing",
            "two astronauts stranded on a malfunctioning space station",
            "a librarian and a patron searching for a forbidden book",
            "a chef and a food critic at a closing restaurant",
            "two siblings reuniting at their childhood home",
            "a diplomat and an insurgent negotiating in secret",
            "a doctor and a patient receiving an unusual diagnosis",
            "a thief and a guard on the same heist",
            "a teacher and a student who challenges everything they teach",
            "two musicians improvising together in an empty hall",
            "a historian and an archaeologist uncovering a contradiction",
            "a pilot and a mechanic before a dangerous flight",
            "a journalist and a source in a safe house",
            "a sculptor and a model during an intense session",
            "two rivals competing for the same patron's favor",
        ]

    def next_speaker(self, current: str) -> str:
        return "mirror" if current == "echo" else "echo"
