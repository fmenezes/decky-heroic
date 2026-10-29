import { Focusable, Navigation } from "@decky/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { GameCard } from "./GameCard";
import { ensureSteamShortcut, getLibrary, updateStoreCounts } from "../lib/heroic";
import { toaster } from "@decky/api";
import type { GameEntry, Store } from "../types";

interface Props {
  /** Show a single store. */
  store: Store;
}

const STORE_NAMES: Record<string, string> = {
  gog: "GOG",
  epic: "Epic",
  amazon: "Amazon",
  sideload: "Sideloaded",
};

const storeName = (store: string) => STORE_NAMES[store] ?? store;

// measured against Steam's native tiles: 134x201 card, 42px gap
const CARD_WIDTH = 134;
const CARD_GAP = 42;

export const StoreLibraryTab = ({ store }: Props) => {
  const [games, setGames] = useState<GameEntry[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const [rowSize, setRowSize] = useState(5);

  // Steam's grid adapts to screen size (e.g. TV = more columns): compute
  // how many tiles fit the tab's width and re-layout on resize
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const compute = () => {
      const width = el.clientWidth;
      if (width > 0) {
        setRowSize(
          Math.max(1, Math.floor((width + CARD_GAP) / (CARD_WIDTH + CARD_GAP))),
        );
      }
    };
    compute();
    const observer = new ResizeObserver(compute);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await getLibrary();
        if (!cancelled) {
          updateStoreCounts(res.games ?? []);
          setGames((res.games ?? []).filter((g) => g.store === store));
          setErrors(res.errors ?? []);
        }
      } catch (e) {
        if (!cancelled) setErrors([`Backend error: ${String(e)}`]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [store]);

  const onSelect = useCallback(async (game: GameEntry) => {
    try {
      // registers the Steam shortcut on this click if needed (explicit user
      // action), then opens Steam's native game page — Play/Install/overlay
      // all work natively there, no Steam restart required
      const appid = await ensureSteamShortcut(game);
      Navigation.Navigate(`/library/app/${appid}`);
    } catch (e) {
      toaster.toast({
        title: game.title,
        body: String(e),
      });
    }
  }, []);

  const relevantErrors = errors.filter((e) => e.startsWith(store));
  const label = storeName(store);

  const rows: GameEntry[][] = [];
  for (let i = 0; i < games.length; i += rowSize) {
    rows.push(games.slice(i, i + rowSize));
  }

  return (
    <Focusable
      flow-children="column"
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        overflowY: "auto",
        // tab wrapper adds ~25px itself; this lands the first tile at 33px,
        // aligned with the L1 icon like Steam's native grids
        padding: "0 8px",
      }}
    >
      {loading && <div>Loading {label} library…</div>}
      {!loading && relevantErrors.length > 0 && (
        <div style={{ color: "#ff6b6b", fontSize: "13px" }}>
          {relevantErrors.join("; ")}
        </div>
      )}
      {!loading && games.length === 0 && relevantErrors.length === 0 && (
        <div style={{ opacity: 0.6, fontSize: "14px", padding: "20px 0" }}>
          No games found in your {label} library.
        </div>
      )}
      {rows.map((row, rowIndex) => (
        <Focusable
          key={rowIndex}
          flow-children="row"
          style={{ display: "flex", gap: "42px", padding: "14px 0" }}
        >
          {row.map((g) => (
            <GameCard key={g.app_name} game={g} onSelect={onSelect} />
          ))}
        </Focusable>
      ))}
    </Focusable>
  );
};
