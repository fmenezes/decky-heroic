# Heroic Library Decky Plugin — Design

Date: 2026-10-27
Status: Approved

## Purpose

A Decky Loader plugin that surfaces the Heroic Games Launcher library (GOG + Epic) as a
Quick Access panel on SteamOS/Bazzite, showing installed status and launching games
without leaving Game Mode.

## Architecture

Standard Decky plugin following the official decky-plugin-template stack
(`@decky/ui` + `@decky/api` + `@decky/rollup`, React provided by Steam's CEF)
plus a Python backend (`main.py`, using the `decky` python API).

- `src/index.tsx` — plugin entry; registers the Quick Access panel.
- `src/components/GameLibraryPanel.tsx` — search box, "Installed only" toggle,
  error banners, refresh, game list.
- `src/components/GameRow.tsx` — one game: cover art, title, badges (store,
  cloud saves, install size), Play button.
- `main.py` — backend entry (Decky lifecycle class `Plugin`).
- `py_modules/heroic_library.py` — pure-Python library parser, importable/testable without
  Decky.

## Data source (validated against the real machine)

Heroic flatpak config dir: `~/.var/app/com.heroicgameslauncher.hgl/config/heroic`

- `store_cache/gog_library.json` → `.games[]`
- `store_cache/legendary_library.json` → `.library[]`

Each entry already carries everything we need (no CLI calls, no cross-referencing
of `installed.json`):

| field            | use                        |
|------------------|----------------------------|
| `title`          | display name               |
| `app_name`       | launch id                  |
| `runner`         | gog / legendary            |
| `is_installed`   | installed badge, Play gate |
| `art_square`     | cover art (remote CDN URL) |
| `art_cover`      | wide art (unused in v1)    |
| `install.install_size` | size badge          |
| `cloud_save_enabled` | cloud-save badge       |

The `gog-redist` entry (Galaxy redistributables) is filtered out.

## Launching

`xdg-open` on Heroic's registered deep links (handler confirmed present on the
target machine via `xdg-settings`):

- Epic: `heroic://launch/<app_name>`
- GOG: `heroic://gogLaunch/<app_name>`

Launching through Heroic (not raw `legendary`/`gogdl`) preserves Heroic's pre/post
game hooks, including cloud-save sync. Fallback: `flatpak run
com.heroicgameslauncher.hgl <url>` if `xdg-open` fails immediately.

## Backend API

- `get_library()` → `{ games: GameEntry[], errors: string[] }` where `GameEntry =
  {title, app_name, store, runner, is_installed, art_square, art_cover,
  install_size, cloud_saves}`. Games sorted installed-first, then alphabetical.
  Missing/corrupt JSON per store yields a partial list plus an error string.
- `launch_game(store, app_name)` → `{ url }` on success, raises on immediate
  launch failure.

## Error handling

- Heroic not installed / flatpak config missing → empty list + error surfaced as
  a panel message.
- Corrupt JSON → parse the other store, report error.
- Launch failure → backend logs via `decky_plugin.logger`, frontend shows a toast.

## Testing

- Python: stdlib `unittest` tests for `heroic_library.py` against fixture JSONs
  sampled from the real files.
- End-to-end: build locally, `rsync` to the Bazzite machine into
  `~/homebrew/plugins/heroic-library/`, verify in Game Mode.

## Publishing

GitHub Actions workflow (`.github/workflows/publish.yml`): on `v*` tag —
`npm ci`, `npm run build`, zip `{plugin.json, plugin.py, heroic_library.py,
dist/}` as `heroic-library.zip`, create a GitHub Release with the zip attached.
Manual `workflow_dispatch` builds and uploads the artifact without releasing.

## Out of scope (v1)

- Install/uninstall actions
- Amazon (nile) and sideloaded games (empty on this machine; parser structure
  allows adding stores later)
- Steam shortcut syncing (native cards)

## Addendum (post-v1, implemented)

- **Per-store library tabs**: GOG and Epic each get a tab in the main Steam
  library tab bar (content: our own React grid with cover tiles; click to
  launch). Injection via a `/library` route patch that splices custom tabs
  into the library's tab memo — approach adapted from TabMaster
  (Tormak9970/TabMaster), including the memo cache + rerender handler so
  tab changes apply without restarting Steam.
- **Settings screen** (gear → in the QAM panel): `gogTab` / `epicTab`
  toggles controlling which store tabs appear; persisted by the backend as
  JSON in the Decky plugin settings dir.
- **Defensive Heroic discovery**: probe order = custom path
  (`configPath` setting or `HEROIC_CONFIG_DIR` env) → flatpak config dir →
  native `~/.config/heroic`; a candidate counts only if it has
  `store_cache/`. When nothing is found, `get_library` returns an empty
  list plus an error listing every probed path.
