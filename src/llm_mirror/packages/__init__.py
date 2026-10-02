from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import entry_points
from typing import Protocol, runtime_checkable

from llm_mirror.prompt import Message


@runtime_checkable
class Package(Protocol):
    @property
    def name(self) -> str:
        """Machine-readable package identifier, e.g. 'debate'."""

    @property
    def personas(self) -> dict[str, str]:
        """Speaker key → persona card string. Keys match speaker names used in messages."""

    @property
    def system_prompt(self) -> str:
        """Full system prompt text. Includes intro, persona cards, and rules."""

    def render_transcript(self, messages: Sequence[Message]) -> str:
        """Render conversation history as plain text with speaker labels."""

    def render_tail(self, speaker: str, opening: bool) -> str:
        """Tail directive telling the model what to write next."""

    @property
    def seed_topics(self) -> list[str]:
        """List of seed topic strings for new sessions."""

    def next_speaker(self, current: str) -> str:
        """Return the next speaker given the current one."""


def load_packages() -> dict[str, Package]:
    eps = entry_points(group="llm_mirror.packages")
    return {ep.name: ep.load() for ep in eps}
