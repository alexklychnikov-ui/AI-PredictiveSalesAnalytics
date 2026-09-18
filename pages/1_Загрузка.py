"""Загрузка и контроль качества данных."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.config import get_settings
from src.data.mapper import ColumnMapping
from src.data.pipeline import preview_from_bytes, preview_ingest, to_dataset_create
from src.db.repositories import DatasetRepository
from src.db.session import session_scope
from src.ui.feedback import error_state, page_guard
from src.ui.help_texts import FACTOR_HELP, METRIC_HELP, PAGE_INTROS, show_glossary
from src.ui.labels import AGG_LABELS, FREQ_LABELS, KPI_LABELS, OPTIONAL_FACTOR_LABELS

SAMPLE_PATH = Path("sample_data/synthetic_sales.csv")
KPI_OPTIONS = list(KPI_LABELS.keys())
FREQ_OPTIONS = list(FREQ_LABELS.keys())
AGG_OPTIONS = list(AGG_LABELS.keys())


def _load_source() -> tuple[object, object] | tuple[None, None]:
    settings = get_settings()
    st.subheader("1. Источник")
    source = st.radio(
        "Откуда взять данные",
        ["Загрузить файл", "Синтетический пример"],
        horizontal=True,
        help="Учебный пример — готовая таблица без персональных данных, чтобы сразу пройти весь путь.",
    )
    if source == "Синтетический пример":
        if not SAMPLE_PATH.exists():
            st.error("Файл sample_data/synthetic_sales.csv не найден")
            return None, None
        data = SAMPLE_PATH.read_bytes()
        loaded, mapping = preview_from_bytes(data, SAMPLE_PATH.name)
        st.caption(f"Загружен пример: {SAMPLE_PATH.name} ({len(loaded.frame)} строк)")
        return loaded, mapping

    uploaded = st.file_uploader("CSV или XLSX", type=["csv", "xlsx", "xls"])
    if uploaded is None:
        return None, None
    max_bytes = settings.max_upload_mb * 1024 * 1024
    raw = uploaded.getvalue()
    if len(raw) > max_bytes:
        error_state(f"Файл больше лимита {settings.max_upload_mb} МБ")
        return None, None
    try:
        loaded, mapping = preview_from_bytes(raw, uploaded.name)
    except ValueError as exc:
        error_state("Не удалось прочитать файл", str(exc))
        return None, None
    return loaded, mapping


@page_guard
def main() -> None:
    st.title("Загрузка данных")
    st.caption(PAGE_INTROS["upload"])
    show_glossary(st)

    loaded_mapping = _load_source()
    if loaded_mapping[0] is None:
        st.info("Выберите файл или синтетический пример")
        return
    loaded, suggested = loaded_mapping

    st.subheader("2. Предпросмотр")
    st.dataframe(loaded.frame.head(20), use_container_width=True)
    st.write(f"Колонки: {list(loaded.frame.columns)}")

    st.subheader("3. Сопоставление и параметры")
    st.caption(
        "Укажите, какая колонка — дата, какая — главный показатель продаж, "
        "и при желании дополнительные поля (скидка, реклама…)."
    )
    cols = list(loaded.frame.columns)
    c1, c2 = st.columns(2)
    date_column = c1.selectbox(
        "Колонка даты",
        cols,
        index=cols.index(suggested.date_column),
        help="Когда была продажа / день учёта.",
    )
    target_column = c2.selectbox(
        "Колонка показателя",
        cols,
        index=cols.index(suggested.target_column) if suggested.target_column in cols else 0,
        help="Что прогнозируем: обычно выручка или количество.",
    )

    optional_values = {}
    opt_keys = list(suggested.optional_columns.keys())
    opt_cols = st.multiselect(
        "Дополнительные факторы (по желанию)",
        options=opt_keys,
        default=opt_keys,
        format_func=lambda key: OPTIONAL_FACTOR_LABELS.get(key, key),
        help="Необязательные поля, которые потом можно крутить в сценариях.",
    )
    for logical in opt_cols:
        default_col = suggested.optional_columns.get(logical, cols[0])
        optional_values[logical] = st.selectbox(
            f"→ {OPTIONAL_FACTOR_LABELS.get(logical, logical)}",
            cols,
            index=cols.index(default_col) if default_col in cols else 0,
            key=f"opt_{logical}",
            help=FACTOR_HELP.get(logical, "Сопоставьте с колонкой в файле."),
        )

    c3, c4, c5, c6 = st.columns(4)
    frequency = c3.selectbox(
        "Частота",
        FREQ_OPTIONS,
        format_func=lambda x: FREQ_LABELS[x],
        help=METRIC_HELP["frequency"],
    )
    agg = c4.selectbox(
        "Агрегация показателя",
        AGG_OPTIONS,
        index=0,
        format_func=lambda x: AGG_LABELS[x],
        help="Как свернуть несколько строк в один день/неделю: обычно сумма.",
    )
    target_kpi = c5.selectbox(
        "Смысл показателя",
        KPI_OPTIONS,
        index=0,
        format_func=lambda x: KPI_LABELS[x],
        help="Подпись для отчётов: выручка, штуки, заказы…",
    )
    horizon = int(
        c6.number_input(
            "Желаемый горизонт, периодов",
            min_value=1,
            max_value=365,
            value=30,
            help=METRIC_HELP["horizon"],
        )
    )
    fill_missing = st.checkbox(
        "Заполнять пропуски календаря нулями",
        value=False,
        help="Если в какие-то дни продаж не было — подставить 0, чтобы ряд был ровным.",
    )
    dataset_name = st.text_input("Имя набора", value=Path(loaded.source_name).stem)

    mapping = ColumnMapping(
        date_column=date_column,
        target_column=target_column,
        optional_columns=optional_values,
    )

    if st.button("Сформировать отчёт качества", type="primary"):
        try:
            preview = preview_ingest(
                loaded.frame,
                source_name=loaded.source_name,
                mapping=mapping,
                frequency=frequency,
                agg=agg,
                horizon=horizon,
                fill_missing_as_zero=fill_missing,
                encoding=loaded.encoding,
                separator=loaded.separator,
                sheet_name=loaded.sheet_name,
            )
        except ValueError as exc:
            error_state("Ошибка подготовки данных", str(exc))
            return
        st.session_state["ingest_preview"] = preview
        st.session_state["ingest_meta"] = {
            "name": dataset_name,
            "target_kpi": target_kpi,
            "frequency": frequency,
            "horizon": horizon,
        }

    preview = st.session_state.get("ingest_preview")
    meta = st.session_state.get("ingest_meta")
    if preview is None or meta is None:
        return

    st.subheader("4. Отчёт качества")
    q = preview.quality
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Строк: исходные → чистые", f"{q.rows_raw} → {q.rows_clean}")
    m2.metric("Статус истории", q.history.status)
    m3.metric("Горизонт", f"{q.history.requested_horizon} → {preview.allowed_horizon}")
    m4.metric("Можно прогнозировать", "да" if q.can_forecast else "нет")

    if q.warnings:
        for warning in q.warnings:
            st.warning(warning)
    else:
        st.success("Критических предупреждений нет")

    with st.expander("Технические детали отчёта"):
        st.json(q.to_dict())

    st.subheader("Нормализованный ряд")
    show = preview.transform.clean.head(50).rename(
        columns={
            "ds": "дата",
            "y": "значение",
            "series_key": "ряд",
            "dimensions": "измерения",
            "drivers": "факторы",
            "is_transformed": "преобразовано",
        }
    )
    st.dataframe(show, use_container_width=True)
    st.line_chart(preview.transform.clean.set_index("ds")["y"])

    if st.button("Сохранить в PostgreSQL", type="primary"):
        try:
            payload = to_dataset_create(
                preview,
                name=dataset_name,
                target_kpi=target_kpi,
                frequency=frequency,
            )
            with session_scope() as session:
                created = DatasetRepository(session).create_with_observations(payload)
                dataset_id = created.id
        except Exception as exc:  # noqa: BLE001
            error_state("Не удалось сохранить набор", f"{type(exc).__name__}: {exc}")
            return
        st.success(f"Сохранено: набор №{dataset_id}, точек: {len(payload.observations)}")
        st.session_state.pop("ingest_preview", None)
        st.session_state.pop("ingest_meta", None)


main()
