"""Проверка, что AI не выдумал числа вне facts."""

from __future__ import annotations

import re
from typing import Any

from src.recommendations.facts import collect_numbers
from src.recommendations.schemas import RecommendationsReport

_NUM_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)?%?")


def extract_numbers_from_text(text: str) -> list[float]:
    found: list[float] = []
    for raw in _NUM_RE.findall(text or ""):
        token = raw.replace("%", "").replace(",", ".")
        try:
            found.append(float(token))
        except ValueError:
            continue
    return found


def _close_enough(value: float, allowed: set[float], *, rel: float = 0.02, abs_tol: float = 0.05) -> bool:
    for a in allowed:
        if abs(value - a) <= max(abs_tol, rel * max(1.0, abs(a))):
            return True
        # целые округления
        if abs(value - round(a)) <= abs_tol:
            return True
    return False


def validate_report_numbers(
    report: RecommendationsReport,
    facts: dict[str, Any],
) -> tuple[bool, list[str]]:
    allowed = set(facts.get("allowed_numbers") or [])
    allowed |= collect_numbers(facts)

    violations: list[str] = []
    blobs = [report.summary]
    blobs.extend(report.caveats)
    for item in report.recommendations:
        blobs.extend(
            [
                item.title,
                item.action,
                item.evidence,
                item.expected_effect,
                item.limitation,
                item.applicable_period,
            ]
        )
    for blob in blobs:
        for num in extract_numbers_from_text(blob):
            if not _close_enough(num, allowed):
                violations.append(f"Число {num} отсутствует в facts")
    return len(violations) == 0, violations
