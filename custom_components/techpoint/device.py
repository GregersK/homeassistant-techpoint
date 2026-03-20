from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL_CONTROLLER,
    DEFAULT_DEVICE_GROUPING,
    GROUP_BY_ITEM,
    GROUP_BY_TYPE,
)


@dataclass(frozen=True)
class DeviceContext:
    """Context used to build device registry entries."""

    entry_id: str
    controller_name: str


def build_device_info(
    ctx: DeviceContext,
    grouping: Optional[str],
    kind: str,
    *,
    item_id: Optional[str | int] = None,
    item_name: Optional[str] = None,
) -> DeviceInfo:
    """Return DeviceInfo for either grouped devices or per-item devices.

    kind must be one of: "door", "doors", "zone", "zones", "area", "areas".
    If grouping is GROUP_BY_ITEM, item_id is required.
    """

    grouping = grouping or DEFAULT_DEVICE_GROUPING

    # Normalize kind tokens
    kind_low = kind.lower()
    if kind_low in ("door", "doors"):
        singular, plural = "door", "doors"
        model_item = f"{MODEL_CONTROLLER} Door"
        model_group = f"{MODEL_CONTROLLER} Doors"
        group_name = f"{ctx.controller_name} - Døre"
        item_prefix = "Dør"
    elif kind_low in ("zone", "zones"):
        singular, plural = "zone", "zones"
        model_item = f"{MODEL_CONTROLLER} Zone"
        model_group = f"{MODEL_CONTROLLER} Zones"
        group_name = f"{ctx.controller_name} - Zoner"
        item_prefix = "Zone"
    elif kind_low in ("area", "areas"):
        singular, plural = "area", "areas"
        model_item = f"{MODEL_CONTROLLER} Area"
        model_group = f"{MODEL_CONTROLLER} Areas"
        group_name = f"{ctx.controller_name} - Områder"
        item_prefix = "Area"
    else:
        # Fallback: treat as grouped type
        singular, plural = kind_low, f"{kind_low}s"
        model_item = f"{MODEL_CONTROLLER} {kind_low.title()}"
        model_group = f"{MODEL_CONTROLLER} {plural.title()}"
        group_name = f"{ctx.controller_name} - {plural.title()}"
        item_prefix = kind_low.title()

    if grouping == GROUP_BY_ITEM:
        if item_id is None:
            raise ValueError("item_id is required when grouping=GROUP_BY_ITEM")

        # Reuse legacy identifier format from earlier versions so HA can reattach.
        identifier = f"{ctx.entry_id}_{singular}_{item_id}"

        name = (item_name or str(item_id)).strip()
        if name and not name.lower().startswith(item_prefix.lower()):
            name = f"{item_prefix} {name}"

        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=name,
            manufacturer=MANUFACTURER,
            model=model_item,
            via_device=(DOMAIN, ctx.entry_id),
        )

    # GROUP_BY_TYPE
    return DeviceInfo(
        identifiers={(DOMAIN, f"{ctx.entry_id}_{plural}")},
        name=group_name,
        manufacturer=MANUFACTURER,
        model=model_group,
        via_device=(DOMAIN, ctx.entry_id),
    )
