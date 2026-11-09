"""Sensors for NAUC.link."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import APP_URL, DOMAIN, PLANS
from .coordinator import (
    BrokenLink,
    NaucConfigEntry,
    NaucData,
    NaucDataUpdateCoordinator,
)

# Coordinator-driven: no per-entity requests to throttle.
PARALLEL_UPDATES = 0

type StateValue = str | int | datetime | None


@dataclass(frozen=True, kw_only=True)
class NaucSensorEntityDescription(SensorEntityDescription):
    """Describes a NAUC.link sensor."""

    value_fn: Callable[[NaucData], StateValue]
    attributes_fn: Callable[[NaucData], dict[str, Any]] | None = None


def _used(key: str) -> Callable[[NaucData], int | None]:
    def value(data: NaucData) -> int | None:
        meter = data.usage.get(key)
        return meter["used"] if meter else None

    return value


def _limit(key: str) -> Callable[[NaucData], dict[str, Any]]:
    def attributes(data: NaucData) -> dict[str, Any]:
        meter = data.usage.get(key)
        return {"limit": meter["limit"]} if meter else {}

    return attributes


def _broken_link_attributes(link: BrokenLink) -> dict[str, Any]:
    """Flat enough to template with: the first failing destination up front."""
    first = link.destinations[0] if link.destinations else None
    attributes: dict[str, Any] = {
        "name": link.label,
        "short": link.short,
        "url": link.url,
        "destination": first.url if first else None,
        "reason": first.reason if first else None,
        "broken_since": link.broken_since,
        "last_checked": first.last_checked if first else None,
        "manage_url": link.manage_url,
    }
    if len(link.destinations) > 1:
        attributes["destinations"] = [
            {"url": d.url, "reason": d.reason, "last_checked": d.last_checked}
            for d in link.destinations
        ]
    return attributes


def _usage_sensor(
    key: str, translation_key: str, *, enabled_default: bool = True
) -> NaucSensorEntityDescription:
    return NaucSensorEntityDescription(
        key=translation_key,
        translation_key=translation_key,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled_default,
        value_fn=_used(key),
        attributes_fn=_limit(key),
    )


SENSORS: tuple[NaucSensorEntityDescription, ...] = (
    NaucSensorEntityDescription(
        key="plan",
        translation_key="plan",
        device_class=SensorDeviceClass.ENUM,
        options=PLANS,
        value_fn=lambda data: data.plan if data.plan in PLANS else None,
        attributes_fn=lambda data: {"status": data.plan_status},
    ),
    NaucSensorEntityDescription(
        key="plan_period_end",
        translation_key="plan_period_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.current_period_end,
    ),
    _usage_sensor("total", "links_total"),
    _usage_sensor("active", "links_active"),
    _usage_sensor("pages", "pages", enabled_default=False),
    _usage_sensor("cartas", "cartas", enabled_default=False),
    NaucSensorEntityDescription(
        key="visits_30d",
        translation_key="visits_30d",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.visits_30d,
    ),
    NaucSensorEntityDescription(
        # Resets at midnight UTC, which TOTAL_INCREASING records as a new cycle.
        key="visits_today",
        translation_key="visits_today",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.visits_today,
    ),
    NaucSensorEntityDescription(
        key="daily_unique_visitors",
        translation_key="daily_unique_visitors",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.daily_uniques_avg,
    ),
    NaucSensorEntityDescription(
        key="qr_share",
        translation_key="qr_share",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.qr_pct,
    ),
    NaucSensorEntityDescription(
        key="unread_notifications",
        translation_key="unread_notifications",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.unread_notifications,
    ),
    NaucSensorEntityDescription(
        key="broken_links",
        translation_key="broken_links",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            len(data.broken_links) if data.broken_links is not None else None
        ),
        attributes_fn=lambda data: {
            "links": [_broken_link_attributes(link) for link in data.broken_links or []]
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NaucConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NAUC.link sensors."""
    coordinator = entry.runtime_data
    async_add_entities(NaucSensor(coordinator, description) for description in SENSORS)


class NaucSensor(CoordinatorEntity[NaucDataUpdateCoordinator], SensorEntity):
    """A NAUC.link account sensor."""

    _attr_has_entity_name = True
    entity_description: NaucSensorEntityDescription

    def __init__(
        self,
        coordinator: NaucDataUpdateCoordinator,
        description: NaucSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        account_id = coordinator.config_entry.unique_id
        self._attr_unique_id = f"{account_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(account_id))},
            name=coordinator.config_entry.title,
            manufacturer="Nau Creations",
            model="NAUC.link",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=APP_URL,
        )

    @property
    def native_value(self) -> StateValue:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
