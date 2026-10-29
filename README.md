# Heroic Library

Your GOG, Epic, Amazon and sideloaded games — right in your Steam library, on
Steam Deck / Bazzite.

This [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin
adds a tab per store to Steam's main library. Open a game from a tab and it
becomes a real Steam shortcut on the spot: its native game page opens, and
from there it's just a normal Steam game — Play button, overlay, controller
config, playtime tracking. Heroic still handles the actual launch underneath,
so cloud saves keep syncing.

Heroic itself gets a Steam shortcut too (with proper box art) — one click in
the plugin settings and it sits in your library like any other game.

## Installing

Grab the latest
[`decky-heroic.zip`](https://github.com/fmenezes/decky-heroic/releases/latest)
and install it via **Decky → Developer → Install plugin from URL/file**, or:

```bash
sudo decky-plugin-cli install https://github.com/fmenezes/decky-heroic/releases/latest/download/decky-heroic.zip
```

You need [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) and
Heroic (flatpak) with your store(s) logged in and library synced once.

## Settings

In the plugin's Quick Access panel you can turn each store's tab on or off,
and open Heroic itself. That's it.

## How it works

No CLIs, no scraping: the plugin reads Heroic's own library cache files,
injects tabs into the library (the trick pioneered by
[TabMaster](https://github.com/Tormak9970/TabMaster)), and registers games as
shortcuts through Steam's runtime API on first click. Launching goes through
Heroic's `heroic://` protocol, so Heroic's install prompt and cloud-save sync
behave exactly as if you launched from Heroic.

## Contributing

Hack away — see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup, tests,
and how releases get built.

## License

MIT
