"""Lexical checks detect exact repetition, without judging scientific richness."""

import pytest

from autonomous_modality.answer_diagnostics import diagnose_answer


@pytest.mark.parametrize(
    "text,words,repeated",
    [
        ("", 0, 0),
        ("One distinct proposal.", 3, 0),
        ("Hypothesis 1: Same claim.\n\nHypothesis 2: Same claim.", 8, 1),
        ("1. Same claim.\n\n2. Same claim.", 6, 1),
        ("Approach 1: Measure slopes.\n\nApproach 2: Map texture.", 8, 0),
    ],
)
def test_diagnostics(text: str, words: int, repeated: int) -> None:
    result = diagnose_answer(text)
    assert result.whitespace_word_count == words
    assert result.repeated_paragraph_occurrences == repeated
    assert not result.exceeds_300_words


def test_diagnostics_does_not_trim_or_set_an_idea_count() -> None:
    text = " ".join(["word"] * 301)
    result = diagnose_answer(text)
    assert result.exceeds_300_words
    assert result.whitespace_word_count == 301
    assert len(text.split()) == 301
    assert "analytical_approaches" not in result.model_dump()
