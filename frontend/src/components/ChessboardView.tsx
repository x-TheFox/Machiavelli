"use client";

import React, { useState, useMemo, useCallback } from "react";
import { Chessboard } from "react-chessboard";
import { Chess } from "chess.js";
type BoardArrow = {
  startSquare: string;
  endSquare: string;
  color: string;
};
import { CandidateMove } from "@/lib/types";
import { RotateCcw, Crosshair, Sparkles, ShieldAlert, Award } from "lucide-react";

interface ChessboardViewProps {
  fen: string;
  turn: "w" | "b";
  lastMove?: { from: string; to: string; san?: string };
  inCheck?: boolean;
  isCheckmate?: boolean;
  isDraw?: boolean;
  winner?: "white" | "black" | "draw" | null;
  selectedCandidate?: CandidateMove | null;
  bestTacticalCandidate?: CandidateMove | null;
  threatenedSquares?: string[];
  onPieceDrop?: (sourceSquare: string, targetSquare: string) => boolean;
  orientation?: "white" | "black";
  onOrientationToggle?: () => void;
  disabled?: boolean;
}

export function ChessboardView({
  fen,
  turn,
  lastMove,
  inCheck = false,
  isCheckmate = false,
  isDraw = false,
  winner = null,
  selectedCandidate = null,
  bestTacticalCandidate = null,
  threatenedSquares = [],
  onPieceDrop,
  orientation = "white",
  onOrientationToggle,
  disabled = false,
}: ChessboardViewProps) {
  const [boardOrientation, setBoardOrientation] = useState<"white" | "black">(orientation);

  // Keep internal orientation in sync if controlled prop changes
  React.useEffect(() => {
    setBoardOrientation(orientation);
  }, [orientation]);

  // Construct arrows:
  // 1. Selected candidate move (Machiavelli objective move) -> Amber/Gold arrow
  // 2. Pure Stockfish best tactical move -> Cyan/Sky arrow (if different from selected)
  // 3. Last move played -> subtle green arrow
  const customArrows: BoardArrow[] = useMemo(() => {
    const arrows: BoardArrow[] = [];

    if (selectedCandidate && selectedCandidate.uci && selectedCandidate.uci.length >= 4) {
      const from = selectedCandidate.uci.slice(0, 2);
      const to = selectedCandidate.uci.slice(2, 4);
      arrows.push({
        startSquare: from,
        endSquare: to,
        color: "rgba(245, 158, 11, 0.85)", // Amber-500
      });
    }

    if (
      bestTacticalCandidate &&
      bestTacticalCandidate.uci &&
      bestTacticalCandidate.uci.length >= 4 &&
      bestTacticalCandidate.uci !== selectedCandidate?.uci
    ) {
      const from = bestTacticalCandidate.uci.slice(0, 2);
      const to = bestTacticalCandidate.uci.slice(2, 4);
      arrows.push({
        startSquare: from,
        endSquare: to,
        color: "rgba(14, 165, 233, 0.65)", // Sky-500 tactical alternative
      });
    }

    return arrows;
  }, [selectedCandidate, bestTacticalCandidate]);

  // Find King square if in check to highlight in red
  const kingCheckSquare = useMemo(() => {
    if (!inCheck) return null;
    try {
      const c = new Chess(fen);
      const targetKing = `${turn}k`;
      const board = c.board();
      for (let r = 0; r < 8; r++) {
        for (let col = 0; col < 8; col++) {
          const piece = board[r][col];
          if (piece && piece.type === "k" && piece.color === turn) {
            const file = String.fromCharCode(97 + col);
            const rank = 8 - r;
            return `${file}${rank}`;
          }
        }
      }
    } catch {
      // ignore
    }
    return null;
  }, [fen, inCheck, turn]);

  // Construct custom square styles for last-move highlights, check, and threatened squares
  const customSquareStyles = useMemo(() => {
    const styles: Record<string, React.CSSProperties> = {};

    // Last move highlight (soft gold/yellow)
    if (lastMove) {
      styles[lastMove.from] = {
        backgroundColor: "rgba(234, 179, 8, 0.28)",
      };
      styles[lastMove.to] = {
        backgroundColor: "rgba(234, 179, 8, 0.4)",
      };
    }

    // Threatened squares highlight (soft red)
    if (threatenedSquares && threatenedSquares.length > 0) {
      threatenedSquares.forEach((sq) => {
        styles[sq] = {
          ...styles[sq],
          backgroundColor: "rgba(239, 68, 68, 0.35)",
          boxShadow: "inset 0 0 8px rgba(220, 38, 38, 0.7)",
        };
      });
    }

    // King in check highlight (vivid pulsing red)
    if (kingCheckSquare) {
      styles[kingCheckSquare] = {
        background: "radial-gradient(circle, rgba(239,68,68,0.85) 0%, rgba(185,28,28,0.4) 70%, transparent 100%)",
        boxShadow: "0 0 12px 3px rgba(239, 68, 68, 0.8)",
      };
    }

    return styles;
  }, [lastMove, threatenedSquares, kingCheckSquare]);

  const handlePieceDrop = useCallback(
    ({ sourceSquare, targetSquare }: { sourceSquare: string; targetSquare: string | null }) => {
      if (disabled || !targetSquare) return false;
      if (onPieceDrop) {
        return onPieceDrop(sourceSquare, targetSquare);
      }
      return true;
    },
    [disabled, onPieceDrop]
  );

  return (
    <div className="flex flex-col items-center w-full max-w-[560px] mx-auto bg-slate-900/80 border border-slate-800 rounded-xl p-3 sm:p-4 shadow-2xl backdrop-blur-md relative">
      {/* Board Status Bar */}
      <div className="w-full flex items-center justify-between pb-3 px-1 border-b border-slate-800/80 mb-3 text-xs">
        <div className="flex items-center gap-2">
          <div
            className={`w-3.5 h-3.5 rounded-full border border-slate-700 flex items-center justify-center ${
              turn === "w" ? "bg-white text-slate-950" : "bg-slate-950 border-slate-600 text-white"
            }`}
          />
          <span className="font-semibold text-slate-200">
            {turn === "w" ? "White" : "Black"} to move
          </span>
          {inCheck && !isCheckmate && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/40 font-mono text-[11px] font-bold animate-pulse">
              <ShieldAlert className="w-3 h-3" /> CHECK
            </span>
          )}
          {isCheckmate && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono text-[11px] font-bold">
              <Award className="w-3 h-3" /> CHECKMATE ({winner?.toUpperCase()} WINS)
            </span>
          )}
          {isDraw && (
            <span className="px-2 py-0.5 rounded bg-slate-700/50 text-slate-300 border border-slate-600 font-mono text-[11px] font-bold">
              DRAW
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const next = boardOrientation === "white" ? "black" : "white";
              setBoardOrientation(next);
              if (onOrientationToggle) onOrientationToggle();
            }}
            title="Flip Board Orientation"
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium transition-colors"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Flip</span>
          </button>
        </div>
      </div>

      {/* The Board Container */}
      <div className="w-full aspect-square max-w-[512px] rounded-lg overflow-hidden border border-slate-700/70 shadow-inner relative">
        <Chessboard
          options={{
            position: fen,
            boardOrientation: boardOrientation,
            arrows: customArrows,
            squareStyles: customSquareStyles,
            showNotation: true,
            allowDragging: !disabled,
            canDragPiece: () => !disabled,
            onPieceDrop: handlePieceDrop,
            darkSquareStyle: { backgroundColor: "#607274" },
            lightSquareStyle: { backgroundColor: "#ded0b6" },
            boardStyle: {
              borderRadius: "6px",
              boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.6)",
            },
          }}
        />
      </div>

      {/* Legend / Overlay Indicators */}
      <div className="w-full flex flex-wrap items-center justify-between gap-2 pt-3 px-1 text-[11px] text-slate-400 font-mono border-t border-slate-800/80 mt-3">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block shadow-sm shadow-amber-500/50" />
            <span className="text-slate-300 font-medium">Machiavelli Objective Move</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-400 inline-block shadow-sm shadow-sky-400/50" />
            <span className="text-slate-300 font-medium">Stockfish Tactical Best</span>
          </span>
        </div>
        {lastMove?.san && (
          <div className="text-slate-400">
            Last: <span className="text-amber-300 font-semibold font-mono">{lastMove.san}</span>
          </div>
        )}
      </div>
    </div>
  );
}
