"""Кэш отчётов по facts_hash."""

from __future__ import annotations

from threading import Lock
from typing import Any

_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = Lock()
_MAX = 64


def cache_get(facts_hash: str) -> dict[str, Any] | None:
    with _LOCK:
        item = _CACHE.get(facts_hash)
        return None if item is None else dict(item)


def cache_set(facts_hash: str, payload: dict[str, Any]) -> None:
    with _LOCK:
        if facts_hash in _CACHE:
            _CACHE[facts_hash] = dict(payload)
            return
        if len(_CACHE) >= _MAX:
            # FIFO-ish
            oldest = next(iter(_CACHE))
            _CACHE.pop(oldest, None)
        _CACHE[facts_hash] = dict(payload)


def cache_clear() -> None:
    with _LOCK:
        _CACHE.clear()
