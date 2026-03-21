from __future__ import annotations

from typing import Any, Dict, Optional, Sequence


def normalize_id(v: Any) -> Any:
    """Return a usable scalar id from either an int/str or {'id': ...}-style objects."""
    if isinstance(v, dict):
        return v.get("id") or v.get("Id") or v.get("doorId") or v.get("userId")
    return v


def find_by_id(
    items: Sequence[Dict[str, Any]] | None,
    item_id: Any,
    key: str = "id",
) -> Optional[Dict[str, Any]]:
    """Find first dict in items where normalize_id(item[key]) == item_id."""
    if not items:
        return None
    for it in items:
        val = normalize_id(it.get(key))
        if val == item_id:
            return it
    return None
