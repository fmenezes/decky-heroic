import { callable } from "@decky/api";

export interface PluginSettings {
  gogTab: boolean;
  epicTab: boolean;
  amazonTab: boolean;
  sideloadTab: boolean;
  /** Custom Heroic config dir (empty = auto-detect). */
  configPath: string;
}

const getSettings = callable<[], PluginSettings>("get_settings");
const setSetting = callable<[key: string, value: unknown], PluginSettings>(
  "set_setting",
);

const DEFAULTS: PluginSettings = {
  gogTab: true,
  epicTab: true,
  amazonTab: true,
  sideloadTab: true,
  configPath: "",
};

let current: PluginSettings = { ...DEFAULTS };
let loaded = false;
const subscribers = new Set<(settings: PluginSettings) => void>();

/** Load settings from the backend once. Safe to call multiple times. */
export async function initSettings(): Promise<void> {
  if (loaded) return;
  loaded = true;
  try {
    current = { ...DEFAULTS, ...(await getSettings()) };
  } catch {
    // backend unavailable; keep defaults
  }
}

export function getSettingsSync(): PluginSettings {
  return current;
}

export function subscribeSettings(
  fn: (settings: PluginSettings) => void,
): () => void {
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
}

export async function updateSetting<K extends keyof PluginSettings>(
  key: K,
  value: PluginSettings[K],
): Promise<void> {
  current = { ...current, [key]: value };
  try {
    current = { ...DEFAULTS, ...(await setSetting(key, value)) };
  } catch {
    // keep the optimistic value
  }
  subscribers.forEach((fn) => fn(current));
}
