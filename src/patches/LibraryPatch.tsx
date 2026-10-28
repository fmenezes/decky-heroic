import {
  afterPatch,
  gamepadTabbedPageClasses,
  replacePatch,
  wrapReactType,
} from "@decky/ui";
import { routerHook, type RoutePatch } from "@decky/api";
import { type ReactElement, useEffect, useState } from "react";
import { StoreLibraryTab } from "../components/StoreLibraryTab";
import { getHeroicStatus, getStoreCount } from "../lib/heroic";
import { getSettingsSync, type PluginSettings } from "../lib/settings";
import type { Store } from "../types";

type SteamTab = {
  title: string;
  id: string;
  content: ReactElement;
  footer?: Record<string, unknown>;
  renderTabAddon?: () => ReactElement | null;
};

const STORE_TABS: {
  id: string;
  title: string;
  setting: keyof PluginSettings;
  store: Store;
}[] = [
  { id: "heroic-gog", title: "GOG", setting: "gogTab", store: "gog" },
  { id: "heroic-epic", title: "Epic", setting: "epicTab", store: "epic" },
  {
    id: "heroic-amazon",
    title: "Amazon",
    setting: "amazonTab",
    store: "amazon",
  },
  {
    id: "heroic-sideload",
    title: "Sideloaded",
    setting: "sideloadTab",
    store: "sideload",
  },
];

let routePatch: RoutePatch | undefined;
const rerenderHandlers = new Set<() => void>();

/** Ask the patched library component to re-render (e.g. after a settings change). */
export function requestLibraryRerender(): void {
  rerenderHandlers.forEach((fn) => fn());
}

/**
 * Patches the Steam library so Heroic store tabs are added to the tab bar.
 * Approach adapted from TabMaster (Tormak9970), simplified.
 */
export function patchLibrary(): void {
  if (routePatch) return;

  routePatch = routerHook.addPatch(
    "/library",
    (props: { path: string; children: ReactElement }) => {
      afterPatch(props.children, "type", (_: unknown[], ret1: ReactElement) => {
        if (!ret1?.type) return ret1;

        const [refresh, setRefresh] = useState(false);
        let innerPatch: { unpatch: () => void } | undefined;
        let memoCache: unknown;

        useEffect(() => {
          const handler = () => setRefresh(!refresh);
          rerenderHandlers.add(handler);
          return () => {
            rerenderHandlers.delete(handler);
            innerPatch?.unpatch();
          };
        });

        afterPatch(ret1, "type", (_: unknown[], ret2: ReactElement) => {
          if (!ret2?.type) return ret2;

          if (memoCache) {
            ret2.type = memoCache as typeof ret2.type;
            return ret2;
          }

          // @ts-ignore - same unwrapping trick as TabMaster
          const origMemoComponent = ret2.type.type;
          // @ts-ignore
          wrapReactType(ret2);

          innerPatch = replacePatch(ret2.type, "type", (args: unknown[]) => {
            const hooks =
              (window.SP_REACT as any)
                ?.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED
                ?.ReactCurrentDispatcher?.current ||
              Object.values(
                (window.SP_REACT as any)
                  ?.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE,
              ).find((p: any) => p?.useEffect);
            if (!hooks?.useMemo) {
              return origMemoComponent(...(args as []));
            }
            const realUseMemo = hooks.useMemo;

            const fakeUseMemo = (fn: () => unknown, deps: unknown[]) => {
              return realUseMemo(() => {
                const original = fn();

                const isNested =
                  Array.isArray(original) && Array.isArray(original[0]);
                const tabs: SteamTab[] = isNested ? original[0] : original;
                if (!Array.isArray(tabs)) return original;

                const template = tabs.find(
                  (tab: SteamTab) => tab?.id === "AllGames",
                );
                if (!template) return original;

                const TabContext = (template.content.type as any)?._context;
                const wrap = (inner: ReactElement, title: string) =>
                  TabContext
                    ? (
                        <TabContext.Provider value={{ label: title }}>
                          {inner}
                        </TabContext.Provider>
                      )
                    : inner;

                const templateFooter = template.footer
                  ? { ...template.footer }
                  : {};

                const settings = getSettingsSync();
                // while Heroic is undetected the tabs would be empty noise —
                // hide them (they return once detection succeeds and the
                // status subscriber triggers a library rerender)
                const customTabs: SteamTab[] = getHeroicStatus().found
                  ? STORE_TABS.filter((def) => settings[def.setting]).map(
                      (def) => ({
                        title: def.title,
                        id: def.id,
                        footer: templateFooter,
                        content: wrap(
                          <StoreLibraryTab store={def.store} />,
                          def.title,
                        ),
                        renderTabAddon: () => {
                          const count = getStoreCount(def.store);
                          // like Steam's native tabs, always show the count (0
                          // included) so empty stores still read consistently
                          return (
                            <span
                              className={gamepadTabbedPageClasses.TabCount}
                            >
                              {count}
                            </span>
                          );
                        },
                      }),
                    )
                  : [];

                const patchedTabs = tabs.concat(customTabs);
                return isNested ? [patchedTabs, original[1]] : patchedTabs;
              }, deps);
            };

            hooks.useMemo = fakeUseMemo;
            const res = origMemoComponent(...(args as []));
            hooks.useMemo = realUseMemo;
            return res;
          });

          memoCache = ret2.type;
          return ret2;
        });

        return ret1;
      });

      return props;
    },
  );
}

export function unpatchLibrary(): void {
  if (!routePatch) return;
  routerHook.removePatch("/library", routePatch);
  routePatch = undefined;
}
