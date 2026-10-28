import { staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaGamepad } from "react-icons/fa";
import { GameLibraryPanel } from "./components/GameLibraryPanel";
import { initSettings, subscribeSettings } from "./lib/settings";
import {
  primeLibrary,
  subscribeHeroicStatus,
} from "./lib/heroic";
import {
  patchLibrary,
  requestLibraryRerender,
  unpatchLibrary,
} from "./patches/LibraryPatch";

export default definePlugin(() => {
  // NOTE: store-count updates must NOT trigger a library rerender — doing so
  // remounts the tab content, which refetches, which updates counts again:
  // an infinite remount loop (endless "Loading…" + footer flicker). Counters
  // are read whenever Steam re-renders the tab bar on its own.
  const unsubSettings = subscribeSettings(() => requestLibraryRerender());
  // heroic detection changes which tabs exist (hidden while undetected),
  // so a status flip must re-render the library tab bar
  const unsubStatus = subscribeHeroicStatus(() => requestLibraryRerender());

  void initSettings().then(() => patchLibrary());
  void primeLibrary();

  return {
    name: "Heroic Library",
    titleView: <div className={staticClasses.Title}>Heroic Library</div>,
    content: <GameLibraryPanel />,
    icon: <FaGamepad />,
    onDismount() {
      unsubSettings();
      unsubStatus();
      unpatchLibrary();
    },
  };
});
