import { Focusable } from "@decky/ui";
import { useState } from "react";
import type { GameEntry } from "../types";

interface Props {
  game: GameEntry;
  onSelect: (game: GameEntry) => void;
  width?: number;
  height?: number;
}

// Steam native library grid specs:
// Small (<=853px): 110x165
// Medium (handheld): 134x201 (2:3 aspect ratio, 5-col layout)
// Large (docked/high-res): 172x258 (2:3 aspect ratio, 7-col layout)
const DEFAULT_CARD_WIDTH = 134;
const DEFAULT_CARD_HEIGHT = 201;

export const GameCard = ({
  game,
  onSelect,
  width = DEFAULT_CARD_WIDTH,
  height = DEFAULT_CARD_HEIGHT,
}: Props) => {
  const [focused, setFocused] = useState(false);

  return (
    <Focusable
      onActivate={() => onSelect(game)}
      onOKActionDescription="Select"
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onMouseEnter={() => setFocused(true)}
      onMouseLeave={() => setFocused(false)}
      style={{
        width: `${width}px`,
        height: `${height}px`,
        position: "relative",
        cursor: "pointer",
        flexShrink: 0,
        borderRadius: "4px",
        transform: focused ? "scale(1.05)" : "scale(1)",
        transformOrigin: "center center",
        zIndex: focused ? 10 : 1,
        boxShadow: focused
          ? "0px 14px 20px rgba(0, 0, 0, 0.55)"
          : "0px 3px 6px rgba(0, 0, 0, 0.25)",
        transition:
          "transform 0.25s cubic-bezier(0.16, 0.86, 0.43, 0.99), box-shadow 0.25s ease, z-index 0.25s step-end",
      }}
    >
      {game.art_square ? (
        <img
          src={game.art_square}
          alt={game.title}
          title={game.title}
          style={{
            width: `${width}px`,
            height: `${height}px`,
            objectFit: "cover",
            borderRadius: "4px",
            display: "block",
            pointerEvents: "none",
          }}
          onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
        />
      ) : (
        <div
          style={{
            width: `${width}px`,
            height: `${height}px`,
            borderRadius: "4px",
            background: "#2a2a2a",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: width > 150 ? "16px" : width < 120 ? "12px" : "14px",
            padding: "12px",
            textAlign: "center",
            pointerEvents: "none",
          }}
        >
          {game.title}
        </div>
      )}
    </Focusable>
  );
};
