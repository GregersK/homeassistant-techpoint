from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence, Tuple


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


# Maps a TechPoint entity unique_id suffix to (kind, data snapshot key).
# kind/data_key pairs double as the coordinator snapshot key for that resource.
_UID_PATTERNS: list[Tuple[re.Pattern, str]] = [
    (re.compile(r"^door_(?P<id>\d+)_(?P<sub>lock|open|sabotage|status|mode|pulse)$"), "door"),
    (re.compile(r"^zone_(?P<id>\d+)$"), "zone"),
    (re.compile(r"^area_(?P<id>\d+)$"), "area"),
    (re.compile(r"^io_input_(?P<id>\d+)$"), "io_input"),
    (re.compile(r"^io_output_(?P<id>\d+)$"), "io_output"),
]

# kind -> coordinator snapshot key holding the list of current objects of that kind.
UID_KIND_TO_DATA_KEY: Dict[str, str] = {
    "door": "doors",
    "zone": "zones",
    "area": "areas",
    "io_input": "io_inputs",
    "io_output": "io_outputs",
}


def parse_techpoint_unique_id(entry_id: str, unique_id: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """Parse a TechPoint entity unique_id into (kind, object_id, sub_kind).

    kind is one of door/zone/area/io_input/io_output. sub_kind distinguishes the
    per-door sub-entities (lock/open/sabotage/status/mode/pulse); None for the rest.
    Returns None for controller-level entities that don't reference a specific
    door/zone/area/IO (e.g. cardholder_count, threat_level, event_log).
    """
    if not unique_id.startswith(f"{entry_id}_"):
        return None
    suffix = unique_id[len(entry_id) + 1:]
    for pattern, kind in _UID_PATTERNS:
        m = pattern.match(suffix)
        if m:
            return kind, m.group("id"), m.groupdict().get("sub")
    return None
