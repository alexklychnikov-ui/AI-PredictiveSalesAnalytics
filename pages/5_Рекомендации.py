"""Рекомендации: rules + опциональный OpenAI по facts payload."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.analytics.service import apply_filters, observations_to_frame
from src.config import get_settings
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.export.reports import recommendations_text_report
from src.recommendations.facts import to_jsonable
from src.recommendations.openai_client import openai_available
from src.recommendations.service import run_insight_job
from src.schemas import ForecastPointCreate, ForecastRunCreate
from src.ui.feedback import empty_state, page_guard
from src.ui.help_texts import METRIC_HELP, PAGE_INTROS, show_glossary
from src.ui.labels import FREQ_LABELS, label_or_raw
from src.ui.session_store import serialize_insight_job

SOURCE_LABELS = {
    "rules": "правила (шаблоны)",
    "openai": "OpenAI",
    "openai_fallback_rules": "OpenAI не подошёл → шаблоны",
    "cache": "из кэша",
}


@page_guard
def main() -> None:
    st.title("Рекомендации")
    st.caption(PAGE_INTROS["recommendations"])
    show_glossary(st)

    settings = get_settings()
    if openai_available():
        st.success(f"OpenAI доступен · модель {settings.openai_model}")
    else:
        st.info("Ключ OpenAI не задан — будут понятные шаблонные советы без нейросети")

    with session_scope() as session:
        summaries = DatasetRepository(session).list_summaries()

    if not summaries:
        empty_state("Нет сохранённых наборов.", hint="Сначала откройте «Загрузка».")
        return

    options = {f"{item.id} — {item.name}": item for item in summaries}
    selected_label = st.selectbox("Набор данных", list(options.keys()))
    dataset = options[selected_label]

    with session_scope() as session:
        repo = DatasetRepository(session)
        series_keys = repo.list_series_keys(dataset.id)
        frame = observations_to_frame(repo.load_observations(dataset.id))

    if frame.empty:
        empty_state("В наборе нет наблюдений")
        return

    c1, c2, c3 = st.columns(3)
    series_key = c1.selectbox(
        "Ряд",
        series_keys or ["total"],
        index=0,
        help=METRIC_HELP["series_key"],
    )
    horizon = int(
        c2.number_input(
            "Горизонт для фактов",
            min_value=1,
            max_value=90,
            value=14,
            help=METRIC_HELP["horizon"],
        )
    )
    use_openai = c3.checkbox(
        "Подключить OpenAI",
        value=openai_available(),
        help="Нейросеть только переформулирует уже посчитанные цифры, не выдумывает новые.",
    )
    force_refresh = st.checkbox(
        "Пересчитать заново (не брать из кэша)",
        value=False,
        help="Кэш экономит время, если те же данные уже считали.",
    )
    filtered = apply_filters(frame, series_key=series_key)
    st.caption(
        f"Частота: {label_or_raw(FREQ_LABELS, dataset.frequency)} · точек: {len(filtered)}"
    )

    if st.button("Сформировать рекомендации", type="primary"):
        with st.spinner("Сбор facts и генерация…"):
            job = run_insight_job(
                filtered,
                frequency=dataset.frequency,
                horizon=horizon,
                dataset_meta={
                    "id": dataset.id,
                    "name": dataset.name,
                    "target_kpi": dataset.target_kpi,
                    "frequency": dataset.frequency,
                },
                use_openai=use_openai,
                include_prophet=False,
                force_refresh=force_refresh,
            )
        st.session_state["insight_job"] = serialize_insight_job(
            job,
            dataset_id=dataset.id,
            series_key=series_key,
            history_start=str(filtered["ds"].iloc[0]),
            history_end=str(filtered["ds"].iloc[-1]),
        )
        st.session_state["insight_job"]["horizon"] = horizon

    payload = st.session_state.get("insight_job")
    if not payload or payload.get("dataset_id") != dataset.id or payload.get("series_key") != series_key:
        empty_state("Нажмите «Сформировать рекомендации».")
        return

    st.subheader("Источник")
    st.write(
        f"{label_or_raw(SOURCE_LABELS, payload['source'])}"
        + (f" · модель {payload['openai_model']}" if payload.get("openai_model") else "")
        + f" · hash `{(payload.get('facts_hash') or '')[:12]}…`"
    )
    for note in payload.get("notes") or []:
        if "fallback" in note.lower() or "вне facts" in note.lower():
            st.info(note)
        else:
            st.warning(note)
    if (
        not payload.get("validation_ok")
        and payload.get("validation_errors")
        and payload.get("source") == "openai_fallback_rules"
    ):
        st.caption("Отклонённые числа OpenAI: " + "; ".join((payload.get("validation_errors") or [])[:5]))
    elif not payload.get("validation_ok") and payload.get("validation_errors"):
        st.error("Валидация чисел: " + "; ".join((payload.get("validation_errors") or [])[:5]))

    report = payload.get("report") or {}
    st.subheader("Резюме")
    st.write(report.get("summary") or "—")

    st.subheader("Рекомендации")
    items = report.get("recommendations") or []
    if not items:
        empty_state("Рекомендаций нет")
    for i, item in enumerate(items, start=1):
        with st.expander(
            f"{i}. {item.get('title')} · уверенность: {item.get('confidence')}",
            expanded=i <= 3,
        ):
            st.markdown(f"**Действие:** {item.get('action')}")
            st.markdown(f"**Основание:** {item.get('evidence')}")
            st.markdown(f"**Ожидаемый эффект:** {item.get('expected_effect')}")
            st.markdown(f"**Ограничение:** {item.get('limitation')}")
            st.markdown(f"**Период:** {item.get('applicable_period')}")

    caveats = report.get("caveats") or []
    if caveats:
        st.subheader("Оговорки")
        for c in caveats:
            st.caption(f"• {c}")

    with st.expander("Facts payload (агрегаты)"):
        st.json(payload.get("facts_preview") or {})

    st.download_button(
        "Скачать текстовый отчёт",
        data=recommendations_text_report(payload),
        file_name=f"recommendations_{dataset.id}_{series_key}.txt",
        mime="text/plain",
    )

    if st.button("Сохранить отчёт в PostgreSQL"):
        create = ForecastRunCreate(
            dataset_id=dataset.id,
            series_key=series_key,
            model_name="insight",
            horizon=int(payload.get("horizon") or horizon),
            config={"purpose": "insight_container"},
            metrics={},
            quality_status="insight",
            train_start=_as_utc(payload["history_start"]),
            train_end=_as_utc(payload["history_end"]),
            points=[
                ForecastPointCreate(
                    ds=_as_utc(payload["history_end"]),
                    yhat=0.0,
                    scenario_type="insight_anchor",
                )
            ],
        )
        with session_scope() as session:
            repo = DatasetRepository(session)
            run = repo.save_forecast_run(create)
            insight = repo.save_insight_report(
                run_id=run.id,
                facts=to_jsonable(payload.get("facts_full") or {}),
                recommendations=to_jsonable(report),
                source=payload["source"],
                openai_model=payload.get("openai_model"),
                notes="; ".join(payload.get("notes") or []) or None,
            )
            insight_id = insight.id
            run_id = run.id
        st.success(f"Сохранён insight #{insight_id} (run #{run_id})")


def _as_utc(value) -> datetime:
    if isinstance(value, str):
        ts = pd.Timestamp(value).to_pydatetime()
    elif hasattr(value, "to_pydatetime"):
        ts = value.to_pydatetime()
    else:
        ts = value
    if getattr(ts, "tzinfo", None) is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


main()
