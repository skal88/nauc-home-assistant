"""Tests for the broken-link repair issues."""

from __future__ import annotations

from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nauc_link.const import DOMAIN, LINK_HEALTH_INTERVAL

BROKEN_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def frozen_today(freezer: FrozenDateTimeFactory) -> None:
    """Keep time fixed so the link-health cache is predictable."""
    freezer.move_to("2026-11-09T12:00:00+00:00")


def _issues(hass: HomeAssistant) -> dict[str, ir.IssueEntry]:
    return {
        issue_id: issue
        for (domain, issue_id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    }


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_api")
async def test_issue_per_broken_link(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A broken link raises an issue that says which one and why."""
    await _setup(hass, config_entry)

    issues = _issues(hass)
    assert list(issues) == [f"broken_link_{config_entry.entry_id}_{BROKEN_ID}"]
    issue = next(iter(issues.values()))
    assert issue.translation_key == "broken_link"
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.learn_more_url == f"https://app.nauc.link/links/{BROKEN_ID}"
    assert issue.translation_placeholders == {
        "name": "Carta del bar",
        "short_url": "https://qr.nauc.link/menu",
        "destination": "https://bar-ejemplo.es/carta.pdf",
        "reason": "HTTP 404",
    }


async def test_issue_clears_when_link_recovers(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Once the destination works again the issue goes away by itself."""
    await _setup(hass, config_entry)
    assert _issues(hass)

    mock_api.link_health.return_value = [
        {"shortId": BROKEN_ID, "status": "ok", "broken": False}
    ]
    freezer.tick(LINK_HEALTH_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _issues(hass) == {}
    assert hass.states.get("sensor.ana_example_com_broken_links").state == "0"


async def test_error_shown_when_there_is_no_status_code(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """A DNS or TLS failure has no HTTP status: the error is the reason."""
    mock_api.link_health_detail.return_value = [
        {
            "url": "https://gone.example",
            "status": "broken",
            "error": "ENOTFOUND",
        },
        {"url": "https://fine.example", "status": "ok"},
    ]
    await _setup(hass, config_entry)

    issue = next(iter(_issues(hass).values()))
    assert issue.translation_placeholders["reason"] == "ENOTFOUND"
    link = hass.states.get("sensor.ana_example_com_broken_links").attributes["links"][0]
    assert link["destination"] == "https://gone.example"
    # A single failing destination needs no list.
    assert "destinations" not in link


async def test_several_broken_destinations_are_listed(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """Programmable links and menus can fail on more than one destination."""
    mock_api.link_health_detail.return_value = [
        {"url": "https://a.example", "status": "broken", "statusCode": 500},
        {"url": "https://b.example", "status": "broken", "statusCode": 404},
    ]
    await _setup(hass, config_entry)

    link = hass.states.get("sensor.ana_example_com_broken_links").attributes["links"][0]
    assert [d["reason"] for d in link["destinations"]] == ["HTTP 500", "HTTP 404"]


@pytest.mark.usefixtures("mock_api")
async def test_issues_removed_with_the_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Deleting the account leaves no orphan issues behind."""
    await _setup(hass, config_entry)
    assert _issues(hass)

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert _issues(hass) == {}
