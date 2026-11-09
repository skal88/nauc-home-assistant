"""Polling coordinator for NAUC.link."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NaucApiClient, NaucApiError, NaucAuthError
from .const import (
    APP_URL,
    DOMAIN,
    LINK_HEALTH_INTERVAL,
    SHORT_BASE_URL,
    UPDATE_INTERVAL,
)
from .repairs import async_sync_broken_link_issues

_LOGGER = logging.getLogger(__name__)

type NaucConfigEntry = ConfigEntry[NaucDataUpdateCoordinator]


@dataclass(frozen=True)
class BrokenDestination:
    """One destination of a link that the health checker found failing."""

    url: str
    status_code: int | None
    error: str | None
    last_checked: str | None

    @property
    def reason(self) -> str | None:
        """Why it fails, as short as possible: the HTTP status or the error."""
        if self.status_code:
            return f"HTTP {self.status_code}"
        return self.error


@dataclass(frozen=True)
class BrokenLink:
    """A link with at least one broken destination."""

    id: str
    short: str
    name: str | None
    url: str
    manage_url: str
    broken_since: str | None
    # Most link types have one destination; programmable links and menus can
    # have several, and only the failing ones are listed.
    destinations: tuple[BrokenDestination, ...]

    @property
    def label(self) -> str:
        """Owner-facing name, falling back to the short code."""
        return self.name or self.short


@dataclass
class NaucData:
    """Everything the sensors read, fetched in one poll."""

    plan: str
    plan_status: str
    current_period_end: datetime | None
    usage: dict[str, dict[str, int]]
    visits_30d: int
    visits_today: int
    daily_uniques_avg: int
    qr_pct: int
    unread_notifications: int
    broken_links: list[BrokenLink] | None = field(default=None)


def _visits_on(series: list[dict[str, Any]], day: str) -> int:
    return next((int(p["visits"]) for p in series if p.get("day") == day), 0)


class NaucDataUpdateCoordinator(DataUpdateCoordinator[NaucData]):
    """Fetch account, analytics, notifications and link health."""

    config_entry: NaucConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: NaucConfigEntry, client: NaucApiClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._broken_links: list[BrokenLink] | None = None
        self._health_fetched_at: datetime | None = None

    async def _async_update_data(self) -> NaucData:
        try:
            account = await self.client.account_overview()
            analytics = await self.client.analytics_overview()
            unread = await self.client.unread_notifications()
            broken = await self._broken_links_cached()
        except NaucAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NaucApiError as err:
            raise UpdateFailed(str(err)) from err

        plan = account.get("plan", {})
        totals = analytics.get("totals", {})
        period_end = plan.get("currentPeriodEnd")
        # The API buckets visits by UTC day.
        today = dt_util.utcnow().strftime("%Y-%m-%d")

        return NaucData(
            plan=plan.get("id", "free"),
            plan_status=plan.get("status", "none"),
            current_period_end=dt_util.parse_datetime(period_end)
            if period_end
            else None,
            usage=account.get("usage", {}),
            visits_30d=int(totals.get("visits", 0)),
            visits_today=_visits_on(analytics.get("series", []), today),
            daily_uniques_avg=int(totals.get("dailyUniquesAvg", 0)),
            qr_pct=int(totals.get("qrPct", 0)),
            unread_notifications=unread,
            broken_links=broken,
        )

    async def _broken_links_cached(self) -> list[BrokenLink] | None:
        now = dt_util.utcnow()
        if (
            self._health_fetched_at is not None
            and now - self._health_fetched_at < LINK_HEALTH_INTERVAL
        ):
            return self._broken_links

        shorts = await self.client.all_shorts()
        by_id = {s["id"]: s for s in shorts if "id" in s}
        summaries = await self.client.link_health(list(by_id))

        broken: list[BrokenLink] = []
        for summary in summaries:
            short = by_id.get(summary.get("shortId", ""))
            if not summary.get("broken") or short is None:
                continue
            # Only broken links get the per-destination detail.
            targets = await self.client.link_health_detail(short["id"])
            code = short.get("short", "")
            broken.append(
                BrokenLink(
                    id=short["id"],
                    short=code,
                    name=short.get("name"),
                    url=f"{SHORT_BASE_URL}/{code}",
                    manage_url=f"{APP_URL}/links/{short['id']}",
                    broken_since=summary.get("brokenSince"),
                    destinations=tuple(
                        BrokenDestination(
                            url=t.get("url", ""),
                            status_code=t.get("statusCode"),
                            error=t.get("error"),
                            last_checked=t.get("lastCheckedAt"),
                        )
                        for t in targets
                        if t.get("status") == "broken"
                    ),
                )
            )

        self._broken_links = broken
        self._health_fetched_at = now
        async_sync_broken_link_issues(self.hass, self.config_entry, broken)
        return self._broken_links
