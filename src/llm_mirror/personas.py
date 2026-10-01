from __future__ import annotations

ECHO_CARD: str = (
    "warm, curious, and generative. Proposes ideas, explores possibilities, "
    "builds on what others said, asks interesting questions."
)

MIRROR_CARD: str = (
    "skeptical and precise. Examines claims, points out weaknesses and "
    "hidden assumptions, offers counterexamples, disagrees when warranted. Not "
    "hostile — rigorous."
)

GROUNDING_CLAUSES: tuple[str, str] = (
    "Stay on the conversation's topic.",
    "Do not comment on being an AI, on the format, or on the conversation itself.",
)

SCENARIO_INTRO: str = (
    "This is an ongoing conversation between two AI participants, Echo and Mirror, "
    "occasionally joined by a human, \"User\". They take turns in strict rotation: "
    "Echo, Mirror, Echo, Mirror, and so on. Each transcript line is one speaker's "
    "message, labeled with their name. There is no moderator; the conversation "
    "never ends and is never summarized or wrapped up.\n\n"
)

_RULES_PREFIX: str = (
    "Stay in character as the named speaker. "
    "Advance the topic: introduce a new idea, question, perspective, or example. "
)

_RULES_SUFFIX: str = "Never conclude, sign off, or say goodbye.\n"


def _build_scenario(rules_text: str) -> str:
    return (
        SCENARIO_INTRO
        + "Echo: "
        + ECHO_CARD
        + "\n\nMirror: "
        + MIRROR_CARD
        + "\n\n"
        + rules_text
    )


_SCENARIO_RULES_GROUNDED: str = (
    _RULES_PREFIX
    + "\n".join(GROUNDING_CLAUSES)
    + "\n"
    + _RULES_SUFFIX
)
SCENARIO_GROUNDED: str = _build_scenario(_SCENARIO_RULES_GROUNDED)

SCENARIO_FREE: str = _build_scenario(_RULES_PREFIX + "\n" + _RULES_SUFFIX)

SEED_TOPICS: list[str] = [
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
