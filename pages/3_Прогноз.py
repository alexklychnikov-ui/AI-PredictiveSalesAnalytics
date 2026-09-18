"""Прогноз: Prophet + seasonal-naive baseline + backtesting."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.analytics.service import apply_filters, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.export.reports import forecast_points_csv
from src.forecasting.service import run_forecast_job
from src.schemas import ForecastPointCreate, ForecastRunCreate
from src.ui.charts import forecast_figure
from src.ui.feedback import empty_state, error_state, page_guard
from src.ui.help_texts import METRIC_HELP, PAGE_INTROS, show_glossary
from src.ui.labels import FREQ_LABELS, MODEL_LABELS, QUALITY_LABELS, label_or_raw
from src.ui.session_store import serialize_forecast_job


def _fmt_metric(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:.2f}{suffix}"


@page_guard
def main() -> None:
    st.title("Прогноз")
    st.caption(PAGE_INTROS["forecast"])
    show_glossary(st)
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
    default_horizon = 30 if dataset.frequency.upper().startswith("D") else 12
    horizon = int(
        c2.number_input(
            "Горизонт",
            min_value=1,
            max_value=365,
            value=default_horizon,
            step=1,
            help=METRIC_HELP["horizon"],
        )
    )
    model_choice = c3.selectbox(
        "Модель",
        options=["auto", "prophet", "seasonal_naive"],
        format_func=lambda x: label_or_raw(MODEL_LABELS, x),
        help="Авто — выбрать ту, что меньше ошибалась на проверке прошлого.",
    )

    target_wape_raw = st.number_input(
        "Целевая ошибка WAPE, % (необязательно)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=1.0,
        help=METRIC_HELP["wape"] + " 0 = не задавать порог.",
    )
    target_wape = None if target_wape_raw <= 0 else float(target_wape_raw)

    filtered = apply_filters(frame, series_key=series_key)
    st.caption(
        f"Частота: {label_or_raw(FREQ_LABELS, dataset.frequency)} · точек в ряде: {len(filtered)}"
    )

    if st.button("Рассчитать прогноз", type="primary"):
        with st.spinner("Обучение и backtesting…"):
            job = run_forecast_job(
                filtered,
                frequency=dataset.frequency,
                horizon=horizon,
                model_choice=model_choice,
                target_wape=target_wape,
            )
        st.session_state["forecast_job"] = serialize_forecast_job(
            job, dataset_id=dataset.id, series_key=series_key
        )

    payload = st.session_state.get("forecast_job")
    if not payload or payload.get("dataset_id") != dataset.id or payload.get("series_key") != series_key:
        empty_state("Задайте параметры и нажмите «Рассчитать прогноз».")
        _show_recent_runs(dataset.id)
        return

    st.subheader("Качество")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Статус", label_or_raw(QUALITY_LABELS, payload["quality_status"]))
    q2.metric("История", payload["history_status"])
    q3.metric("Рекомендация", label_or_raw(MODEL_LABELS, payload["recommended_model"]))
    q4.metric("Выбрано", label_or_raw(MODEL_LABELS, payload["selected_model"]))
    st.caption(
        f"Эффективный горизонт: {payload['horizon']} (макс. по истории {payload['max_horizon']})"
    )
    for note in payload.get("notes") or []:
        st.caption(note)
    if payload.get("unavailable_reason"):
        error_state(payload["unavailable_reason"])
        return

    st.subheader("Метрики backtesting")
    rows = []
    for m in payload.get("metrics_rows") or []:
        rows.append(
            {
                "модель": label_or_raw(MODEL_LABELS, m["модель"]),
                "MAE": _fmt_metric(m.get("mae")),
                "RMSE": _fmt_metric(m.get("rmse")),
                "WAPE %": _fmt_metric(m.get("wape")),
                "sMAPE %": _fmt_metric(m.get("smape")),
                "фолдов": m.get("folds"),
                "n": m.get("n"),
                "ошибка": m.get("error") or "",
            }
        )
    if rows:
        st.dataframe(rows, use_container_width=True)
        if payload["recommended_model"] == "seasonal_naive" and any(
            r["модель"] == label_or_raw(MODEL_LABELS, "prophet") for r in rows
        ):
            st.warning("Prophet не лучше baseline по WAPE — это показано явно.")
    else:
        st.caption("Нет метрик backtesting")

    points = payload.get("points") or []
    st.subheader("График")
    st.plotly_chart(
        forecast_figure(
            filtered,
            points,
            title=f"Прогноз ({label_or_raw(MODEL_LABELS, payload['selected_model'])})",
        ),
        use_container_width=True,
    )
    if points:
        st.dataframe(points, use_container_width=True)
        st.download_button(
            "Скачать прогноз CSV",
            data=forecast_points_csv(points),
            file_name=f"forecast_{dataset.id}_{series_key}.csv",
            mime="text/csv",
        )

    if st.button("Сохранить запуск в PostgreSQL"):
        create = ForecastRunCreate(
            dataset_id=dataset.id,
            series_key=series_key,
            model_name=payload["selected_model"],
            model_version=payload.get("model_version"),
            train_start=_as_utc(payload["train_start"]),
            train_end=_as_utc(payload["train_end"]),
            horizon=int(payload["horizon"]),
            config=payload.get("config") or {},
            metrics=payload.get("metrics_payload") or {},
            quality_status=payload["quality_status"],
            points=[
                ForecastPointCreate(
                    ds=_as_utc(p["ds"]),
                    yhat=float(p["yhat"]),
                    yhat_lower=None if p.get("yhat_lower") is None else float(p["yhat_lower"]),
                    yhat_upper=None if p.get("yhat_upper") is None else float(p["yhat_upper"]),
                    scenario_type="base",
                )
                for p in points
            ],
        )
        with session_scope() as session:
            run = DatasetRepository(session).save_forecast_run(create)
            run_id = run.id
        st.success(f"Сохранён запуск #{run_id}")

    _show_recent_runs(dataset.id)


def _as_utc(value) -> datetime:
    if isinstance(value, str):
        ts = pd.Timestamp(value).to_pydatetime()
    elif hasattr(value, "to_pydatetime"):
        ts = value.to_pydatetime()
    else:
        ts = value
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _show_recent_runs(dataset_id: int) -> None:
    with session_scope() as session:
        runs = DatasetRepository(session).list_forecast_runs(dataset_id, limit=10)
    if not runs:
        return
    st.subheader("Недавние запуски")
    st.dataframe(
        [
            {
                "id": r.id,
                "модель": label_or_raw(MODEL_LABELS, r.model_name),
                "горизонт": r.horizon,
                "качество": label_or_raw(QUALITY_LABELS, r.quality_status),
                "точек": r.points_count,
                "создан": r.created_at,
            }
            for r in runs
        ],
        use_container_width=True,
    )


main()
