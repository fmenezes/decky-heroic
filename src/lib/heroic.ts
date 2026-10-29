import { callable } from "@decky/api";
import { Navigation } from "@decky/ui";
import type { GameEntry, LibraryResult, Store, StoresStatus } from "../types";

export type { GameEntry, LibraryResult, Store, StoresStatus };

export const getLibrary = callable<[], LibraryResult>("get_library");

export interface HeroicStatus {
  /** False once the backend has confirmed Heroic is not installed or configured. Starts
   * optimistic (true) so tabs are not needlessly withheld at load. */
  found: boolean;
  /** Whether Heroic flatpak or native binary is installed on the system. */
  installed: boolean;
  /** Whether flatpak is available on this system. */
  hasFlatpak: boolean;
  /** Stores login status (true if configured/logged in). */
  stores: StoresStatus;
  /** Config paths probed during detection. */
  probed: string[];
  /** True until the first backend check has completed. */
  checked: boolean;
}

let heroicStatus: HeroicStatus = {
  found: false,
  installed: false,
  hasFlatpak: false,
  stores: {
    gog: false,
    epic: false,
    amazon: false,
    sideload: false,
  },
  probed: [],
  checked: false,
};
const statusSubs = new Set<() => void>();

export function getHeroicStatus(): HeroicStatus {
  return heroicStatus;
}

export function subscribeHeroicStatus(fn: () => void): () => void {
  statusSubs.add(fn);
  return () => {
    statusSubs.delete(fn);
  };
}

function setHeroicStatus(next: HeroicStatus): void {
  heroicStatus = next;
  statusSubs.forEach((fn) => fn());
}

const checkHeroic = callable<
  [],
  {
    found: boolean;
    installed?: boolean;
    has_flatpak?: boolean;
    stores?: Partial<StoresStatus>;
    probed?: string[];
  }
>("check_heroic");

export interface InstallProgress {
  status: "idle" | "running" | "success" | "error";
  logs: string[];
  error?: string | null;
}

export const startInstallHeroic = callable<[], InstallProgress>(
  "start_install_heroic",
);

export const getInstallProgress = callable<[], InstallProgress>(
  "get_install_progress",
);

export const installHeroic = callable<
  [],
  { success: boolean; error?: string }
>("install_heroic");

/** Re-run Heroic detection and notify subscribers. Never throws. */
export async function refreshHeroicStatus(): Promise<void> {
  try {
    const res = await checkHeroic();
    setHeroicStatus({
      found: Boolean(res.found),
      installed: res.installed !== undefined ? Boolean(res.installed) : Boolean(res.found),
      hasFlatpak: Boolean(res.has_flatpak),
      stores: {
        gog: Boolean(res.stores?.gog),
        epic: Boolean(res.stores?.epic),
        amazon: Boolean(res.stores?.amazon),
        sideload: Boolean(res.stores?.sideload),
      },
      probed: res.probed ?? [],
      checked: true,
    });
  } catch (e) {
    console.error("heroic check failed", e);
  }
}
export const launchGame = callable<
  [app_name: string, runner: string],
  { url: string }
>("launch_game");

export const addShortcut = callable<
  [store: string, app_name: string, steam_appid: number | null],
  { appid: number; added: number; removed: number }
>("add_shortcut");

const LAUNCHER_NAME = "Heroic Games Launcher";
let launcherId: number | undefined;

const getLauncherArt = callable<
  [],
  {
    grid_b64?: string;
    hero_b64?: string;
    logo_b64?: string;
    wide_b64?: string;
    icon_path?: string;
  }
>("get_launcher_art");

/**
 * Open Heroic's native Steam page — registering a launcher shortcut if
 * needed — so the gamepad can start/stop it like any game, and Steam manages
 * focus in Game Mode. (No lock handling: navigation is all we do; a running
 * Heroic keeps its window and second launches are no-ops by design.)
 */
