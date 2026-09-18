"""Pydantic-схемы рекомендаций."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["низкая", "средняя", "высокая"]


class RecommendationItem(BaseModel):
    title: str = Field(description="Заголовок")
    action: str = Field(description="Конкретное действие")
    evidence: str = Field(description="Числовое основание из facts")
    expected_effect: str = Field(description="Ожидаемый эффект или диапазон")
    confidence: Confidence
    limitation: str = Field(description="Ограничение применимости")
    applicable_period: str = Field(description="Период применимости")


class RecommendationsReport(BaseModel):
    summary: str = Field(description="Краткое резюме на русском")
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()
