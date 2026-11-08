"""Tests for setting up NAUC.link and its sensors."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nauc_link.api import NaucApiError, NaucAuthError
from custom_components.nauc_link.const import OAUTH2_TOKEN, UPDATE_INTERVAL


@pytest.fixture(autouse=True)
def frozen_today(freezer: FrozenDateTimeFactory) -> None:
    """Match the `today` of the analytics fixture."""
    freezer.move_to("2026-11-09T12:00:00+00:00")


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_api")
async def test_sensors(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Every sensor reflects the API responses."""
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    def state(entity_id: str):
        st = hass.states.get(entity_id)
        assert st is not None, entity_id
        return st

    plan = state("sensor.ana_example_com_plan")
    assert plan.state == "pro"
    assert plan.attributes["status"] == "active"
    assert (
        state("sensor.ana_example_com_plan_renewal").state
        == "2026-12-01T10:00:00+00:00"
    )

    links = state("sensor.ana_example_com_links")
    assert links.state == "42"
    assert links.attributes["limit"] == 200
    assert state("sensor.ana_example_com_active_links").state == "12"
    assert state("sensor.ana_example_com_visits_30_days").state == "1234"
    assert state("sensor.ana_example_com_visits_today").state == "17"
    assert state("sensor.ana_example_com_daily_unique_visitors").state == "31"
    assert state("sensor.ana_example_com_visits_from_qr").state == "64"
    assert state("sensor.ana_example_com_unread_notifications").state == "3"

    broken = state("sensor.ana_example_com_broken_links")
    assert broken.state == "1"
    assert broken.attributes["links"] == [
        {
            "short": "menu",
            "name": "Carta del bar",
            "url": "https://qr.nauc.link/menu",
            "broken_since": "2026-11-07T08:00:00.000Z",
        }
    ]

    # Pages and cartas exist but start disabled.
    assert hass.states.get("sensor.ana_example_com_pages") is None
    assert hass.states.get("sensor.ana_example_com_menus") is None


async def test_link_health_is_cached(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Links are listed for health at most every 30 minutes, not every poll."""
    await _setup(hass, config_entry)
    assert mock_api.all_shorts.await_count == 1

    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_api.account_overview.await_count == 2
    assert mock_api.all_shorts.await_count == 1


async def test_api_down_retries_setup(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """A network failure leaves the entry retrying, not asking for a login."""
    mock_api.account_overview.side_effect = NaucApiError("boom")
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_rejected_token_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
) -> None:
    """A 401/403 from the API asks the user to log in again."""
    mock_api.account_overview.side_effect = NaucAuthError("401")
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_expired_offline_session_starts_reauth(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Keycloak refusing the refresh token (invalid_grant) asks for a new login."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            "token": {**config_entry.data["token"], "expires_at": time.time() - 10},
        },
    )
    aioclient_mock.post(OAUTH2_TOKEN, status=400, json={"error": "invalid_grant"})

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


@pytest.mark.usefixtures("mock_api")
async def test_unload(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The entry unloads cleanly."""
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
