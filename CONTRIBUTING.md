# Contributing

Thanks for hacking on this! Here's the dev setup.

## Stack

- Backend: Python (`main.py` + `py_modules/`, Decky's `decky` API)
- Frontend: React/TypeScript on the official
  [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template)
  stack (`@decky/ui` + `@decky/api` + `@decky/rollup`)

## Setup

Requires Node.js 20+.

```bash
npm install
npm run test        # Python backend unit tests
npm run typecheck   # TypeScript checks
npm run build       # Production frontend build -> dist/
npm run watch       # Dev watch mode
```

## Project layout

```
├── plugin.json               # Decky plugin manifest
├── main.py                   # Decky backend (decky python API)
├── py_modules/
│   ├── heroic_library.py     # Heroic library parser (unit-testable)
│   └── steam_shortcuts.py    # shortcuts.vdf read/write (unit-testable)
├── src/                      # React/TS frontend
│   ├── index.tsx
│   ├── lib/                   # shared callables, settings store
│   ├── patches/               # LibraryPatch.tsx (tab injection)
│   └── components/           # GameLibraryPanel, GameCard, StoreLibraryTab
├── tests/                     # Python unit tests + fixtures
└── .github/workflows/         # ci.yml + publish.yml
```

## Manual install on your own machine

Package the same zip that releases ship, copy it over, and unzip it into the
plugins dir:

```bash
npm run pack
scp decky-heroic.zip user@machinename.local:/tmp/
ssh user@machinename.local "cd ~/homebrew/plugins && sudo rm -rf heroic-library && sudo unzip -o /tmp/decky-heroic.zip && rm /tmp/decky-heroic.zip"
```

Restart the plugin via the Decky menu to pick up changes.

## Releasing (GitHub Actions)

- **CI** (`.github/workflows/ci.yml`): on every push and pull request — runs
  the backend unit tests, typechecks, and builds the frontend
- **Publish** (`.github/workflows/publish.yml`): on every `v*` tag —
  runs tests + build, packages `decky-heroic.zip` in the decky-loader
  plugin distribution layout, and attaches it to a GitHub Release

```bash
git tag v0.1.0
git push origin v0.1.0
```

`workflow_dispatch` runs build + artifact upload without creating a release.
