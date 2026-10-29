import { Focusable } from "@decky/ui";
import { useState } from "react";
import type { GameEntry } from "../types";

interface Props {
  game: GameEntry;
  onSelect: (game: GameEntry) => void;
}

// Steam native library grid specs: 148x222 card (2:3 aspect ratio)
const CARD_WIDTH = 148;
const CARD_HEIGHT = 222;

export const GameCard = ({ game, onSelect }: Props) => {
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
        width: `${CARD_WIDTH}px`,
        height: `${CARD_HEIGHT}px`,
        position: "relative",
        cursor: "pointer",
        flexShrink: 0,
        borderRadius: "4px",
        transform: focused ? "scale(1.08)" : "scale(1)",
        transformOrigin: "center center",
        zIndex: focused ? 10 : 1,
        boxShadow: focused
          ? "0px 14px 24px rgba(0, 0, 0, 0.65), 0 0 0 2px rgba(255, 255, 255, 0.75)"
          : "0px 4px 8px rgba(0, 0, 0, 0.3)",
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
            width: `${CARD_WIDTH}px`,
            height: `${CARD_HEIGHT}px`,
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
            width: `${CARD_WIDTH}px`,
            height: `${CARD_HEIGHT}px`,
            borderRadius: "4px",
            background: "#2a2a2a",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "14px",
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
