"""Repair issues for NAUC.link: one per broken link."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import BrokenLink


def _issue_prefix(entry: ConfigEntry) -> str:
    # Scoped by entry so two accounts never clear each other's issues.
    return f"broken_link_{entry.entry_id}_"


@callback
def async_sync_broken_link_issues(
    hass: HomeAssistant, entry: ConfigEntry, links: list[BrokenLink]
) -> None:
    """Raise an issue per broken link and clear the ones that recovered."""
    prefix = _issue_prefix(entry)
    wanted = {f"{prefix}{link.id}": link for link in links}

    for issue_id, link in wanted.items():
        destination = link.destinations[0] if link.destinations else None
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            learn_more_url=link.manage_url,
            translation_key="broken_link",
            translation_placeholders={
                "name": link.label,
                "short_url": link.url,
                "destination": destination.url if destination else "-",
                "reason": (destination.reason if destination else None) or "-",
            },
        )

    async_delete_broken_link_issues(hass, entry, keep=set(wanted))


@callback
def async_delete_broken_link_issues(
    hass: HomeAssistant, entry: ConfigEntry, keep: set[str] | None = None
) -> None:
    """Delete this entry's broken-link issues, except those in `keep`."""
    prefix = _issue_prefix(entry)
    registry = ir.async_get(hass)
    stale = [
        issue_id
        for (domain, issue_id) in registry.issues
        if domain == DOMAIN
        and issue_id.startswith(prefix)
        and issue_id not in (keep or set())
    ]
    for issue_id in stale:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
