"""OAuth2 implementation for NAUC.link (Keycloak, authorization code + PKCE)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    LocalOAuth2ImplementationWithPkce,
)

from .const import CLIENT_ID, DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN


class NaucOAuth2Implementation(LocalOAuth2ImplementationWithPkce):
    """Public Keycloak client baked into the integration.

    Users never create application credentials: the client id is public and
    PKCE replaces the client secret.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the implementation."""
        super().__init__(hass, DOMAIN, CLIENT_ID, OAUTH2_AUTHORIZE, OAUTH2_TOKEN)

    @property
    def name(self) -> str:
        """Name shown if Home Assistant ever lists implementations."""
        return "NAUC.link"
