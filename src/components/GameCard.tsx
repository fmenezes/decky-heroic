import { Focusable } from "@decky/ui";
import type { GameEntry } from "../types";

interface Props {
  game: GameEntry;
  onSelect: (game: GameEntry) => void;
}

// Steam cover art is 600x900; these dimensions were measured against the
// native library tiles (134x201) so the grids visually match.
const CARD_WIDTH = 134;
const CARD_HEIGHT = 201;

export const GameCard = ({ game, onSelect }: Props) => {
  return (
    <Focusable
      onActivate={() => onSelect(game)}
      onOKActionDescription="Select"
      style={{ width: `${CARD_WIDTH}px`, position: "relative", cursor: "pointer" }}
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
            borderRadius: "6px",
            display: "block",
          }}
          onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
        />
      ) : (
        <div
          style={{
            width: `${CARD_WIDTH}px`,
            height: `${CARD_HEIGHT}px`,
            borderRadius: "6px",
            background: "#2a2a2a",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "13px",
            padding: "8px",
            textAlign: "center",
          }}
        >
          {game.title}
        </div>
      )}
    </Focusable>
  );
};
