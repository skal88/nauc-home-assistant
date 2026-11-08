"""Tests for the NAUC.link API client."""

from __future__ import annotations

from aiohttp import ClientResponseError, ClientSession, RequestInfo
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from multidict import CIMultiDict, CIMultiDictProxy
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from yarl import URL

from custom_components.nauc_link.api import NaucApiClient, NaucApiError, NaucAuthError

BASE = "https://api.test"


def _client(session: ClientSession, token: str = "tok") -> NaucApiClient:
    async def get_token() -> str:
        return token

    return NaucApiClient(session, BASE, get_token)


async def test_sends_bearer(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Every request carries the access token."""
    aioclient_mock.get(f"{BASE}/notifications/unread-count", json={"unreadCount": 5})

    assert await _client(async_get_clientsession(hass)).unread_notifications() == 5
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Bearer tok"


async def test_pages_through_shorts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """`all_shorts` follows the pagination until `total` is reached."""
    first = [{"id": str(i)} for i in range(100)]
    aioclient_mock.get(
        f"{BASE}/shorts?page=0&limit=100", json={"total": 101, "shorts": first}
    )
    aioclient_mock.get(
        f"{BASE}/shorts?page=1&limit=100", json={"total": 101, "shorts": [{"id": "x"}]}
    )

    shorts = await _client(async_get_clientsession(hass)).all_shorts()

    assert len(shorts) == 101


async def test_link_health_batches_ids(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Ids are sent in batches of 100 to keep URLs short."""
    aioclient_mock.get(f"{BASE}/link-health/summary", json={"summaries": [{}]})

    result = await _client(async_get_clientsession(hass)).link_health(
        [str(i) for i in range(150)]
    )

    assert aioclient_mock.call_count == 2
    assert len(result) == 2


async def test_link_health_with_no_links(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """No links means no request at all."""
    assert await _client(async_get_clientsession(hass)).link_health([]) == []
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, NaucAuthError), (403, NaucAuthError), (500, NaucApiError)],
)
async def test_error_status(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    error: type[Exception],
) -> None:
    """401/403 mean the login is gone; anything else is a transient API error."""
    aioclient_mock.get(f"{BASE}/account/overview", status=status)

    with pytest.raises(error):
        await _client(async_get_clientsession(hass)).account_overview()


async def test_refresh_rejected_is_auth_error(hass: HomeAssistant) -> None:
    """Keycloak refusing the refresh token surfaces as an auth error."""

    async def get_token() -> str:
        raise ClientResponseError(
            RequestInfo(URL(BASE), "POST", CIMultiDictProxy(CIMultiDict())),
            (),
            status=400,
        )

    client = NaucApiClient(async_get_clientsession(hass), BASE, get_token)
    with pytest.raises(NaucAuthError):
        await client.account_overview()
