"""OpenAI client: timeout, retry, structured JSON, fallback наружу."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.config import get_settings
from src.recommendations.schemas import RecommendationsReport

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты аналитик продаж. Тебе дан JSON facts — только агрегаты.
Сформируй структурированные рекомендации на русском.
Жёсткие правила:
1) Используй ТОЛЬКО числа, которые есть в facts (или их очевидные округления).
2) Не выдумывай метрики, даты, WAPE, суммы, дельты.
3) Период указывай как в facts.period.start / facts.period.end; годы из этих строк допустимы.
4) Не проси сырые данные; не упоминай клиентов/email/телефоны.
5) Каждая рекомендация: title, action, evidence, expected_effect, confidence (низкая|средняя|высокая), limitation, applicable_period.
6) Если данных мало — так и скажи в caveats.
7) Простой сдвиг прогноза (±%) и корреляции не выдавай за причинность.
Верни только JSON объекта RecommendationsReport.
"""


def openai_available() -> bool:
    return get_settings().openai_enabled


def generate_openai_report(
    facts: dict[str, Any],
    *,
    timeout_s: float = 30.0,
    retries: int = 2,
) -> RecommendationsReport:
    settings = get_settings()
    if not settings.openai_enabled:
        raise RuntimeError("OPENAI_API_KEY не задан")

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key, timeout=timeout_s)
    user_content = (
        "facts JSON:\n"
        + json.dumps(facts, ensure_ascii=False, default=str)[:12000]
        + "\n\nВерни JSON со полями summary, recommendations[], caveats[]."
    )

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            return RecommendationsReport.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("OpenAI attempt %s failed: %s", attempt + 1, exc)
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))
    assert last_error is not None
    raise last_error
