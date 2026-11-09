# NAUC.link for Home Assistant

Bring your [NAUC.link](https://nauc.link) account into Home Assistant: visits to
your links and QR codes, plan usage, broken links and unread notifications, as
sensors you can chart, put on a dashboard or use in automations.

You log in with your NAUC.link account. There are no API keys to copy and
Home Assistant never sees your password. Access is **read only**: the
integration cannot create, change or delete your links.

## Installation

### HACS (recommended)

1. In HACS, open the menu → **Custom repositories**, add
   `https://github.com/skal88/nauc-home-assistant` with category
   **Integration**.
2. Search for **NAUC.link**, download it and restart Home Assistant.

### Manual

Copy `custom_components/nauc_link` into the `custom_components` folder of your
Home Assistant configuration and restart.

Requires Home Assistant **2025.4** or newer.

## Setup

1. **Settings → Devices & services → Add integration → NAUC.link**.
2. You are sent to the NAUC.link login. Log in and accept the access request
   ("read your links").
3. Back in Home Assistant, the account appears as a device with its sensors.

Add the integration once per NAUC.link account.

> The login comes back through `my.home-assistant.io`, so the
> [My Home Assistant](https://www.home-assistant.io/integrations/my/) integration
> must be enabled. It is, unless you removed `default_config:` from your
> configuration; in that case add `my:`.

## Sensors

| Sensor | State | Attributes |
|---|---|---|
| Plan | `free`, `ong`, `pro` or `business` | `status` (`none`, `active`, `past_due`, `canceled`) |
| Plan renewal | End of the current paid period | |
| Links | Links in the account | `limit` |
| Active links | Enabled links | `limit` |
| Visits (30 days) | Visits in the last 30 days | |
| Visits today | Visits since 00:00 UTC | |
| Daily unique visitors | Average unique visitors per day (30 days) | |
| Visits from QR | Share of visits that came from scanning a QR code (%) | |
| Unread notifications | Unread notifications in NAUC.link | |
| Broken links | Links whose destination is failing | `links` (see below) |
| Pages, Menus | Usage of those plan features (disabled by default) | `limit` |

Data refreshes every 5 minutes; broken links every 30 minutes (NAUC.link
checks destinations at most hourly).

### Broken links

Each entry of the `links` attribute of the **Broken links** sensor says which
link fails and why:

| Key | Example |
|---|---|
| `name` | `Carta del bar` (the short code if the link has no name) |
| `short` / `url` | `menu` / `https://qr.nauc.link/menu` |
| `destination` | `https://bar-ejemplo.es/carta.pdf`, where the link points |
| `reason` | `HTTP 404`, or the network error (`ENOTFOUND`, a TLS error…) |
| `broken_since` / `last_checked` | ISO timestamps |
| `manage_url` | Page of the link in NAUC.link, to fix it |
| `destinations` | Only when several destinations fail (programmable links, menus): `url`, `reason`, `last_checked` of each |

Optionally, each broken link can also show up in **Settings → Repairs**, with
the failing destination and a button to the link in NAUC.link. It is off by
default: turn on **Show broken links in Repairs** under **Configure** on the
integration. The notice disappears by itself once the destination works again,
and turning the option off clears the existing ones.

To list them on a dashboard, use a Markdown card:

```yaml
type: markdown
title: Enlaces rotos
content: >
  {% for l in state_attr('sensor.your_account_broken_links', 'links') or [] %}
  - **[{{ l.name }}]({{ l.manage_url }})** → {{ l.destination }} ({{ l.reason }})
  {% else %}
  Todo funciona.
  {% endfor %}
```

### Example: tell me when a link breaks

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.your_account_broken_links
    above: 0
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "NAUC.link"
      message: >
        {% for l in state_attr('sensor.your_account_broken_links', 'links') %}
        {{ l.name }} → {{ l.destination }} ({{ l.reason }})
        {% endfor %}
```

## Reauthentication

The integration keeps an offline session with NAUC.link and renews it on
every refresh, so it stays connected indefinitely while Home Assistant is
running. If the session is revoked (for example from your NAUC.link account) or
Home Assistant is off for longer than the session idle limit, a **Reconfigure**
notification asks you to log in again.

## Removing

**Settings → Devices & services → NAUC.link → ⋮ → Delete**. To also revoke the
session on NAUC.link's side, open
[your account's applications](https://auth.naucreations.com/realms/naucreations/account/applications)
and remove access for Home Assistant.

## How the login works

Authorization code flow with PKCE against the NAUC.link Keycloak
(`auth.naucreations.com`, realm `naucreations`) using the public client
`nauc-home-assistant`, built into the integration so no application
credentials are needed. The client only has the `shorts-read` scope, so the
access token can only read; `offline_access` is requested so the session is not
bound to the browser login. The Keycloak side is provisioned by
`scripts/configure-home-assistant.sh` in the `nauc-keycloak` repository.

## Development

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv -r requirements_test.txt
.venv/bin/python -m pytest
uvx ruff check . && uvx ruff format --check .
```

To try it against a local NAUC.link stack, start Home Assistant with:

```bash
NAUC_LINK_KEYCLOAK_REALM_URL=http://localhost:8080/realms/nauc-test \
NAUC_LINK_API_URL=http://localhost:3001 hass -c config
```

The dev realm also accepts `http://localhost:8123/auth/external/callback`, for a
local instance without `my`.

### Releasing

1. Bump `version` in `custom_components/nauc_link/manifest.json`.
2. Create a GitHub release tagged `vX.Y.Z`; HACS offers it as an update.

### Brand

`brand/` holds the icon to submit to
[home-assistant/brands](https://github.com/home-assistant/brands) under
`custom_integrations/nauc_link/`. Until it is merged, the HACS validation skips
the brands check.

## License

MIT
