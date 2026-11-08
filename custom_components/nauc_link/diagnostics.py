"""Diagnostics for NAUC.link."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import NaucConfigEntry

TO_REDACT = {"token", "access_token", "refresh_token", "id_token", "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NaucConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, without tokens or identity."""
    data = entry.runtime_data.data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "data": asdict(data) if data else None,
    }
