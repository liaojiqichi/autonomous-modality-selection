"""Non-mutating lexical diagnostics; these are not semantic A/P annotations."""

import re
from collections import Counter

from pydantic import Field

from autonomous_modality.models import StrictModel

DIAGNOSTICS_VERSION = "answer-lexical-diagnostics-1.0"


class AnswerDiagnostics(StrictModel):
    """Approximate word count and exact paragraph repetition after label removal."""

    version: str = DIAGNOSTICS_VERSION
    whitespace_word_count: int = Field(ge=0)
    exceeds_300_words: bool
    repeated_paragraph_occurrences: int = Field(ge=0)


def diagnose_answer(text: str) -> AnswerDiagnostics:
    """Flag length and repeated bodies without trimming, rewriting or rescoring answers."""
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        body = re.sub(
            r"^\s*(?:\#{1,6}\s*)?(?:hypothesis|approach|perspective)\s+\d+\s*[:.)-]\s*",
            "",
            paragraph,
            flags=re.IGNORECASE,
        )
        body = re.sub(r"^\s*(?:\d+[.)]|[-*])\s+", "", body)
        body = " ".join(body.casefold().split())
        if body:
            paragraphs.append(body)
    count = len(text.split())
    return AnswerDiagnostics(
        whitespace_word_count=count,
        exceeds_300_words=count > 300,
        repeated_paragraph_occurrences=sum(n - 1 for n in Counter(paragraphs).values()),
    )
