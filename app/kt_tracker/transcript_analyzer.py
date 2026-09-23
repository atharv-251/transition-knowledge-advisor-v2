"""Transcript / topic-coverage analysis for automated KT tracking.

Given a raw Teams meeting transcript (VTT/plain text) and the list of topics
expected to be covered for a KT activity, this module determines what was
*actually* discussed rather than assuming a meeting that "happened" covered
everything on the agenda.

The default implementation is a deterministic, keyword/heuristic analyzer so
the pipeline works out of the box without any external AI dependency. A
pluggable hook (``set_llm_backend``) lets a real LLM (for example the
internal VW LLMAAS endpoint already configured via ``LLMAAS_*`` env vars)
be dropped in later to improve topic/question/action-item extraction without
changing any caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_VTT_TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->")


@dataclass
class TopicAnalysis:
    covered: list[str] = field(default_factory=list)
    partially_covered: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)


@dataclass
class TranscriptAnalysis:
    topics: TopicAnalysis
    questions_raised: int
    questions_unresolved: int
    action_items: list[str]
    summary: str
    confidence: float


class LlmBackend(Protocol):
    def __call__(self, transcript_text: str, expected_topics: list[str]) -> dict:
        ...


_llm_backend: LlmBackend | None = None


def set_llm_backend(backend: LlmBackend | None) -> None:
    """Register an optional LLM-based analyzer to replace the heuristic one.

    ``backend`` must be a callable accepting (transcript_text, expected_topics)
    and returning a dict compatible with the fields on ``TranscriptAnalysis``.
    Pass ``None`` to revert to the built-in heuristic analyzer.
    """
    global _llm_backend
    _llm_backend = backend


def _clean_transcript(raw_text: str) -> str:
    """Strip VTT cue numbers/timestamps and speaker-label noise into flat text."""
    lines = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "WEBVTT":
            continue
        if stripped.isdigit():
            continue
        if _VTT_TIMESTAMP_RE.match(stripped):
            continue
        lines.append(stripped)
    return " ".join(lines)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _topic_keywords(topic: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(topic) if len(w) > 2]


_NEGATION_HINTS = (
    "not discussed", "not covered", "not addressed", "did not", "didn't",
    "wasn't covered", "was not covered", "no time for", "did not get to",
    "didn't get to", "won't cover", "will not cover", "skipped", "left out",
    "unable to cover", "couldn't get to", "could not get to", "ran out of time",
    "postponed", "deferred", "pushed to next", "not touched on", "not able to",
)


def _is_negated(sentence_lowered: str) -> bool:
    return any(hint in sentence_lowered for hint in _NEGATION_HINTS)


def _analyze_topic_coverage(sentences: list[str], expected_topics: list[str]) -> TopicAnalysis:
    result = TopicAnalysis()
    lowered_sentences = [s.lower() for s in sentences]
    for topic in expected_topics:
        keywords = _topic_keywords(topic)
        if not keywords:
            result.missed.append(topic)
            continue

        positive_sentences: list[str] = []
        negated_hit = False
        for sentence, lowered in zip(sentences, lowered_sentences):
            matched = all(kw in lowered for kw in keywords) or topic.lower() in lowered
            if not matched:
                continue
            if _is_negated(lowered):
                # A sentence like "we did not get to batch jobs" is evidence
                # the topic was raised but explicitly NOT discussed - it must
                # never count as positive coverage, only as a miss signal.
                negated_hit = True
                continue
            positive_sentences.append(sentence)

        matched_words = sum(len(s.split()) for s in positive_sentences)
        if not positive_sentences:
            result.missed.append(topic)
        elif negated_hit or matched_words < 15:
            result.partially_covered.append(topic)
        else:
            result.covered.append(topic)
    return result


_RESOLUTION_HINTS = (
    "answer", "answered", "response", "so the", "that means", "to clarify",
    "resolved", "we will", "we'll", "sure,", "yes,", "no,", "because",
)
_ACTION_HINTS = (
    "action item", "follow up", "follow-up", "will do", "todo", "to-do",
    "next step", "will share", "will send", "assign",
)


def _analyze_questions(sentences: list[str]) -> tuple[int, int]:
    raised = 0
    unresolved = 0
    for idx, sentence in enumerate(sentences):
        if not sentence.endswith("?"):
            continue
        raised += 1
        follow_up = " ".join(sentences[idx + 1: idx + 3]).lower()
        if not any(hint in follow_up for hint in _RESOLUTION_HINTS):
            unresolved += 1
    return raised, unresolved


def _extract_action_items(sentences: list[str]) -> list[str]:
    items = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(hint in lowered for hint in _ACTION_HINTS):
            items.append(sentence)
    return items[:10]


def _build_summary(sentences: list[str], topics: TopicAnalysis) -> str:
    lead = " ".join(sentences[:2])
    parts = [lead] if lead else []
    if topics.covered:
        parts.append(f"Covered: {', '.join(topics.covered)}.")
    if topics.partially_covered:
        parts.append(f"Partially covered: {', '.join(topics.partially_covered)}.")
    if topics.missed:
        parts.append(f"Not discussed: {', '.join(topics.missed)}.")
    summary = " ".join(parts).strip()
    return summary[:2000]


def _confidence(sentences: list[str], topics: TopicAnalysis, expected_total: int) -> float:
    if not sentences:
        return 0.0
    if expected_total == 0:
        return 0.5
    decisive = len(topics.covered) + len(topics.missed)
    base = 0.5 + 0.4 * (decisive / expected_total)
    length_bonus = min(0.1, len(sentences) / 500)
    return round(min(0.97, base + length_bonus), 2)


def _heuristic_analyze(transcript_text: str, expected_topics: list[str]) -> TranscriptAnalysis:
    cleaned = _clean_transcript(transcript_text)
    sentences = _split_sentences(cleaned)
    topics = _analyze_topic_coverage(sentences, expected_topics)
    questions_raised, questions_unresolved = _analyze_questions(sentences)
    action_items = _extract_action_items(sentences)
    summary = _build_summary(sentences, topics)
    confidence = _confidence(sentences, topics, len(expected_topics))
    return TranscriptAnalysis(
        topics=topics,
        questions_raised=questions_raised,
        questions_unresolved=questions_unresolved,
        action_items=action_items,
        summary=summary,
        confidence=confidence,
    )


def analyze_transcript(transcript_text: str, expected_topics: list[str]) -> TranscriptAnalysis:
    """Analyze a transcript against the expected KT topics.

    Uses the registered LLM backend if one was configured via
    ``set_llm_backend``; otherwise falls back to the deterministic
    keyword/heuristic analyzer, which never marks a topic "covered" from a
    single passing keyword mention (it requires multiple substantive
    sentences of discussion).
    """
    if not transcript_text or not transcript_text.strip():
        return TranscriptAnalysis(
            topics=TopicAnalysis(missed=list(expected_topics)),
            questions_raised=0,
            questions_unresolved=0,
            action_items=[],
            summary="",
            confidence=0.0,
        )

    if _llm_backend is not None:
        try:
            raw = _llm_backend(transcript_text, expected_topics)
            return TranscriptAnalysis(
                topics=TopicAnalysis(
                    covered=raw.get("topics_covered", []),
                    partially_covered=raw.get("topics_partially_covered", []),
                    missed=raw.get("topics_missed", []),
                ),
                questions_raised=int(raw.get("questions_raised", 0)),
                questions_unresolved=int(raw.get("questions_unresolved", 0)),
                action_items=raw.get("action_items", []),
                summary=raw.get("summary", ""),
                confidence=float(raw.get("confidence", 0.5)),
            )
        except Exception:
            # Fall back to the heuristic analyzer rather than failing the sync.
            pass

    return _heuristic_analyze(transcript_text, expected_topics)
