"""Санитизация пользовательских строк перед facts/OpenAI."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?(previous|above)\s+instructions|"
    r"system\s*prompt|"
    r"<\s*/?\s*system\s*>|"
    r"```|"
    r"\bdo\s+not\s+follow\b|"
    r"\boverride\s+rules\b)",
    re.IGNORECASE,
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")


def sanitize_text(value: str, *, max_len: int = 200) -> str:
    text = unicodedata.normalize("NFKC", str(value))
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    text = _INJECTION_RE.sub("[filtered]", text)
    text = " ".join(text.split())
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def sanitize_tree(obj: Any, *, max_len: int = 200) -> Any:
    if isinstance(obj, str):
        return sanitize_text(obj, max_len=max_len)
    if isinstance(obj, dict):
        return {
            sanitize_text(str(k), max_len=64): sanitize_tree(v, max_len=max_len)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [sanitize_tree(v, max_len=max_len) for v in obj[:50]]
    return obj


def sanitize_mapping(payload: dict[str, Any] | None, *, max_len: int = 200) -> dict[str, Any]:
    if not payload:
        return {}
    cleaned = sanitize_tree(payload, max_len=max_len)
    return cleaned if isinstance(cleaned, dict) else {}


def looks_like_secret(text: str) -> bool:
    """Эвристика для литералов секретов (не для шаблонов URL из env)."""
    if re.search(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}", text):
        return True
    if "-----BEGIN" in text and "PRIVATE KEY" in text:
        return True
    if re.search(
        r"""(?i)(?:api[_-]?key|password|secret|token)\s*=\s*['\"][^'\"]{12,}['\"]""",
        text,
    ):
        if "change_me" in text.lower() or "your_" in text.lower() or "os.environ" in text:
            return False
        if "Field(" in text or "alias=" in text:
            return False
        return True
    return False
