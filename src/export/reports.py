"""Экспорт CSV и текстового отчёта."""

from __future__ import annotations

import csv
import io
from typing import Any


def forecast_points_csv(points: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["ds", "yhat", "yhat_lower", "yhat_upper"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in points:
        writer.writerow(
            {
                "ds": row.get("ds"),
                "yhat": row.get("yhat"),
                "yhat_lower": row.get("yhat_lower"),
                "yhat_upper": row.get("yhat_upper"),
            }
        )
    return buf.getvalue()


def scenarios_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["scenario", "scenario_type", "ds", "yhat", "yhat_lower", "yhat_upper"],
    )
    writer.writeheader()
    for p in payload.get("base_points") or []:
        writer.writerow(
            {
                "scenario": "Базовый",
                "scenario_type": "base",
                "ds": p.get("ds"),
                "yhat": p.get("yhat"),
                "yhat_lower": p.get("yhat_lower"),
                "yhat_upper": p.get("yhat_upper"),
            }
        )
    for s in payload.get("stress") or []:
        for p in s.get("points") or []:
            writer.writerow(
                {
                    "scenario": s.get("name"),
                    "scenario_type": s.get("scenario_type"),
                    "ds": p.get("ds"),
                    "yhat": p.get("yhat"),
                    "yhat_lower": p.get("yhat_lower"),
                    "yhat_upper": p.get("yhat_upper"),
                }
            )
    for f in payload.get("factors") or []:
        if not f.get("allowed"):
            continue
        label = f"{f.get('factor')}={f.get('scenario_value')}"
        for p in f.get("points") or []:
            writer.writerow(
                {
                    "scenario": label,
                    "scenario_type": f.get("scenario_type"),
                    "ds": p.get("ds"),
                    "yhat": p.get("yhat"),
                    "yhat_lower": p.get("yhat_lower"),
                    "yhat_upper": p.get("yhat_upper"),
                }
            )
    return buf.getvalue()


def recommendations_text_report(payload: dict[str, Any]) -> str:
    report = payload.get("report") or {}
    lines = [
        "Отчёт рекомендаций — AI-PredictiveSalesAnalytics",
        f"Источник: {payload.get('source')}",
        f"Модель OpenAI: {payload.get('openai_model') or '—'}",
        f"facts_hash: {payload.get('facts_hash') or '—'}",
        "",
        "Резюме",
        report.get("summary") or "—",
        "",
        "Рекомендации",
    ]
    for i, item in enumerate(report.get("recommendations") or [], start=1):
        lines.extend(
            [
                f"{i}. {item.get('title')} [{item.get('confidence')}]",
                f"   Действие: {item.get('action')}",
                f"   Основание: {item.get('evidence')}",
                f"   Эффект: {item.get('expected_effect')}",
                f"   Ограничение: {item.get('limitation')}",
                f"   Период: {item.get('applicable_period')}",
                "",
            ]
        )
    caveats = report.get("caveats") or []
    if caveats:
        lines.append("Оговорки")
        for c in caveats:
            lines.append(f"- {c}")
        lines.append("")
    notes = payload.get("notes") or []
    if notes:
        lines.append("Служебные заметки")
        for n in notes:
            lines.append(f"- {n}")
    return "\n".join(lines).strip() + "\n"


def comparison_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "сценарий,тип,сумма,Δ к базе,Δ %\n"
    buf = io.StringIO()
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
