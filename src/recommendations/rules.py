"""Rule-based рекомендации без OpenAI."""

from __future__ import annotations

from typing import Any

from src.recommendations.schemas import RecommendationItem, RecommendationsReport


def build_rule_recommendations(facts: dict[str, Any]) -> RecommendationsReport:
    items: list[RecommendationItem] = []
    caveats: list[str] = list(facts.get("limitations") or [])

    forecast = facts.get("forecast") or {}
    analytics = facts.get("analytics") or {}
    scenarios = facts.get("scenarios") or {}
    period = facts.get("period") or {}

    quality = forecast.get("quality_status") or "unknown"
    selected = forecast.get("selected_model")
    recommended = forecast.get("recommended_model")

    metrics = forecast.get("metrics") or {}
    prop = (metrics.get("prophet") or {}).get("metrics") or {}
    base = (metrics.get("seasonal_naive") or {}).get("metrics") or {}
    prop_wape = prop.get("wape")
    base_wape = base.get("wape")

    if quality in {"unavailable", "low_confidence"} or forecast.get("history_status") == "недостаточно":
        items.append(
            RecommendationItem(
                title="Увеличить историю наблюдений",
                action="Собрать больше периодов продаж до пересчёта прогноза",
                evidence=(
                    f"Статус качества: {quality}; точек: {period.get('points')}; "
                    f"история: {forecast.get('history_status')}"
                ),
                expected_effect="Повышение устойчивости backtesting и доверия к прогнозу",
                confidence="высокая",
                limitation="Без достаточной истории уверенные рекомендации по акциям недоступны",
                applicable_period="до накопления практического минимума истории",
            )
        )

    if selected and recommended and selected != recommended:
        items.append(
            RecommendationItem(
                title="Сверить выбор модели",
                action=f"Для итогового прогноза использовать модель «{recommended}»",
                evidence=f"Выбрано: {selected}; рекомендовано по WAPE: {recommended}",
                expected_effect="Снижение ошибки относительно текущего выбора",
                confidence="средняя",
                limitation="Рекомендация основана только на backtesting WAPE",
                applicable_period=f"горизонт {forecast.get('horizon')} периодов",
            )
        )
    elif prop_wape is not None and base_wape is not None and prop_wape > base_wape:
        items.append(
            RecommendationItem(
                title="Prophet не лучше baseline",
                action="Опираться на сезонный naive либо упростить настройки Prophet",
                evidence=f"WAPE Prophet={prop_wape:.2f}; baseline={base_wape:.2f}",
                expected_effect="Избежать завышенной уверенности в сложной модели",
                confidence="высокая",
                limitation="Сравнение на одинаковых holdout-точках текущего запуска",
                applicable_period=f"горизонт {forecast.get('horizon')}",
            )
        )
    elif prop_wape is not None and base_wape is not None:
        items.append(
            RecommendationItem(
                title="Зафиксировать рабочую модель прогноза",
                action=f"Продолжать использовать «{selected or recommended}» как базовую",
                evidence=f"WAPE Prophet={prop_wape:.2f}; baseline={base_wape:.2f}; качество={quality}",
                expected_effect="Воспроизводимый прогнозный контур для сценариев",
                confidence="средняя",
                limitation="Качество зависит от стабильности ряда и длины истории",
                applicable_period=f"горизонт {forecast.get('horizon')}",
            )
        )

    season = analytics.get("seasonality") or {}
    by_dow = season.get("by_dow") or []
    if by_dow:
        best = max(by_dow, key=lambda x: x.get("value") or 0)
        worst = min(by_dow, key=lambda x: x.get("value") or 0)
        items.append(
            RecommendationItem(
                title="Учитывать недельный профиль спроса",
                action=(
                    f"Планировать акции ближе к слабому дню «{worst.get('key')}», "
                    f"а не только к пику «{best.get('key')}»"
                ),
                evidence=(
                    f"Среднее в пик {best.get('key')}={best.get('value')}; "
                    f"в спаде {worst.get('key')}={worst.get('value')}"
                ),
                expected_effect="Потенциальное сглаживание недельной волатильности (гипотеза)",
                confidence="низкая",
                limitation="Сезонный профиль ≠ причинность; нужны A/B или holdout по акциям",
                applicable_period="типичная календарная неделя при стабильном ассортименте",
            )
        )

    kpi = analytics.get("kpi") or {}
    if kpi.get("prev_period_change_pct") is not None:
        ch = kpi["prev_period_change_pct"]
        if ch < -5:
            items.append(
                RecommendationItem(
                    title="Разбрать спад к предыдущему окну",
                    action="Сверить ассортимент, цены, промо и дефицит за последнее окно",
                    evidence=f"Изменение к предыдущему окну: {ch:.1f}%",
                    expected_effect="Выявление управляемых причин спада",
                    confidence="средняя",
                    limitation="Агрегат не разделяет вклад категорий без доп. срезов",
                    applicable_period="текущий и следующий сопоставимый период",
                )
            )

    elig = scenarios.get("eligibility") or []
    eligible = [e for e in elig if e.get("eligible")]
    ineligible = [e for e in elig if not e.get("eligible")]
    if eligible:
        names = ", ".join(e.get("factor") for e in eligible[:4])
        conf_raw = str(eligible[0].get("confidence") or "низкая")
        conf: Any = conf_raw if conf_raw in {"низкая", "средняя", "высокая"} else "низкая"
        items.append(
            RecommendationItem(
                title="Осторожно тестировать доступные факторы",
                action=f"Прогонять what-if только для: {names}",
                evidence=f"Eligible факторов: {len(eligible)}; пример n={eligible[0].get('n_non_null')}",
                expected_effect="Сценарии в пределах наблюдавшегося диапазона факторов",
                confidence=conf,
                limitation="Эффект оценивается регрессией; не является доказанной эластичностью",
                applicable_period="горизонт текущего прогноза",
            )
        )
    if ineligible:
        need = ", ".join(
            f"{e.get('factor')} ({(e.get('reasons') or ['нет данных'])[0]})" for e in ineligible[:3]
        )
        caveats.append(f"Факторы недоступны для управления: {need}")

    profit = scenarios.get("profit_status") or {}
    if not profit.get("available"):
        caveats.append(profit.get("hint") or "Profit/ROI недоступен без margin/cost")
    else:
        items.append(
            RecommendationItem(
                title="Считать прибыль, не только выручку",
                action="При сценариях бюджета сверять Δ прибыли и ROI, а не только yhat",
                evidence=f"Режим прибыли: {profit.get('mode')}; полей: {profit.get('fields')}",
                expected_effect="Отсечение сценариев с ростом выручки без маржи",
                confidence="средняя",
                limitation="Маржа усреднена по истории; структура затрат может меняться",
                applicable_period="сценарии с изменением spend/цены",
            )
        )

    comparison = scenarios.get("comparison") or []
    stress = next((r for r in comparison if r.get("тип") == "stress_pessimistic"), None)
    if stress and stress.get("Δ %") is not None:
        items.append(
            RecommendationItem(
                title="Заложить стресс-сценарий",
                action="Проверить устойчивость плана при пессимистичном % stress-test",
                evidence=(
                    f"Пессимистичный stress: сумма={stress.get('сумма')}; "
                    f"Δ%={stress.get('Δ %')}"
                ),
                expected_effect="Понимание чувствительности плана к отклонению прогноза",
                confidence="средняя",
                limitation="Stress-test не моделирует причинный шок фактора",
                applicable_period=f"горизонт {forecast.get('horizon')}",
            )
        )

    if not items:
        items.append(
            RecommendationItem(
                title="Продолжить мониторинг KPI",
                action="Пересчитывать аналитику и прогноз после каждого существенного обновления данных",
                evidence=f"Точек в ряде: {period.get('points')}; качество={quality}",
                expected_effect="Своевременное обнаружение смены режима ряда",
                confidence="низкая",
                limitation="Недостаточно сигналов для точечных действий",
                applicable_period="текущий операционный цикл",
            )
        )

    # confidence must be valid literal
    fixed: list[RecommendationItem] = []
    for it in items:
        conf = it.confidence if it.confidence in {"низкая", "средняя", "высокая"} else "низкая"
        fixed.append(it.model_copy(update={"confidence": conf}))

    summary = (
        f"Сформированы рекомендации по агрегатам "
        f"(качество прогноза: {quality}, точек: {period.get('points')})."
    )
    return RecommendationsReport(summary=summary, recommendations=fixed[:8], caveats=caveats)
