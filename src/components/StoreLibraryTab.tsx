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

// Steam native library grid specs (reverse-engineered from Valve sp.js):
// GamepadUIBreakNarrow: 853px, GamepadUIBreakWide: 1280px, GamepadUIBreakShort: 500px
// GamepadPortraitWidthSmall: 110px, Medium: 134px, Large: 172px
const CARD_COL_GAP = 16;
const CARD_ROW_GAP = 42;

export interface CardDimensions {
  width: number;
  height: number;
}

const calculateSteamCardSize = (el: HTMLElement | null): CardDimensions => {
  if (!el) return { width: 134, height: 201 };
  const win = el.ownerDocument?.defaultView;
  const winWidth = win ? win.innerWidth : 0;
  const winHeight = win ? win.innerHeight : 0;
  const containerWidth = el.getBoundingClientRect().width;

  // Decky runs in background SharedJSContext (1x1 window), so we read the actual
  // Big Picture Mode display window from the DOM element, falling back to container width.
  const effectiveWidth = winWidth > 1 ? winWidth : containerWidth;
  const effectiveHeight = winHeight > 1 ? winHeight : el.getBoundingClientRect().height;

  if (effectiveWidth <= 853 || (effectiveHeight > 1 && effectiveHeight <= 500)) {
    return { width: 110, height: 165 };
  }
  if (effectiveWidth >= 1280) {
    return { width: 172, height: 258 };
  }
  return { width: 134, height: 201 };
};

export const StoreLibraryTab = ({ store }: Props) => {
  const [games, setGames] = useState<GameEntry[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const [cardSize, setCardSize] = useState<CardDimensions>({ width: 134, height: 201 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const update = () => {
      setCardSize(calculateSteamCardSize(el));
    };

    update();

    const ro = new ResizeObserver(() => {
      update();
    });
    ro.observe(el);

    const win = el.ownerDocument?.defaultView;
    if (win) {
      win.addEventListener("resize", update);
    }

    return () => {
      ro.disconnect();
      if (win) {
        win.removeEventListener("resize", update);
      }
    };
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

  return (
    <Focusable
      ref={containerRef}
      flow-children="column"
      style={{
        width: "100%",
        height: "100%",
        overflowY: "auto",
        boxSizing: "border-box",
        scrollPaddingTop: "20px",
      }}
    >
      {loading && (
        <div style={{ opacity: 0.7, fontSize: "14px", padding: "24px 8px" }}>
          Loading {label} library…
        </div>
      )}
      {!loading && relevantErrors.length > 0 && (
        <div
          style={{ color: "#ff6b6b", fontSize: "13px", padding: "12px 8px" }}
        >
          {relevantErrors.join("; ")}
        </div>
      )}
      {!loading && games.length === 0 && relevantErrors.length === 0 && (
        <div style={{ opacity: 0.6, fontSize: "14px", padding: "24px 8px" }}>
          No games found in your {label} library.
        </div>
      )}
      {games.length > 0 && (
        <Focusable
          flow-children="grid"
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(auto-fill, ${cardSize.width}px)`,
            gridAutoRows: `${cardSize.height}px`,
            columnGap: `${CARD_COL_GAP}px`,
            rowGap: `${CARD_ROW_GAP}px`,
            justifyContent: "space-between",
            width: "100%",
            padding: "20px 8px 32px 8px",
            boxSizing: "border-box",
          }}
        >
          {games.map((g) => (
            <GameCard
              key={g.app_name}
              game={g}
              onSelect={onSelect}
              width={cardSize.width}
              height={cardSize.height}
            />
          ))}
        </Focusable>
      )}
    </Focusable>
  );
};
