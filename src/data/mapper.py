from __future__ import annotations

from dataclasses import dataclass, field

DATE_ALIASES = {
    "date",
    "ds",
    "datetime",
    "timestamp",
    "день",
    "дата",
    "period",
    "дата продажи",
}
TARGET_ALIASES = {
    "y",
    "target",
    "sales",
    "revenue",
    "amount",
    "qty",
    "quantity",
    "value",
    "продажи",
    "выручка",
    "сумма",
    "количество",
}
OPTIONAL_ALIASES: dict[str, set[str]] = {
    "discount_pct": {"discount", "discount_pct", "скидка"},
    "promo_flag": {"promo", "promo_flag", "акция"},
    "marketing_spend": {"ad_spend", "marketing_spend", "реклама", "бюджет"},
    "unit_price": {"price", "unit_price", "цена"},
    "stockout_flag": {"stockout", "stockout_flag", "дефицит"},
    "category": {"category", "категория"},
    "product_id": {"product", "product_id", "sku", "товар"},
    "channel": {"channel", "канал"},
    "region": {"region", "регион"},
    "store": {"store", "магазин"},
}


@dataclass
class ColumnMapping:
    date_column: str
    target_column: str
    optional_columns: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, str | dict[str, str]]:
        return {
            "date": self.date_column,
            "target": self.target_column,
            "optional": self.optional_columns,
        }


def _normalize(name: str) -> str:
    return " ".join(str(name).strip().lower().replace("_", " ").split())


def suggest_mapping(columns: list[str]) -> ColumnMapping:
    normalized = {_normalize(col): col for col in columns}
    date_column = next(
        (normalized[key] for key in (_normalize(alias) for alias in DATE_ALIASES) if key in normalized),
        columns[0],
    )
    remaining = [c for c in columns if c != date_column]
    target_column = next(
        (
            normalized[key]
            for key in (_normalize(alias) for alias in TARGET_ALIASES)
            if key in normalized and normalized[key] != date_column
        ),
        remaining[0] if remaining else columns[0],
    )
    optional: dict[str, str] = {}
    for logical, aliases in OPTIONAL_ALIASES.items():
        for alias in aliases:
            key = _normalize(alias)
            if key in normalized and normalized[key] not in {date_column, target_column}:
                optional[logical] = normalized[key]
                break
    return ColumnMapping(date_column=date_column, target_column=target_column, optional_columns=optional)
