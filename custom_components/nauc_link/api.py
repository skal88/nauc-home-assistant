"""Minimal client for the NAUC.link REST API (shorts-manager)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

# The API accepts 10, 50 or 100 per page.
PAGE_SIZE = 100
# Link-health ids travel in the query string; keep each URL well under limits.
HEALTH_BATCH = 100

REQUEST_TIMEOUT = ClientTimeout(total=30)


class NaucApiError(Exception):
    """The API could not be reached or answered with an error."""


class NaucAuthError(NaucApiError):
    """The token was rejected or could not be refreshed: the user must log in again."""


class NaucApiClient:
    """Read-only access to the endpoints the integration shows in Home Assistant."""

    def __init__(
        self,
        websession: ClientSession,
        base_url: str,
        get_access_token: Callable[[], Awaitable[str]],
    ) -> None:
        """Initialize the client."""
        self._websession = websession
        self._base_url = base_url.rstrip("/")
        self._get_access_token = get_access_token

    async def _access_token(self) -> str:
        try:
            return await self._get_access_token()
        except ClientResponseError as err:
            # Keycloak answers 400 invalid_grant once the offline session is gone.
            if 400 <= err.status < 500:
                raise NaucAuthError("Refreshing the access token was rejected") from err
            raise NaucApiError(f"Keycloak error {err.status}") from err
        except (ClientError, TimeoutError) as err:
            raise NaucApiError(f"Cannot reach Keycloak: {err}") from err

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        token = await self._access_token()
        try:
            async with self._websession.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise NaucAuthError(f"{path} answered {resp.status}")
                if resp.status >= 400:
                    raise NaucApiError(f"{path} answered {resp.status}")
                return await resp.json()
        except (ClientError, TimeoutError) as err:
            raise NaucApiError(f"Cannot reach {path}: {err}") from err

    async def account_overview(self) -> dict[str, Any]:
        """Plan and usage meters: `{plan: {...}, usage: {key: {used, limit}}}`."""
        return await self._get("/account/overview")

    async def analytics_overview(self) -> dict[str, Any]:
        """Account-wide visits for the last 30 days, with a UTC daily series."""
        return await self._get("/analytics/overview")

    async def unread_notifications(self) -> int:
        """Number of unread notifications in the NAUC.link inbox."""
        data = await self._get("/notifications/unread-count")
        return int(data["unreadCount"])

    async def all_shorts(self) -> list[dict[str, Any]]:
        """Every link of the account, following the pagination."""
        shorts: list[dict[str, Any]] = []
        page = 0
        while True:
            data = await self._get("/shorts", {"page": page, "limit": PAGE_SIZE})
            batch = data.get("shorts", [])
            shorts.extend(batch)
            if not batch or len(shorts) >= int(data.get("total", 0)):
                return shorts
            page += 1

    async def link_health(self, short_ids: list[str]) -> list[dict[str, Any]]:
        """Health summary for the given links (`status`, `broken`, `brokenSince`)."""
        summaries: list[dict[str, Any]] = []
        for start in range(0, len(short_ids), HEALTH_BATCH):
            ids = short_ids[start : start + HEALTH_BATCH]
            data = await self._get("/link-health/summary", {"shortIds": ",".join(ids)})
            summaries.extend(data.get("summaries", []))
        return summaries
