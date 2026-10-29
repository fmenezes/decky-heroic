import { Focusable } from "@decky/ui";
import type { GameEntry } from "../types";

interface Props {
  game: GameEntry;
  onSelect: (game: GameEntry) => void;
}

// Steam native library grid specs: 148x222 card (2:3 aspect ratio)
const CARD_WIDTH = 148;
const CARD_HEIGHT = 222;

export const GameCard = ({ game, onSelect }: Props) => {
  return (
    <Focusable
      onActivate={() => onSelect(game)}
      onOKActionDescription="Select"
      style={{
        width: `${CARD_WIDTH}px`,
        height: `${CARD_HEIGHT}px`,
        position: "relative",
        cursor: "pointer",
        flexShrink: 0,
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
          }}
        >
          {game.title}
        </div>
      )}
    </Focusable>
  );
};