export async function openHeroicLauncher(): Promise<void> {
  const appStore = (window as any).appStore;
  const sc = (window as any).SteamClient.Apps;
  const alive = (id: number | undefined) => {
    if (!id) return false;
    try {
      return Boolean(appStore?.GetAppOverviewByAppID?.(id));
    } catch {
      return false;
    }
  };
  let id = alive(launcherId) ? launcherId : undefined;
  if (!id) {
    const byName = (appStore?.allApps ?? []).find(
      (a: any) => a.display_name === LAUNCHER_NAME && a.app_type === 0x40000000,
    );
    id = byName?.appid;
  }
  if (!id) {
    id = await sc.AddShortcut(
      LAUNCHER_NAME,
      "/usr/bin/flatpak",
      "/usr/bin",
      "run com.heroicgameslauncher.hgl",
    );
    sc.SetShortcutName(id, LAUNCHER_NAME);
    sc.SetShortcutLaunchOptions(id, "run com.heroicgameslauncher.hgl");
    launcherId = id;
    // apply the bundled artwork (hero/logo/grid/wide + icon)
    try {
      const art = await getLauncherArt();
      if (art.grid_b64) await sc.SetCustomArtworkForApp(id, art.grid_b64, "png", 0);
      if (art.hero_b64) await sc.SetCustomArtworkForApp(id, art.hero_b64, "png", 1);
      if (art.logo_b64) await sc.SetCustomArtworkForApp(id, art.logo_b64, "png", 2);
      if (art.wide_b64) await sc.SetCustomArtworkForApp(id, art.wide_b64, "png", 3);
      if (art.icon_path) sc.SetShortcutIcon(id, art.icon_path);
    } catch (e) {
      console.error("launcher artwork failed", e);
    }
  }
  Navigation.Navigate(`/library/app/${id}`);
  // close the Quick Access menu so the navigated page is actually visible
  Navigation.CloseSideMenus();
}

export const getGameArt = callable<
  [store: string, app_name: string, steam_appid: number],
  {
    square_b64?: string;
    square_type?: "jpg" | "png";
    cover_b64?: string;
    cover_type?: "jpg" | "png";
  }
>("get_game_art");

// session cache: "store:app_name" -> steam shortcut appid
const runtimeShortcutIds = new Map<string, number>();

/**
 * Make Steam (running client) know the game as a non-Steam shortcut and
 * return its app id — no Steam restart needed:
 *  1. session cache hit
 *  2. a vdf-synced shortcut whose id the running client already knows
 *  3. runtime AddShortcut (+ explicit SetShortcutName — Steam otherwise
 *     derives the name from the executable)
 * The click calling this IS the user's explicit consent to write the link.
 */
export async function ensureSteamShortcut(game: GameEntry): Promise<number> {
  const key = `${game.store}:${game.app_name}`;
  const appStore = (window as any).appStore;
  const known = (id: number | undefined) => {
    if (!id) return undefined;
    try {
      return appStore?.GetAppOverviewByAppID?.(id) ? id : undefined;
    } catch {
      return undefined;
    }
  };

  const cached = runtimeShortcutIds.get(key);
  if (cached && known(cached)) return cached;

  const tagged = known(game.steam_appid);
  if (tagged) {
    runtimeShortcutIds.set(key, tagged);
    return tagged;
  }

  // After a Steam restart the client recomputes shortcut ids on load; if the
  // vdf-tagged id no longer resolves, find the loaded shortcut by name so we
  // don't create a duplicate.
  const byName = ((window as any).appStore?.allApps ?? []).find(
    (a: any) => a.display_name === game.title && a.app_type === 0x40000000,
  );
  if (byName?.appid) {
    runtimeShortcutIds.set(key, byName.appid);
    return byName.appid;
  }

  const sc = (window as any).SteamClient.Apps;
  const url = launchUrlFor(game);
  const id: number = await sc.AddShortcut(
    game.title,
    "/usr/bin/flatpak",
    "/usr/bin",
    `run com.heroicgameslauncher.hgl "${url}"`,
  );
  sc.SetShortcutName(id, game.title);
  sc.SetShortcutLaunchOptions(id, `run com.heroicgameslauncher.hgl "${url}"`);
  // wait for the UI store to register the new app — first-time navigation
  // otherwise races Steam and lands on a broken page (later ones are fine)
  for (let i = 0; i < 30; i++) {
    if (known(id)) break;
    await new Promise((r) => setTimeout(r, 100));
  }
  // artwork: portrait grid + hero banner (base64 from the backend; also
  // written into Steam's grid dir for the file-based path)
  try {
    const art = await getGameArt(game.store, game.app_name, id);
    if (art.square_b64 && art.square_type)
      await sc.SetCustomArtworkForApp(id, art.square_b64, art.square_type, 0);
    if (art.cover_b64 && art.cover_type)
      await sc.SetCustomArtworkForApp(id, art.cover_b64, art.cover_type, 1);
  } catch (e) {
    console.error("artwork fetch failed", e);
  }
  // persist to shortcuts.vdf with Steam's own id so it survives restarts
  void addShortcut(game.store, game.app_name, id).catch((e) =>
    console.error("vdf persist failed", e),
  );
  runtimeShortcutIds.set(key, id);
  return id;
}

