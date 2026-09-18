"""Сценарии: stress-test и факторы с eligibility."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.analytics.service import apply_filters, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.export.reports import comparison_csv, scenarios_csv
from src.scenarios.eligibility import assess_all_factors, profit_data_status
from src.scenarios.service import run_scenario_job
from src.schemas import ForecastPointCreate, ForecastRunCreate
from src.ui.charts import scenarios_compare_figure
from src.ui.feedback import empty_state, error_state, page_guard, warn_list
from src.ui.help_texts import METRIC_HELP, PAGE_INTROS, factor_help, show_factor_guide, show_glossary
from src.ui.labels import FREQ_LABELS, MODEL_LABELS, OPTIONAL_FACTOR_LABELS, label_or_raw
from src.ui.session_store import serialize_scenario_job


@page_guard
def main() -> None:
    st.title("Сценарии")
    st.caption(PAGE_INTROS["scenarios"])
    show_glossary(st)

    with session_scope() as session:
        summaries = DatasetRepository(session).list_summaries()

    if not summaries:
        empty_state("Нет сохранённых наборов.", hint="Сначала загрузите данные.")
        return

    options = {f"{item.id} — {item.name}": item for item in summaries}
    selected_label = st.selectbox("Набор данных", list(options.keys()))
    dataset = options[selected_label]

    with session_scope() as session:
        repo = DatasetRepository(session)
        series_keys = repo.list_series_keys(dataset.id)
        frame = observations_to_frame(repo.load_observations(dataset.id))

    if frame.empty:
        st.warning("В наборе нет наблюдений")
        return

    c1, c2 = st.columns(2)
    series_key = c1.selectbox(
        "Ряд",
        series_keys or ["total"],
        index=0,
        help=METRIC_HELP["series_key"],
    )
    default_horizon = 14 if dataset.frequency.upper().startswith("D") else 8
    horizon = int(
        c2.number_input(
            "Горизонт",
            min_value=1,
            max_value=365,
            value=default_horizon,
            help=METRIC_HELP["horizon"],
        )
    )

    filtered = apply_filters(frame, series_key=series_key)
    st.caption(
        f"Частота: {label_or_raw(FREQ_LABELS, dataset.frequency)} · точек: {len(filtered)}"
    )

    st.subheader("Простой сдвиг прогноза, %")
    st.caption(METRIC_HELP["stress"])
    s1, s2, s3 = st.columns(3)
    opt_pct = float(s1.number_input("Оптимистичный, %", value=10.0, step=1.0, help="Например +10% ко всему прогнозу"))
    pes_pct = float(s2.number_input("Пессимистичный, %", value=-10.0, step=1.0, help="Например −10% ко всему прогнозу"))
    custom_pct = float(s3.number_input("Свой вариант, %", value=5.0, step=1.0, help="Любой свой процент сдвига"))

    eligibility = assess_all_factors(filtered)
    st.subheader("Какие факторы можно крутить")
    st.caption(METRIC_HELP["eligibility"])
    elig_rows = []
    for e in eligibility:
        elig_rows.append(
            {
                "фактор": label_or_raw(OPTIONAL_FACTOR_LABELS, e.factor),
                "код в данных": e.factor,
                "доступен": "да" if e.eligible else "нет",
                "заполнено точек": e.n_non_null,
                "разных значений": e.n_unique,
                "уверенность": e.confidence,
                "что это": factor_help(e.factor).split(".")[0] + ".",
                "почему": "; ".join(e.reasons) if e.reasons else "достаточно истории",
            }
        )
    if elig_rows:
        st.dataframe(elig_rows, use_container_width=True)
        show_factor_guide(st, codes=[e.factor for e in eligibility])
    else:
        st.caption("В наборе нет дополнительных числовых факторов (скидка, реклама и т.п.)")
        show_factor_guide(st)

    profit_status = profit_data_status(filtered)
    if not profit_status.get("available"):
        st.info(profit_status.get("hint") or METRIC_HELP["profit"])
    else:
        st.success(
            "Прибыль и окупаемость доступны: в данных есть маржа или себестоимость с ценой."
        )

    eligible = [e for e in eligibility if e.eligible]
    factor_values: dict[str, float] = {}
    if eligible:
        st.subheader("Что если изменить фактор")
        st.caption(
            "Двигайте ползунок и нажмите «Рассчитать». "
            "Старт = последнее значение из истории (сценарий «как сейчас»). "
            "Текст под ползунком объясняет фактор; «?» — то же кратко."
        )
        for e in eligible:
            label = label_or_raw(OPTIONAL_FACTOR_LABELS, e.factor)
            hist_vals = pd.to_numeric(filtered[e.factor], errors="coerce").dropna()
            default = float(hist_vals.iloc[-1]) if not hist_vals.empty else (
                e.mean_value if e.mean_value is not None else 0.0
            )
            lo = e.min_value if e.min_value is not None else default - 1
            hi = e.max_value if e.max_value is not None else default + 1
            span = max(hi - lo, 1.0)
            value = st.slider(
                label,
                min_value=float(lo - 0.2 * span),
                max_value=float(hi + 0.2 * span),
                value=float(default),
                key=f"factor_{e.factor}",
                help=factor_help(e.factor),
            )
            factor_values[e.factor] = float(value)
            st.caption(factor_help(e.factor))
            if e.factor == "discount_pct" and not e.can_optimize_levels:
                st.caption(
                    "Скидка в истории почти не менялась — тонкий подбор «лучшей скидки» ограничен."
                )
    else:
        st.caption("Нет факторов, которыми можно управлять на этих данных")

    if st.button("Рассчитать сценарии", type="primary"):
        with st.spinner("Считаем базовый прогноз и варианты…"):
            job = run_scenario_job(
                filtered,
                frequency=dataset.frequency,
                horizon=horizon,
                optimistic_pct=opt_pct,
                pessimistic_pct=pes_pct,
                custom_pct=custom_pct,
                factor_values=factor_values or None,
                model_choice="seasonal_naive",
                include_prophet=False,
            )
        st.session_state["scenario_job"] = serialize_scenario_job(
            job, dataset_id=dataset.id, series_key=series_key
        )

    payload = st.session_state.get("scenario_job")
    if not payload or payload.get("dataset_id") != dataset.id or payload.get("series_key") != series_key:
        empty_state("Задайте параметры и нажмите «Рассчитать сценарии».")
        return

    warn_list(list(payload.get("notes") or []))

    if not payload.get("base_points"):
        error_state("Нет базового прогноза для сценариев")
        return

    st.subheader("Сравнение")
    st.caption(
        f"Базовая модель: {label_or_raw(MODEL_LABELS, payload['base_model'])} · "
        f"горизонт: {payload['horizon']}"
    )
    comparison = payload.get("comparison") or []
    st.dataframe(comparison, use_container_width=True)
    if comparison:
        st.download_button(
            "Скачать сравнение CSV",
            data=comparison_csv(comparison),
            file_name=f"scenarios_compare_{dataset.id}.csv",
            mime="text/csv",
        )

    chart_series = [
        {
            "name": "Базовый",
            "points": [{"ds": p["ds"], "yhat": p["yhat"]} for p in payload["base_points"]],
        }
    ]
    stress_list = payload.get("stress") or []
    if stress_list:
        st.caption(
            stress_list[0].get("disclaimer")
            or "Простой сдвиг прогноза на ±% — не оценка причинности фактора."
        )
    for s in stress_list:
        chart_series.append(
            {
                "name": s["name"],
                "points": [{"ds": p["ds"], "yhat": p["yhat"]} for p in s.get("points") or []],
            }
        )
    for f in payload.get("factors") or []:
        if not f.get("allowed"):
            continue
        label = label_or_raw(OPTIONAL_FACTOR_LABELS, f["factor"])
        chart_series.append(
            {
                "name": f"{label}={f['scenario_value']:g}",
                "points": [{"ds": p["ds"], "yhat": p["yhat"]} for p in f.get("points") or []],
            }
        )
        st.caption(
            f"{label}: оценка «что если» по истории "
            f"(на 1 единицу фактора ≈ {f.get('effect_per_unit'):.4g}; "
            f"ошибка с фактором / без: {f.get('mae_with'):.3f} / {f.get('mae_without'):.3f}). "
            "Связь в прошлом ≠ доказанная причина."
        )

    st.plotly_chart(scenarios_compare_figure(chart_series), use_container_width=True)
    st.download_button(
        "Скачать сценарии CSV",
        data=scenarios_csv(payload),
        file_name=f"scenarios_{dataset.id}_{series_key}.csv",
        mime="text/csv",
    )

    profit = payload.get("profit")
    if profit is not None:
        st.subheader("Прибыль и окупаемость")
        st.caption(METRIC_HELP["profit"])
        if profit.get("available"):
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Прибыль (база)", f"{profit['base_profit']:,.2f}")
            p2.metric("Прибыль (сценарий)", f"{profit['scenario_profit']:,.2f}")
            p3.metric("Разница прибыли", f"{profit['delta_profit']:,.2f}")
            p4.metric(
                "Окупаемость (ROI), %",
                "—" if profit.get("roi_pct") is None else f"{profit['roi_pct']:.1f}",
                help="Насколько доп. затраты окупились приростом прибыли",
            )
        else:
            st.info(profit.get("hint") or "Недостаточно данных для прибыли")

    if st.button("Сохранить сценарии в PostgreSQL"):
        points: list[ForecastPointCreate] = []
        for p in payload["base_points"]:
            points.append(
                ForecastPointCreate(
                    ds=_as_utc(p["ds"]),
                    yhat=float(p["yhat"]),
                    yhat_lower=None if p.get("yhat_lower") is None else float(p["yhat_lower"]),
                    yhat_upper=None if p.get("yhat_upper") is None else float(p["yhat_upper"]),
                    scenario_type="base",
                )
            )
        for s in payload.get("stress") or []:
            for p in s.get("points") or []:
                points.append(
                    ForecastPointCreate(
                        ds=_as_utc(p["ds"]),
                        yhat=float(p["yhat"]),
                        yhat_lower=None if p.get("yhat_lower") is None else float(p["yhat_lower"]),
                        yhat_upper=None if p.get("yhat_upper") is None else float(p["yhat_upper"]),
                        scenario_type=s["scenario_type"],
                        scenario_factors={"pct_change": s.get("pct_change")},
                    )
                )
        for f in payload.get("factors") or []:
            if not f.get("allowed"):
                continue
            for p in f.get("points") or []:
                points.append(
                    ForecastPointCreate(
                        ds=_as_utc(p["ds"]),
                        yhat=float(p["yhat"]),
                        yhat_lower=None if p.get("yhat_lower") is None else float(p["yhat_lower"]),
                        yhat_upper=None if p.get("yhat_upper") is None else float(p["yhat_upper"]),
                        scenario_type=f["scenario_type"],
                        scenario_factors={
                            f["factor"]: f["scenario_value"],
                            "baseline": f["baseline_value"],
                            "coef": f["effect_per_unit"],
                        },
                    )
                )
        create = ForecastRunCreate(
            dataset_id=dataset.id,
            series_key=series_key,
            model_name="scenario",
            model_version="1.0",
            train_start=_as_utc(filtered["ds"].iloc[0]),
            train_end=_as_utc(filtered["ds"].iloc[-1]),
            horizon=int(payload["horizon"]),
            config=payload.get("config") or {},
            metrics={
                "comparison": comparison,
                "eligibility": payload.get("eligibility") or [],
                "profit": profit if profit else payload.get("profit_status"),
            },
            quality_status="scenario",
            points=points,
        )
        with session_scope() as session:
            run = DatasetRepository(session).save_forecast_run(create)
            run_id = run.id
        st.success(f"Сохранён сценарный запуск #{run_id}")


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
