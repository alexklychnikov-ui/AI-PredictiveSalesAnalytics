"""Оркестрация: rules всегда; OpenAI опционально с fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.config import get_settings
from src.recommendations.cache import cache_get, cache_set
from src.recommendations.facts import build_facts_payload, to_jsonable
from src.recommendations.openai_client import generate_openai_report, openai_available
from src.recommendations.rules import build_rule_recommendations
from src.recommendations.schemas import RecommendationsReport
from src.recommendations.validate import validate_report_numbers


@dataclass
class InsightJobResult:
    facts: dict[str, Any]
    report: RecommendationsReport
    source: str  # rules | openai | openai_fallback_rules | cache
    openai_model: str | None = None
    notes: list[str] = field(default_factory=list)
    validation_ok: bool = True
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts_hash": self.facts.get("facts_hash"),
            "source": self.source,
            "openai_model": self.openai_model,
            "notes": self.notes,
            "validation_ok": self.validation_ok,
            "validation_errors": self.validation_errors,
            "report": self.report.to_dict(),
        }


def run_insight_job(
    history: pd.DataFrame,
    *,
    frequency: str,
    horizon: int = 14,
    dataset_meta: dict[str, Any] | None = None,
    use_openai: bool = True,
    include_prophet: bool = False,
    force_refresh: bool = False,
) -> InsightJobResult:
    facts = build_facts_payload(
        history,
        frequency=frequency,
        horizon=horizon,
        dataset_meta=dataset_meta,
        include_prophet=include_prophet,
    )
    facts = to_jsonable(facts)
    fhash = str(facts.get("facts_hash"))
    cache_key = f"{fhash}|openai={1 if use_openai else 0}"
    if not force_refresh:
        cached = cache_get(cache_key)
        if cached is not None:
            report = RecommendationsReport.model_validate(cached["report"])
            return InsightJobResult(
                facts=facts,
                report=report,
                source="cache",
                openai_model=cached.get("openai_model"),
                notes=list(cached.get("notes") or ["Взято из кэша по facts_hash"]),
                validation_ok=True,
            )

    rules_report = build_rule_recommendations(facts)
    notes: list[str] = []

    if not use_openai or not openai_available():
        if use_openai and not openai_available():
            notes.append("OPENAI_API_KEY отсутствует — использованы rule-based рекомендации")
        result = InsightJobResult(
            facts=facts,
            report=rules_report,
            source="rules",
            openai_model=None,
            notes=notes,
            validation_ok=True,
        )
        cache_set(
            cache_key,
            {
                "report": result.report.to_dict(),
                "openai_model": None,
                "notes": notes,
                "source": "rules",
            },
        )
        return result

    try:
        ai_report = generate_openai_report(facts)
        ok, errors = validate_report_numbers(ai_report, facts)
        if not ok:
            notes.append("OpenAI вернул числа вне facts — fallback на rules")
            notes.extend(errors[:5])
            result = InsightJobResult(
                facts=facts,
                report=rules_report,
                source="openai_fallback_rules",
                openai_model=None,
                notes=notes,
                validation_ok=False,
                validation_errors=errors,
            )
        else:
            model_name = get_settings().openai_model
            result = InsightJobResult(
                facts=facts,
                report=ai_report,
                source="openai",
                openai_model=model_name,
                notes=notes,
                validation_ok=True,
            )
    except Exception as exc:  # noqa: BLE001
        notes.append(f"OpenAI недоступен ({type(exc).__name__}) — fallback на rules")
        result = InsightJobResult(
            facts=facts,
            report=rules_report,
            source="openai_fallback_rules",
            openai_model=None,
            notes=notes,
            validation_ok=False,
            validation_errors=[str(exc)],
        )

    cache_set(
        cache_key,
        {
            "report": result.report.to_dict(),
            "openai_model": result.openai_model,
            "notes": result.notes,
            "source": result.source,
        },
    )
    return result
