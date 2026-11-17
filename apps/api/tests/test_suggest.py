import json

from app.pipeline.suggest import Draft, apply_rules, heuristic_drafts, label_parts, parse_llm_payload
from app.pipeline.words import Word, plan_chunks, sentences_from_words


def _words(count: int, sentence_every: int = 12) -> list[Word]:
    words: list[Word] = []
    for index in range(count):
        text = f"palavra{index}"
        if (index + 1) % sentence_every == 0:
            text += "."
        words.append(Word(text, index * 0.4, index * 0.4 + 0.3))
    return words


def test_parse_llm_json_inside_fence() -> None:
    raw = """```json
{"clips":[{"start":0,"end":30,"title":"Abertura","hook":"Olha isso","score":90,"reason":"gancho"}]}
```"""
    parsed = parse_llm_payload(raw)
    assert parsed[0].title == "Abertura"
    assert parsed[0].score == 90


def test_parse_llm_rejects_invalid_shape() -> None:
    try:
        parse_llm_payload(json.dumps({"items": []}))
    except ValueError as exc:
        assert "clips" in str(exc)
    else:
        raise AssertionError("deveria falhar")


def test_rules_snap_to_sentences_and_drop_overlap() -> None:
    words = _words(80)
    raw = parse_llm_payload(
        json.dumps(
            {
                "clips": [
                    {"start": 0.1, "end": 28, "title": "Um", "hook": "gancho", "score": 80, "reason": "a"},
                    {"start": 2, "end": 40, "title": "Dois", "hook": "outro", "score": 70, "reason": "b"},
                    {"start": 40, "end": 70, "title": "Tres", "hook": "mais", "score": 60, "reason": "c"},
                ]
            }
        )
    )
    drafts = apply_rules(raw, words)
    assert drafts
    assert all(20 <= item.end - item.start <= 60 for item in drafts)
    for left, right in zip(drafts, drafts[1:]):
        assert right.start >= left.end - 0.2


def test_contiguous_clips_keep_the_same_cut_number() -> None:
    drafts = label_parts(
        [
            Draft(0, 30, "Europa", "gancho", 80, "a", "fala"),
            Draft(30, 58, "Segue", "gancho", 70, "b", "fala"),
            Draft(90, 120, "Outro assunto", "gancho", 60, "c", "fala"),
        ]
    )
    assert drafts[0].title.startswith("Corte 1 · Parte 1 · Europa")
    assert drafts[1].title.startswith("Corte 1 · Parte 2 · Europa")
    assert drafts[2].title == "Outro assunto"


def test_heuristic_ranks_without_llm() -> None:
    words = _words(200)
    drafts = heuristic_drafts(words, energy=[(second, 0.8) for second in range(0, 70)])
    assert drafts
    assert len(drafts) <= 20
    assert drafts[0].score >= 0


def test_chunk_plan_offsets_cover_duration() -> None:
    chunks = plan_chunks(duration=3600, file_size=80_000_000, max_bytes=20_000_000)
    assert chunks[0][0] == 0
    assert chunks[-1][1] == 3600
    assert all(end > start for start, end in chunks)
    assert len(chunks) > 1


def test_sentences_split_on_punctuation() -> None:
    words = [Word("Oi", 0, 0.2), Word("tudo.", 0.2, 0.5), Word("Bem", 0.6, 0.8), Word("vindo!", 0.8, 1.1)]
    sentences = sentences_from_words(words)
    assert len(sentences) == 2
    assert sentences[0].text == "Oi tudo."
