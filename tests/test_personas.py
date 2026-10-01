from __future__ import annotations

import llm_mirror.personas as P


class TestPersonas:
    def test_scenario_free_minus_two_clauses(self) -> None:
        free = P.SCENARIO_FREE
        grounded = P.SCENARIO_GROUNDED
        for clause in P.GROUNDING_CLAUSES:
            assert clause in grounded, f"'{clause}' should be in grounded"
            assert clause not in free, f"'{clause}' should NOT be in free"
        # Free has fewer lines (two grounding clauses removed)
        assert len(free.splitlines()) < len(grounded.splitlines())

    def test_seed_topics_count(self) -> None:
        assert len(P.SEED_TOPICS) == 30

    def test_seed_topics_unique(self) -> None:
        assert len(set(P.SEED_TOPICS)) == 30

    def test_card_prefixes(self) -> None:
        assert P.ECHO_CARD.startswith("warm,")
        assert P.MIRROR_CARD.startswith("skeptical")

    def test_scenario_intro_present(self) -> None:
        assert "This is an ongoing conversation" in P.SCENARIO_GROUNDED
        assert "This is an ongoing conversation" in P.SCENARIO_FREE

    def test_scenario_rules_present(self) -> None:
        assert "Stay in character as the named speaker" in P.SCENARIO_GROUNDED
        assert "Stay in character as the named speaker" in P.SCENARIO_FREE

    def test_grounding_clauses_in_grounded(self) -> None:
        for clause in P.GROUNDING_CLAUSES:
            assert clause in P.SCENARIO_GROUNDED

    def test_no_duplicates_in_seed_topics(self) -> None:
        seen: set[str] = set()
        for topic in P.SEED_TOPICS:
            assert topic not in seen
            seen.add(topic)
