"""Состояния UI: empty / error / подсказки пути."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

import streamlit as st

PATH_STEPS = [
    ("Загрузка", "файл или учебный пример → проверка → сохранение в базу"),
    ("Аналитика", "сколько продавали, тренд, сезонность, выбросы"),
    ("Прогноз", "две модели сравниваются на прошлом, выбирается точнее"),
    ("Сценарии", "что если продажи ±% или меняем скидку/рекламу"),
    ("Рекомендации", "краткие советы по цифрам; нейросеть по желанию"),
]

F = TypeVar("F", bound=Callable[..., None])
logger = logging.getLogger(__name__)


def empty_state(message: str, *, hint: str | None = None) -> None:
    st.info(message)
    if hint:
        st.caption(hint)


def error_state(title: str, detail: str | None = None) -> None:
    st.error(title)
    if detail:
        st.caption(detail)


def page_guard(fn: F) -> F:
    """Показывает ошибку пользователю без traceback в UI."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка страницы %s", getattr(fn, "__name__", fn))
            error_state(
                "Не удалось отобразить страницу",
                f"{type(exc).__name__}: {exc}",
            )
            return None

    return wrapper  # type: ignore[return-value]


def warn_list(notes: list[str], *, limit: int = 8) -> None:
    for note in notes[:limit]:
        st.warning(note)


def show_user_path(*, current: str | None = None) -> None:
    st.subheader("Путь пользователя")
    for title, desc in PATH_STEPS:
        mark = "→ " if current == title else ""
        st.markdown(f"- **{mark}{title}** — {desc}")
