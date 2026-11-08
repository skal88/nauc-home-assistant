"""Tests for the NAUC.link config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.nauc_link.const import (
    CLIENT_ID,
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

from .conftest import ACCESS_TOKEN, EMAIL, SUB, make_jwt

REDIRECT_URI = "https://example.com/auth/external/callback"


async def _start_login(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    flow_id: str,
    url: str,
) -> None:
    """Check the authorize URL and come back through the OAuth callback."""
    query = parse_qs(urlparse(url).query)
    assert url.startswith(OAUTH2_AUTHORIZE)
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["scope"] == ["openid offline_access"]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_challenge" in query

    client = await hass_client_no_auth()
    resp = await client.get(
        f"/auth/external/callback?code=abcd&state={query['state'][0]}"
    )
    assert resp.status == 200


def _mock_token(aioclient_mock: AiohttpClientMocker, access_token: str) -> None:
    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "access_token": access_token,
            "refresh_token": "offline-refresh-token",
            "token_type": "Bearer",
            "expires_in": 300,
            "refresh_expires_in": 0,
        },
    )


@pytest.fixture(autouse=True)
async def setup_auth(hass: HomeAssistant) -> None:
    """Set up what a real instance already has: the OAuth callback view lives in `auth`.

    The integration itself is deliberately not set up: Home Assistant does not
    run `async_setup` before showing the config flow of an integration that
    has no entries yet, so the flow must work without it.
    """
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "auth", {})


@pytest.mark.usefixtures("current_request_with_host")
async def test_full_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    mock_api: AsyncMock,
) -> None:
    """Logging in creates an entry named after the account and keyed by `sub`."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    await _start_login(hass, hass_client_no_auth, result["flow_id"], result["url"])
    _mock_token(aioclient_mock, ACCESS_TOKEN)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == EMAIL
    assert result["result"].unique_id == SUB
    assert result["data"]["token"]["refresh_token"] == "offline-refresh-token"
    # PKCE: the code verifier travels with the token request.
    token_request = aioclient_mock.mock_calls[-1][2]
    assert token_request["client_id"] == CLIENT_ID
    assert "code_verifier" in token_request
    assert "client_secret" not in token_request


@pytest.mark.usefixtures("current_request_with_host")
async def test_already_configured(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """The same NAUC.link account cannot be added twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await _start_login(hass, hass_client_no_auth, result["flow_id"], result["url"])
    _mock_token(aioclient_mock, ACCESS_TOKEN)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("current_request_with_host")
async def test_reauth(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    mock_api: AsyncMock,
) -> None:
    """Reauth stores the new token on the existing entry."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await _start_login(hass, hass_client_no_auth, result["flow_id"], result["url"])
    new_token = make_jwt({"sub": SUB, "email": EMAIL, "jti": "new"})
    _mock_token(aioclient_mock, new_token)

    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["token"]["access_token"] == new_token


@pytest.mark.usefixtures("current_request_with_host")
async def test_reauth_wrong_account(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Reauth with another account is refused and keeps the old token."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await _start_login(hass, hass_client_no_auth, result["flow_id"], result["url"])
    _mock_token(aioclient_mock, make_jwt({"sub": "someone-else"}))

    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert config_entry.data["token"]["access_token"] == ACCESS_TOKEN


async def test_implementation_is_registered_by_the_flow(hass: HomeAssistant) -> None:
    """Users never need application credentials: the flow brings the client."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is not FlowResultType.ABORT, result.get("reason")

    implementations = await config_entry_oauth2_flow.async_get_implementations(
        hass, DOMAIN
    )
    assert list(implementations) == [DOMAIN]
    assert implementations[DOMAIN].name == "NAUC.link"
