"""Обзор окружения и сохранённых наборов."""

from __future__ import annotations

import streamlit as st

from src.config import get_settings
from src.db.repositories import DatasetRepository
from src.db.session import check_db, session_scope
from src.ui.feedback import empty_state, error_state, page_guard, show_user_path
from src.ui.labels import ENV_LABELS, FREQ_LABELS, STATUS_LABELS, label_or_raw


@page_guard
def main() -> None:
    settings = get_settings()

    st.title("Предиктивная аналитика продаж")
    st.caption(
        "Полный путь: Загрузка → Аналитика → Прогноз → Сценарии → Рекомендации. "
        "Код менять не нужно."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Окружение", label_or_raw(ENV_LABELS, settings.app_env))
    col2.metric("Домен", settings.app_domain)
    col3.metric("OpenAI", "вкл" if settings.openai_enabled else "выкл")

    show_user_path()

    ok, message = check_db()
    if ok:
        st.success("PostgreSQL подключён")
        with st.expander("Версия PostgreSQL"):
            st.code(message, language="text")
    else:
        error_state("PostgreSQL недоступен", message)
        return

    try:
        with session_scope() as session:
            summaries = DatasetRepository(session).list_summaries()
        st.metric("Наборов в БД", len(summaries))
        if summaries:
            st.dataframe(
                [
                    {
                        "ID": item.id,
                        "Название": item.name,
                        "Частота": label_or_raw(FREQ_LABELS, item.frequency),
                        "KPI": item.target_kpi,
                        "Строк": item.observations_count,
                        "Статус": label_or_raw(STATUS_LABELS, item.status),
                    }
                    for item in summaries
                ],
                use_container_width=True,
            )
            st.caption("Дальше: «Аналитика» или «Прогноз» по выбранному набору.")
        else:
            empty_state(
                "Пока нет сохранённых наборов.",
                hint="Откройте страницу «Загрузка» и сохраните CSV или синтетический пример.",
            )
    except Exception as exc:  # noqa: BLE001
        error_state("Не удалось прочитать наборы", str(exc))


main()
