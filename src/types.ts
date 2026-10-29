export type Store = "gog" | "epic" | "amazon" | "sideload";

export interface StoresStatus {
  gog: boolean;
  epic: boolean;
  amazon: boolean;
  sideload: boolean;
}

export interface GameEntry {
  title: string;
  app_name: string;
  store: Store;
  runner: string;
  is_installed: boolean;
  art_square: string;
  art_cover: string;
  install_size: string;
  cloud_saves: boolean;
  /** Steam shortcut app id when the game has been synced to Steam. */
  steam_appid?: number;
}

export interface LibraryResult {
  games: GameEntry[];
  errors: string[];
  /** Heroic config dir that was used (absent when Heroic was not found). */
  config?: string;
  /** False when Heroic was not detected on this machine. */
  heroic_found?: boolean;
  /** Whether Heroic is installed. */
  installed?: boolean;
  /** Store login statuses. */
  stores?: Partial<StoresStatus>;
  /** Config paths probed during detection (for the settings warning). */
  probed?: string[];
}
