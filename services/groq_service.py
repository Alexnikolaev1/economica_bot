"""
services/groq_service.py — транскрипция голосовых через Groq Whisper.
"""

import logging

import aiohttp

logger = logging.getLogger(__name__)

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-large-v3-turbo"


async def transcribe_audio(
    api_key: str,
    audio_bytes: bytes,
    filename: str = "audio.ogg",
) -> str | None:
    """Преобразует аудио в текст. Возвращает None при ошибке."""
    headers = {"Authorization": f"Bearer {api_key}"}

    form = aiohttp.FormData()
    form.add_field("file", audio_bytes, filename=filename, content_type="audio/ogg")
    form.add_field("model", WHISPER_MODEL)
    form.add_field("language", "ru")
    form.add_field("response_format", "json")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROQ_TRANSCRIBE_URL,
                headers=headers,
                data=form,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("Groq HTTP %d: %s", resp.status, body[:300])
                    return None
                data = await resp.json()
                return (data.get("text") or "").strip() or None
    except Exception as exc:
        logger.exception("Ошибка транскрипции Groq: %s", exc)
        return None
