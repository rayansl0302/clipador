import logging
from pathlib import Path

import httpx

from app.config import Settings
from app.pipeline.suggest import Draft, apply_rules, heuristic_drafts, parse_llm_payload, windows
from app.pipeline.words import Word, text_of

logger = logging.getLogger("clip.llm")


class LlmError(RuntimeError):
    pass


def suggest_clips(words: list[Word], settings: Settings, energy: list[tuple[float, float]] | None = None) -> tuple[list[Draft], str]:
    provider = settings.llm_provider
    if provider == "heuristic" or not _has_key(settings):
        reason = "Heurística" if provider == "heuristic" else f"Sem chave para {provider}; heurística"
        return heuristic_drafts(words, energy), reason
    drafts: list[Draft] = []
    try:
        for chunk in windows(words):
            raw = _complete(settings, _prompt(chunk), json_mode=True)
            drafts.extend(apply_rules(parse_llm_payload(raw), chunk))
        merged = apply_rules(
            [_payload(item) for item in drafts],
            words,
        )
        if merged:
            return merged, provider
    except (LlmError, ValueError) as exc:
        logger.info("llm_fallback reason=%s", exc)
        return heuristic_drafts(words, energy), f"Heurística depois de falha do modelo: {exc}"
    return heuristic_drafts(words, energy), "Heurística: o modelo não devolveu cortes válidos"


def suggest_publish_text(title: str, hook: str, caption: str, settings: Settings) -> str:
    fallback = _fallback_caption(title, hook, caption)
    if settings.llm_provider == "heuristic" or not _has_key(settings):
        return fallback
    prompt = (
        "Escreva a legenda de uma publicação curta em português, com gancho e até 5 hashtags. "
        "Responda só com o texto.\n"
        f"Título: {title}\nGancho: {hook}\nFala: {caption[:800]}"
    )
    try:
        text = _complete(settings, prompt).strip()
    except LlmError:
        return fallback
    return text or fallback


def _complete(settings: Settings, prompt: str, json_mode: bool = False) -> str:
    if settings.llm_provider == "anthropic":
        return _anthropic(settings, prompt)
    if settings.llm_provider == "openai":
        return _openai(settings, prompt, json_mode)
    raise LlmError(f"LLM_PROVIDER desconhecido: {settings.llm_provider}")


def _anthropic(settings: Settings, prompt: str) -> str:
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.llm_model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise LlmError(f"Anthropic falhou ({response.status_code}): {response.text[:400]}")
    payload = response.json()
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        raise LlmError("Resposta da Anthropic sem content")
    texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
    return "\n".join(text for text in texts if isinstance(text, str))


def _openai(settings: Settings, prompt: str, json_mode: bool) -> str:
    body: dict[str, object] = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    if response.status_code >= 400:
        raise LlmError(f"OpenAI falhou ({response.status_code}): {response.text[:400]}")
    payload = response.json()
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise LlmError("Resposta da OpenAI sem choices")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if not isinstance(content, str):
        raise LlmError("Resposta da OpenAI sem texto")
    return content


def _prompt(words: list[Word]) -> str:
    lines = [f"{word.start:.2f}-{word.end:.2f} {word.word}" for word in words]
    transcript = "\n".join(lines)
    return (
        "Você escolhe cortes de vídeo curto. Responda somente JSON válido neste formato: "
        '{"clips":[{"start":0,"end":30,"title":"","hook":"","score":80,"reason":""}]}. '
        "Regras: cada corte entre 20 e 60 segundos; start e end em segundos, no início e no fim de uma frase; "
        "sem sobreposição; o gancho precisa estar nos 2 primeiros segundos; score de 0 a 100; "
        "entre 8 e 20 cortes se o material permitir, senão menos. Não invente falas.\n"
        f"Transcrição:\n{transcript}"
    )


def _payload(draft: Draft):
    from app.pipeline.suggest import SuggestionPayload

    return SuggestionPayload(
        start=draft.start,
        end=draft.end,
        title=draft.title,
        hook=draft.hook,
        score=draft.score,
        reason=draft.reason,
    )


def _has_key(settings: Settings) -> bool:
    if settings.llm_provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if settings.llm_provider == "openai":
        return bool(settings.openai_api_key)
    return False


def _fallback_caption(title: str, hook: str, caption: str) -> str:
    base = hook or title or text_of([])
    snippet = caption[:180].strip()
    body = f"{base}\n\n{snippet}".strip()
    return f"{body}\n\n#cortes #viral"


def prompt_for_test(words: list[Word]) -> str:
    return _prompt(words)
