from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    word: str
    start: float
    end: float


@dataclass(frozen=True)
class Sentence:
    text: str
    start: float
    end: float
    words: tuple[Word, ...]


def offset_words(words: list[Word], offset: float) -> list[Word]:
    return [Word(word.word, round(word.start + offset, 3), round(word.end + offset, 3)) for word in words]


def plan_chunks(duration: float, file_size: int, max_bytes: int) -> list[tuple[float, float]]:
    if duration <= 0:
        return []
    if file_size <= max_bytes:
        return [(0.0, duration)]
    bytes_per_second = file_size / duration
    chunk_seconds = max(30.0, (max_bytes * 0.85) / max(bytes_per_second, 1))
    chunks: list[tuple[float, float]] = []
    start = 0.0
    while start < duration - 0.05:
        end = min(duration, start + chunk_seconds)
        chunks.append((round(start, 3), round(end, 3)))
        start = end
    return chunks


def sentences_from_words(words: list[Word]) -> list[Sentence]:
    grouped: list[Word] = []
    sentences: list[Sentence] = []
    for word in words:
        grouped.append(word)
        if word.word.rstrip().endswith((".", "!", "?")):
            sentences.append(_sentence(grouped))
            grouped = []
    if grouped:
        sentences.append(_sentence(grouped))
    return sentences


def words_between(words: list[Word], start: float, end: float) -> list[Word]:
    return [word for word in words if word.end > start and word.start < end]


def text_of(words: list[Word]) -> str:
    return " ".join(word.word.strip() for word in words if word.word.strip())


def hook_text(words: list[Word], start: float) -> str:
    opening = [word for word in words if word.start < start + 2]
    return text_of(opening)


def _sentence(words: list[Word]) -> Sentence:
    return Sentence(text=text_of(words), start=words[0].start, end=words[-1].end, words=tuple(words))
