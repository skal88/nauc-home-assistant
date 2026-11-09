"""Constants for the NAUC.link integration."""

from __future__ import annotations

from datetime import timedelta
import os
from typing import Final

DOMAIN: Final = "nauc_link"

# Public OAuth client (authorization code + PKCE). The id is not a secret: it
# ships with the integration, and Keycloak only accepts the my.home-assistant.io
# redirect for it.
CLIENT_ID: Final = "nauc-home-assistant"

# Overridable through the environment only to point a local Home Assistant at
# a development stack; real installs always use the production endpoints.
KEYCLOAK_REALM_URL: Final = os.environ.get(
    "NAUC_LINK_KEYCLOAK_REALM_URL",
    "https://auth.naucreations.com/realms/naucreations",
)
API_URL: Final = os.environ.get("NAUC_LINK_API_URL", "https://api.nauc.link")

OAUTH2_AUTHORIZE: Final = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/auth"
OAUTH2_TOKEN: Final = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/token"

# `offline_access` makes Keycloak issue an offline refresh token, which is not
# bound to the browser SSO session and so survives the realm's 30-day SSO max.
SCOPES: Final = ["openid", "offline_access"]

APP_URL: Final = "https://app.nauc.link"
SHORT_BASE_URL: Final = "https://qr.nauc.link"

UPDATE_INTERVAL: Final = timedelta(minutes=5)
# Links are checked at most hourly server side, so listing every link to read
# its health on each poll would only add load.
LINK_HEALTH_INTERVAL: Final = timedelta(minutes=30)

PLANS: Final = ["free", "ong", "pro", "business"]

# Option: raise a repair issue per broken link. Off by default, since the
# Broken links sensor already carries them and Repairs is meant for things
# that need the Home Assistant owner's attention.
CONF_BROKEN_LINK_REPAIRS: Final = "broken_link_repairs"
DEFAULT_BROKEN_LINK_REPAIRS: Final = False
