"""Аналитика выбранного набора данных."""

from __future__ import annotations

import streamlit as st

from src.analytics.service import apply_filters, build_analytics_report, observations_to_frame
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.ui.charts import (
    anomalies_figure,
    contribution_figure,
    history_with_rolling_figure,
    profile_bar_figure,
)
from src.ui.feedback import page_guard
from src.ui.help_texts import METRIC_HELP, PAGE_INTROS, show_glossary
from src.ui.labels import FREQ_LABELS, OPTIONAL_FACTOR_LABELS, label_or_raw


@page_guard
def main() -> None:
    st.title("Аналитика")
    st.caption(PAGE_INTROS["analytics"])
    show_glossary(st)
    with session_scope() as session:
        summaries = DatasetRepository(session).list_summaries()

    if not summaries:
        st.info("Нет сохранённых наборов. Сначала загрузите данные.")
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
    series_key = c1.selectbox("Ряд", series_keys or ["total"], index=0)
    dim_filters: dict[str, str] = {}
    dim_cols = [c.replace("dim_", "") for c in frame.columns if str(c).startswith("dim_")]
    if dim_cols:
        dim_key = c2.selectbox("Измерение", ["(нет)"] + dim_cols)
        if dim_key != "(нет)":
            values = sorted({str(v) for v in frame[f"dim_{dim_key}"].dropna().unique()})
            if values:
                dim_value = st.selectbox(f"Значение «{dim_key}»", values)
                dim_filters[dim_key] = dim_value

    filtered = apply_filters(frame, series_key=series_key, dimension_filters=dim_filters or None)
    if filtered.empty:
        st.warning("После фильтрации данных не осталось")
        return

    report = build_analytics_report(filtered, frequency=dataset.frequency)
    kpi = report.kpi

    st.subheader("Ключевые цифры за период")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Сумма", f"{kpi.total:,.2f}", help=METRIC_HELP["kpi_total"])
    m2.metric("Среднее", f"{kpi.mean:,.2f}", help=METRIC_HELP["kpi_mean"])
    m3.metric("Последнее", f"{kpi.last_value:,.2f}", help=METRIC_HELP["kpi_last"])
    m4.metric(
        "Изменение к пред. окну",
        "—" if kpi.prev_period_change_pct is None else f"{kpi.prev_period_change_pct:.1f}%",
        help=METRIC_HELP["prev_change"],
    )
    m5.metric(
        "Насколько «скачет» ряд",
        "—" if kpi.volatility is None else f"{kpi.volatility:.2f}",
        help=METRIC_HELP["volatility"],
    )
    st.caption(
        f"Частота: {label_or_raw(FREQ_LABELS, dataset.frequency)} · точек: {kpi.points} · "
        f"мин {kpi.min_value:,.2f} ({kpi.min_date}) · макс {kpi.max_value:,.2f} ({kpi.max_date})"
    )

    st.subheader("История и тренд")
    t = report.trend
    st.write(
        f"Наклон: {t.slope_per_period:.4f} за период"
        + (f" ({t.slope_pct_per_period:.3f}% от среднего)" if t.slope_pct_per_period is not None else "")
        + (
            f" · недавнее vs ранее: {t.recent_vs_earlier_pct:.1f}%"
            if t.recent_vs_earlier_pct is not None
            else ""
        )
    )
    st.plotly_chart(history_with_rolling_figure(filtered, t.rolling_mean), use_container_width=True)

    st.subheader("Сезонность")
    s = report.seasonality
    for note in s.notes:
        st.caption(note)
    c3, c4 = st.columns(2)
    if s.by_dow:
        c3.plotly_chart(profile_bar_figure(s.by_dow, "Профиль дня недели"), use_container_width=True)
    if s.by_month:
        c4.plotly_chart(profile_bar_figure(s.by_month, "Профиль месяца"), use_container_width=True)
    if s.by_quarter:
        st.plotly_chart(profile_bar_figure(s.by_quarter, "Профиль квартала"), use_container_width=True)
    st.write(
        "Сила сезонности — "
        f"недельная: {'—' if s.weekly_strength is None else f'{s.weekly_strength:.2f}'}, "
        f"годовая: {'—' if s.yearly_strength is None else f'{s.yearly_strength:.2f}'}"
    )

    st.subheader("Аномалии")
    a = report.anomalies
    st.write(f"Метод: {a.method.upper()} · найдено: {a.count}")
    st.plotly_chart(anomalies_figure(filtered, a.points), use_container_width=True)
    if a.points:
        st.dataframe(a.points, use_container_width=True)

    st.subheader("Связь факторов с продажами")
    corr = report.correlations
    st.info(corr.disclaimer)
    st.caption(
        "Числа от −1 до +1: ближе к +1 — росли/падали вместе; ближе к −1 — двигались в разные стороны; "
        "около 0 — явной связи почти нет. Это не доказательство причины."
    )
    if corr.pairs:
        st.dataframe(
            [
                {
                    "Фактор": label_or_raw(OPTIONAL_FACTOR_LABELS, p["factor"]),
                    "Код в данных": p["factor"],
                    "Вместе линейно": p["pearson"],
                    "Вместе по порядку": p["spearman"],
                    "Сдвиг назад, периодов": p["best_lag"],
                    "Связь со сдвигом": p["best_lag_pearson"],
                    "Точек учтено": p["n"],
                }
                for p in corr.pairs
            ],
            use_container_width=True,
        )
    else:
        st.caption("Числовых факторов недостаточно, чтобы оценить связь с продажами")

    if report.category_contribution:
        st.subheader("Вклад категорий")
        st.plotly_chart(contribution_figure(report.category_contribution), use_container_width=True)


main()