function launchUrlFor(game: GameEntry): string {
  const runner =
    { gog: "gog", epic: "legendary", amazon: "nile", sideload: "sideload" }[
      game.store
    ] ?? game.runner;
  return `heroic://launch?appName=${encodeURIComponent(
    game.app_name,
  )}&runner=${encodeURIComponent(runner)}`;
}

/**
 * Direct launch: register the shortcut if needed, then run it through Steam
 * (native focus/overlay/tracking). Falls back to Heroic's protocol launch.
 */
export async function playGame(game: GameEntry): Promise<void> {
  try {
    const appid = await ensureSteamShortcut(game);
    (window as any).SteamClient.Apps.RunGame(String(appid), "", -1, 200);
    return;
  } catch {
    // fall through to the protocol launch
  }
  await launchGame(game.app_name, game.runner);
}

interface StoreCount {
  total: number;
  installed: number;
}

const storeCounts: Record<string, StoreCount> = {};
const countSubs = new Set<() => void>();

/** Update the per-store game counts (used for library tab counters). */
export function updateStoreCounts(games: GameEntry[]): void {
  const counts: Record<string, StoreCount> = {};
  const bump = (key: string, installed: boolean) => {
    const c = (counts[key] ??= { total: 0, installed: 0 });
    c.total += 1;
    if (installed) c.installed += 1;
  };
  for (const g of games) bump(g.store, g.is_installed);
  // aggregate entry used by the cross-store "Heroic Installed" tab
  counts["all"] = {
    total: games.length,
    installed: games.filter((g) => g.is_installed).length,
  };
  for (const key of Object.keys(storeCounts)) delete storeCounts[key];
  Object.assign(storeCounts, counts);
  countSubs.forEach((fn) => fn());
}

export function getStoreCount(
  store: Store | "all",
  installedOnly = false,
): number {
  const c = storeCounts[store];
  if (!c) return 0;
  return installedOnly ? c.installed : c.total;
}

export function subscribeStoreCounts(fn: () => void): () => void {
  countSubs.add(fn);
  return () => {
    countSubs.delete(fn);
  };
}

/** Fetch the library once at startup to prime tab counters, the
 * shortcut id cache (games previously synced to Steam get their ids back
 * without re-adding anything), and the Heroic-installed status. */
export async function primeLibrary(): Promise<void> {
  try {
    const res = await getLibrary();
    if (res.installed !== undefined || res.heroic_found !== undefined) {
      setHeroicStatus({
        found: Boolean(res.heroic_found),
        installed: Boolean(res.installed),
        hasFlatpak: heroicStatus.hasFlatpak,
        stores: {
          gog: Boolean(res.stores?.gog),
          epic: Boolean(res.stores?.epic),
          amazon: Boolean(res.stores?.amazon),
          sideload: Boolean(res.stores?.sideload),
        },
        probed: res.probed ?? [],
        checked: true,
      });
      void refreshHeroicStatus();
    } else {
      void refreshHeroicStatus();
    }
    updateStoreCounts(res.games ?? []);
    for (const g of res.games ?? []) {
      if (g.steam_appid) {
        runtimeShortcutIds.set(`${g.store}:${g.app_name}`, g.steam_appid);
      }
    }
  } catch {
    // backend unavailable; counters stay zero
  }
}
