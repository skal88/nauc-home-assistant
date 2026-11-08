# Working conventions

Instructions for Claude Code (and any other AI assistant) working in this repository.
Same rules as the `nauc-shortener` monorepo.

## Attribution: none

Nothing this assistant produces is ever signed, credited or marked as
AI-generated. No `Co-Authored-By` trailer, no "Generated with" line, no note in a
commit body, pull request description, code comment or document saying how the
work was made. The work is the repository owner's and reads as theirs everywhere.

## Language: English

Code, identifiers, file names, comments, tests, commit messages, branch names and
docs are in **English**.

**Exception — user-facing copy.** What Home Assistant shows to the user lives in
`custom_components/nauc_link/translations/`: `es.json` is the primary language of
the product and `en.json` must stay in sync with it (and with `strings.json`, which
mirrors `en.json`). Add a key to all three or none.

## Git workflow

- Rebase, never merge. New work goes on top of the latest `main`.
- Commit freely on feature branches; PRs are squash-merged.
- Angular commit convention: `type(scope): subject` — types `feat`, `fix`, `docs`,
  `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`; scopes such as
  `auth`, `api`, `sensor`, `hacs`. Imperative, lowercase subject, no trailing period.
- Branch names: `feat/link-switch`, `fix/token-refresh`, …

## Architecture

- `custom_components/nauc_link/` — the integration (domain `nauc_link`).
  - `oauth.py` + `config_flow.py` — Keycloak login (authorization code + PKCE) with the
    public client `nauc-home-assistant`, registered in `async_setup` so users never
    need application credentials. The entry's `unique_id` is the token `sub`.
  - `api.py` — the only place that talks to `api.nauc.link`. 401/403 or a refused
    refresh raise `NaucAuthError` (→ reauth); anything else `NaucApiError` (→ retry).
  - `coordinator.py` — one poll every 5 min; link health at most every 30 min.
  - `sensor.py` — entity descriptions; names and units come from translations.
- The Keycloak client is provisioned by `scripts/configure-home-assistant.sh` in the
  `nauc-keycloak` repo. It only grants `shorts:read`: a feature that writes (e.g. a
  switch to enable a link) needs a new scope on that client first, then a reauth for
  existing users.
- Minimum Home Assistant version is 2025.4 (`LocalOAuth2ImplementationWithPkce`).
  Keep `hacs.json` and the README in sync if it changes.

## Checks

```bash
.venv/bin/python -m pytest
uvx ruff check . && uvx ruff format --check .
```
