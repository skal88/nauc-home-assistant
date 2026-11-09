"""The NAUC.link integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow, config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import NaucApiClient
from .const import API_URL, DOMAIN
from .coordinator import NaucConfigEntry, NaucDataUpdateCoordinator
from .oauth import NaucOAuth2Implementation
from .repairs import async_delete_broken_link_issues

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the built-in OAuth2 implementation."""
    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN, NaucOAuth2Implementation(hass)
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NaucConfigEntry) -> bool:
    """Set up NAUC.link from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    # A refused refresh surfaces from the client as NaucAuthError, which the
    # coordinator turns into a reauth flow.
    async def get_access_token() -> str:
        await session.async_ensure_token_valid()
        return session.token["access_token"]

    client = NaucApiClient(async_get_clientsession(hass), API_URL, get_access_token)
    coordinator = NaucDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: NaucConfigEntry) -> None:
    """Reload so the new options apply on a fresh link-health fetch."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NaucConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: NaucConfigEntry) -> None:
    """Clear the broken-link issues of a removed account."""
    async_delete_broken_link_issues(hass, entry)
