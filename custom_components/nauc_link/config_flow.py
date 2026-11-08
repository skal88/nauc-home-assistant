"""Config flow for NAUC.link: log in with Keycloak."""

from __future__ import annotations

import base64
from collections.abc import Mapping
import json
import logging
from typing import Any

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DOMAIN, SCOPES
from .oauth import NaucOAuth2Implementation


def _token_claims(access_token: str) -> dict[str, Any]:
    """Read the claims of a JWT without verifying it.

    The token comes straight from Keycloak's token endpoint over TLS and is
    only used to name the entry; the API verifies it on every request.
    """
    payload = access_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle the NAUC.link OAuth2 login."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        """Return the logger."""
        return logging.getLogger(__name__)

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Ask for an offline token so the connection outlives the SSO session."""
        return {"scope": " ".join(SCOPES)}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Register the built-in client before picking an implementation.

        Home Assistant does not run the integration's `async_setup` before
        showing the config flow of an integration with no entries, so the
        registration there alone leaves the flow with nothing to pick.
        """
        config_entry_oauth2_flow.async_register_implementation(
            self.hass, DOMAIN, NaucOAuth2Implementation(self.hass)
        )
        return await super().async_step_user(user_input)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start a new login when the stored session stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm before sending the user to log in again."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create (or refresh) the entry for the NAUC.link account that logged in."""
        claims = _token_claims(data["token"]["access_token"])
        await self.async_set_unique_id(claims["sub"])

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=data
            )

        self._abort_if_unique_id_configured()
        title = claims.get("email") or claims.get("preferred_username") or "NAUC.link"
        return self.async_create_entry(title=title, data=data)
