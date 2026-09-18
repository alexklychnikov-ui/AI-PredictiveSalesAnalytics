"""Русские подписи UI. Сырые коды остаются в данных."""

ENV_LABELS = {
    "production": "продакшен",
    "development": "разработка",
    "staging": "стейджинг",
    "test": "тест",
}

STATUS_LABELS = {
    "ready": "готов",
    "limited": "ограничен",
    "error": "ошибка",
    "draft": "черновик",
}

QUALITY_LABELS = {
    "good": "хорошо",
    "acceptable": "приемлемо",
    "low_confidence": "низкая уверенность",
    "unavailable": "прогноз недоступен",
    "unknown": "неизвестно",
}

HISTORY_STATUS_LABELS = {
    "достаточно": "достаточно",
    "ограниченно": "ограниченно",
    "недостаточно": "недостаточно",
}

MODEL_LABELS = {
    "prophet": "Prophet",
    "seasonal_naive": "простая сезонная",
    "auto": "авто (лучшая по WAPE)",
    "none": "нет",
}

FREQ_LABELS = {
    "D": "день",
    "W": "неделя",
    "M": "месяц",
}

KPI_LABELS = {
    "revenue": "выручка",
    "quantity": "количество",
    "orders": "заказы",
    "other": "другое",
}

AGG_LABELS = {
    "sum": "сумма",
    "mean": "среднее",
    "median": "медиана",
    "min": "минимум",
    "max": "максимум",
    "count": "количество записей",
}

OPTIONAL_FACTOR_LABELS = {
    "discount_pct": "Скидка, %",
    "promo_flag": "Акция (есть / нет)",
    "marketing_spend": "Рекламный бюджет",
    "unit_price": "Цена за штуку",
    "stockout_flag": "Дефицит товара (есть / нет)",
    "category": "Категория",
    "product_id": "Товар",
    "channel": "Канал",
    "region": "Регион",
    "store": "Магазин",
}

SCENARIO_TYPE_LABELS = {
    "base": "базовый (как модель)",
    "stress_optimistic": "оптимистичный (+%)",
    "stress_pessimistic": "пессимистичный (−%)",
    "stress_custom": "свой сдвиг, %",
}

CONFIDENCE_LABELS = {
    "низкая": "низкая",
    "средняя": "средняя",
    "высокая": "высокая",
}


def label_or_raw(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value)
