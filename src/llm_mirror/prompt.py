from __future__ import annotations

import re
from collections.abc import Sequence

import llm_mirror.personas as P


class Message:
    __slots__ = ("content", "speaker")

    def __init__(self, speaker: str, content: str) -> None:
        self.speaker = speaker
        self.content = content


def speaker_label(speaker: str) -> str:
    return {"echo": "Echo", "mirror": "Mirror", "user": "User"}[speaker]


def render_system(echo_card: str, mirror_card: str, free: bool) -> str:
    scenario = P.SCENARIO_INTRO
    scenario += "Echo: " + echo_card + "\n"
    scenario += "Mirror: " + mirror_card + "\n"
    rules = P.SCENARIO_FREE if free else P._SCENARIO_RULES_GROUNDED
    scenario += rules
    return scenario


def render_transcript(messages: Sequence[Message]) -> str:
    return "\n".join(
        f"{speaker_label(m.speaker)}: {m.content}" for m in messages
    )


def render_tail(speaker: str, opening: bool) -> str:
    label = speaker_label(speaker)
    if opening:
        return (
            "This is the opening of the conversation. The next message is from Echo. "
            "Write only Echo's message text (no name label), in character."
        )
    return (
        f"The next message is from {label}. "
        f"Write only {label}'s next message text (no name label), in character."
    )


def render_user_message(
    messages: Sequence[Message], opening: bool
) -> str:
    transcript = render_transcript(messages)
    tail = render_tail(
        "echo" if opening else messages[-1].speaker if messages else "echo",
        opening,
    )
    if transcript:
        return transcript + "\n\n" + tail
    return tail


def strip_reply(content: str, speaker: str) -> str:
    label = speaker_label(speaker)
    # 1. Remove think tags (both markdown and plain-text variants)
    content = re.sub(r"```thinking\b[\s\S]*?```", "", content)
    content = re.sub(r"<thinking>[\s\S]*?</thinking>", "", content)
    # degenerate: lone opening tag, no close
    if "<thinking>" in content:
        content = content.split("<thinking>", 1)[-1]
        if "</thinking>" in content:
            content = content.split("</thinking>", 1)[1]
        else:
            content = ""
    # 2. Strip numbered thinking process blocks (model leaking internal reasoning)
    content = re.sub(
        r"(?:Here's a thinking process:|Thinking Process:)\s*\n"
        r"(?:(?:\d+\.|Step \d+:)\s+[\*\*]?\w+[\*\*]?\s*\n(?:\s*[-•].*\n)*)+",
        "",
        content,
    )
    # 3. Strip leading whitespace
    content = content.lstrip()
    # 4. Remove leading label prefix
    for prefix in (f"{label}: ", f"{label}:", f"{label} — ", f"{label} —"):
        if content.startswith(prefix):
            content = content[len(prefix):]
            content = content.lstrip()
            break
    # 5. Strip matching surrounding double quotes
    if len(content) >= 2 and content[0] == '"' and content[-1] == '"':
        content = content[1:-1]
    # 6. Strip trailing whitespace
    content = content.rstrip()
    return content
