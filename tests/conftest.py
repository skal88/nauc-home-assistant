"""Shared fixtures for the NAUC.link tests."""

from __future__ import annotations

import base64
from collections.abc import Generator
import json
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, load_fixture

from custom_components.nauc_link.const import DOMAIN

SUB = "6f1c2b0e-4d4a-4c55-9a83-0c6b2a1f9e10"
EMAIL = "ana@example.com"


def make_jwt(claims: dict[str, Any]) -> str:
    """Build an unsigned JWT; the integration only reads its claims."""

    def part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none'})}.{part(claims)}.signature"


ACCESS_TOKEN = make_jwt({"sub": SUB, "email": EMAIL, "preferred_username": "ana"})


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


def json_fixture(name: str) -> Any:
    """Load a JSON fixture from tests/fixtures."""
    return json.loads(load_fixture(name))


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry with a valid, unexpired token."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=SUB,
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": ACCESS_TOKEN,
                "refresh_token": "offline-refresh-token",
                "token_type": "Bearer",
                "expires_in": 300,
                "expires_at": time.time() + 300,
            },
        },
    )


@pytest.fixture
def mock_api() -> Generator[AsyncMock]:
    """Patch the API client with responses shaped like the real API."""
    with patch(
        "custom_components.nauc_link.NaucApiClient", autospec=True
    ) as client_cls:
        client = client_cls.return_value
        client.account_overview.return_value = json_fixture("account_overview.json")
        client.analytics_overview.return_value = json_fixture("analytics_overview.json")
        client.unread_notifications.return_value = 3
        client.all_shorts.return_value = json_fixture("shorts.json")["shorts"]
        client.link_health.return_value = json_fixture("link_health.json")["summaries"]
        client.link_health_detail.return_value = json_fixture(
            "link_health_detail.json"
        )["targets"]
        yield client
