import json
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.pipeline.words import Sentence, Word, hook_text, sentences_from_words, text_of, words_between

MIN_SECONDS = 20.0
MAX_SECONDS = 60.0
MAX_CLIPS = 20
WINDOW_WORDS = 1400


class SuggestionPayload(BaseModel):
    start: float
    end: float
    title: str = ""
    hook: str = ""
    score: int = Field(default=0, ge=0, le=100)
    reason: str = ""


class SuggestionList(BaseModel):
    clips: list[SuggestionPayload]


@dataclass(frozen=True)
class Draft:
    start: float
    end: float
    title: str
    hook: str
    score: int
    reason: str
    caption: str


def parse_llm_payload(raw: str) -> list[SuggestionPayload]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("A resposta do modelo não é JSON") from exc
    try:
        parsed = SuggestionList.model_validate(data)
    except ValidationError as exc:
        raise ValueError("O JSON do modelo não tem a lista clips esperada") from exc
    return parsed.clips


def apply_rules(candidates: list[SuggestionPayload], words: list[Word]) -> list[Draft]:
    sentences = sentences_from_words(words)
    drafts: list[Draft] = []
    for candidate in candidates:
        snapped = _snap(sentences, candidate.start, candidate.end)
        if snapped is None:
            continue
        start, end = snapped
        if any(_overlaps(start, end, item.start, item.end) for item in drafts):
            continue
        selected = words_between(words, start, end)
        drafts.append(
            Draft(
                start=start,
                end=end,
                title=_clean(candidate.title) or _title_from(selected),
                hook=_clean(candidate.hook) or hook_text(selected, start),
                score=candidate.score,
                reason=_clean(candidate.reason),
                caption=text_of(selected),
            )
        )
    unique = _dedupe(drafts)
    unique.sort(key=lambda item: item.score, reverse=True)
    kept = unique[:MAX_CLIPS]
    kept.sort(key=lambda item: item.start)
    return label_parts(kept)


def windows(words: list[Word], size: int = WINDOW_WORDS) -> list[list[Word]]:
    if len(words) <= size:
        return [words]
    chunks: list[list[Word]] = []
    step = int(size * 0.8)
    start = 0
    while start < len(words):
        chunks.append(words[start : start + size])
        if start + size >= len(words):
            break
        start += step
    return chunks


def heuristic_drafts(words: list[Word], energy: list[tuple[float, float]] | None = None) -> list[Draft]:
    sentences = sentences_from_words(words)
    peaks = energy or []
    candidates: list[Draft] = []
    for index, sentence in enumerate(sentences):
        group = [sentence]
        duration = sentence.end - sentence.start
        cursor = index + 1
        while duration < 35 and cursor < len(sentences):
            group.append(sentences[cursor])
            duration = group[-1].end - group[0].start
            cursor += 1
        snapped = _fit(group)
        if snapped is None:
            continue
        start, end, chosen = snapped
        selected = words_between(words, start, end)
        density = len(selected) / max(end - start, 0.1)
        energy_score = _energy_score(peaks, start, end)
        hook_bonus = 15 if hook_text(selected, start) else 0
        score = max(0, min(100, int(density * 12 + energy_score + hook_bonus)))
        candidates.append(
            Draft(
                start=start,
                end=end,
                title=_title_from(selected),
                hook=hook_text(selected, start),
                score=score,
                reason="Densidade de fala e energia do áudio",
                caption=text_of(selected),
            )
        )
    return apply_rules(
        [SuggestionPayload(start=item.start, end=item.end, title=item.title, hook=item.hook, score=item.score, reason=item.reason) for item in candidates],
        words,
    )


def _snap(sentences: list[Sentence], start: float, end: float) -> tuple[float, float] | None:
    covered = [sentence for sentence in sentences if sentence.end > start and sentence.start < end]
    fitted = _fit(covered)
    if fitted is None:
        return None
    start_at, end_at, _chosen = fitted
    return start_at, end_at


def _fit(group: list[Sentence]) -> tuple[float, float, list[Sentence]] | None:
    chosen = list(group)
    while chosen and (chosen[-1].end - chosen[0].start) > MAX_SECONDS:
        chosen.pop()
    if not chosen:
        return None
    start = chosen[0].start
    end = chosen[-1].end
    if end - start < MIN_SECONDS or end - start > MAX_SECONDS:
        return None
    return start, end, chosen


def _overlaps(start: float, end: float, other_start: float, other_end: float) -> bool:
    return min(end, other_end) - max(start, other_start) > 0.2


def _dedupe(drafts: list[Draft]) -> list[Draft]:
    ranked = sorted(drafts, key=lambda item: item.score, reverse=True)
    kept: list[Draft] = []
    for draft in ranked:
        if any(_iou(draft, item) > 0.5 for item in kept):
            continue
        kept.append(draft)
    return kept


def _iou(left: Draft, right: Draft) -> float:
    intersection = max(0.0, min(left.end, right.end) - max(left.start, right.start))
    union = max(left.end, right.end) - min(left.start, right.start)
    if union <= 0:
        return 0.0
    return intersection / union


def _energy_score(peaks: list[tuple[float, float]], start: float, end: float) -> float:
    values = [level for moment, level in peaks if start <= moment <= end]
    if not values:
        return 0.0
    return min(40.0, (sum(values) / len(values)) * 80)


def label_parts(drafts: list[Draft]) -> list[Draft]:
    if not drafts:
        return []
    ordered = sorted(drafts, key=lambda item: (item.start, item.end))
    groups: list[list[Draft]] = [[ordered[0]]]
    for draft in ordered[1:]:
        previous = groups[-1][-1]
        if draft.start - previous.end <= 1.5:
            groups[-1].append(draft)
        else:
            groups.append([draft])
    labeled: list[Draft] = []
    series = 0
    for group in groups:
        if len(group) == 1:
            labeled.append(group[0])
            continue
        series += 1
        base = _clean(group[0].title) or "Corte"
        for part, draft in enumerate(group, start=1):
            prefix = f"Corte {series} · Parte {part}"
            titled = f"{prefix} · {base}"
            labeled.append(
                Draft(
                    start=draft.start,
                    end=draft.end,
                    title=titled[:200],
                    hook=draft.hook,
                    score=draft.score,
                    reason=draft.reason,
                    caption=draft.caption,
                )
            )
    return labeled


def _title_from(words: list[Word]) -> str:
    text = text_of(words)
    return text[:80] or "Corte"


def _clean(value: str) -> str:
    return " ".join(value.split())
