"use client";

import React, { useState } from "react";
import {
  ChevronFirst,
  ChevronLast,
  ChevronLeft,
  ChevronRight,
  Download,
  Copy,
  Check,
  FileText,
  Clock,
  ExternalLink,
} from "lucide-react";

interface MoveRecord {
  ply: number;
  moveNumber: number;
  color: "white" | "black";
  san: string;
  uci: string;
  fen: string;
  evalCp?: number;
  evalMate?: number;
  activeMilestone?: string;
  isSacrifice?: boolean;
}

interface ReplayInspectorProps {
  moveHistory: string[];
  currentPly: number;
  onSelectPly: (ply: number) => void;
  pgnText?: string;
  objectiveSummary?: Record<string, unknown>;
  moveRecords?: MoveRecord[];
}

export function ReplayInspector({
  moveHistory = [],
  currentPly,
  onSelectPly,
  pgnText,
  objectiveSummary,
  moveRecords = [],
}: ReplayInspectorProps) {
  const [copiedPgn, setCopiedPgn] = useState(false);
  const [copiedReport, setCopiedReport] = useState(false);

  const totalPlies = moveHistory.length;

  const handleCopyPgn = () => {
    if (!pgnText) return;
    navigator.clipboard.writeText(pgnText);
    setCopiedPgn(true);
    setTimeout(() => setCopiedPgn(false), 2000);
  };

  const handleDownloadPgn = () => {
    if (!pgnText) return;
    const blob = new Blob([pgnText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `machiavelli_game_${Date.now()}.pgn`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadReport = () => {
    const reportData = {
      timestamp: new Date().toISOString(),
      engine: "Machiavelli Core (Stockfish 19 + Adversarial Planner)",
      totalMoves: totalPlies,
      moveHistory,
      objectiveSummary,
      pgn: pgnText,
    };
    const blob = new Blob([JSON.stringify(reportData, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `machiavelli_objective_report_${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Group moves into pairs (White / Black)
  const movePairs: Array<{ moveNumber: number; whiteSan?: string; blackSan?: string }> = [];
  for (let i = 0; i < moveHistory.length; i += 2) {
    movePairs.push({
      moveNumber: Math.floor(i / 2) + 1,
      whiteSan: moveHistory[i],
      blackSan: moveHistory[i + 1],
    });
  }

  return (
    <div className="flex flex-col bg-slate-900/90 border border-slate-800 rounded-xl p-4 sm:p-5 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/90 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-teal-500/10 text-teal-400 border border-teal-500/20">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              Move Scrubber & Replay Inspector
            </h2>
            <p className="text-[11px] text-slate-400">
              Interactive ply history with decision telemetry and PGN export
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleCopyPgn}
            disabled={!pgnText}
            title="Copy PGN"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono border border-slate-700 transition-colors disabled:opacity-40"
          >
            {copiedPgn ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
            <span>PGN</span>
          </button>

          <button
            onClick={handleDownloadPgn}
            disabled={!pgnText}
            title="Download PGN"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono border border-slate-700 transition-colors disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">PGN</span>
          </button>

          <button
            onClick={handleDownloadReport}
            title="Download Objective Report JSON"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-mono border border-amber-500/30 transition-colors"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Report</span>
          </button>
        </div>
      </div>

      {/* Scrubber Controls */}
      <div className="flex items-center justify-between gap-3 mb-4 p-2 bg-slate-950/70 border border-slate-800 rounded-lg">
        <div className="flex items-center gap-1">
          <button
            onClick={() => onSelectPly(0)}
            disabled={currentPly <= 0}
            title="Start of Game"
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300 disabled:opacity-30"
          >
            <ChevronFirst className="w-4 h-4" />
          </button>
          <button
            onClick={() => onSelectPly(Math.max(0, currentPly - 1))}
            disabled={currentPly <= 0}
            title="Previous Ply"
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300 disabled:opacity-30"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => onSelectPly(Math.min(totalPlies, currentPly + 1))}
            disabled={currentPly >= totalPlies}
            title="Next Ply"
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300 disabled:opacity-30"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
          <button
            onClick={() => onSelectPly(totalPlies)}
            disabled={currentPly >= totalPlies}
            title="Current Board"
            className="p-1.5 rounded hover:bg-slate-800 text-slate-300 disabled:opacity-30"
          >
            <ChevronLast className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <span>Ply:</span>
          <span className="font-bold text-amber-400">{currentPly}</span>
          <span>/</span>
          <span>{totalPlies}</span>
        </div>

        <input
          type="range"
          min={0}
          max={totalPlies}
          value={currentPly}
          onChange={(e) => onSelectPly(Number(e.target.value))}
          className="flex-1 max-w-[200px] h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
        />
      </div>

      {/* Move History Table */}
      <div className="border border-slate-800 rounded-lg overflow-hidden max-h-[160px] overflow-y-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-slate-950 text-slate-400 text-[10px] uppercase border-b border-slate-800 sticky top-0">
            <tr>
              <th className="py-1.5 px-3 w-12">#</th>
              <th className="py-1.5 px-3">White</th>
              <th className="py-1.5 px-3">Black</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {movePairs.length === 0 ? (
              <tr>
                <td colSpan={3} className="py-6 text-center text-slate-400 text-xs">
                  No moves played yet.
                </td>
              </tr>
            ) : (
              movePairs.map((pair) => {
                const whitePly = (pair.moveNumber - 1) * 2 + 1;
                const blackPly = (pair.moveNumber - 1) * 2 + 2;

                const isWhiteSelected = currentPly === whitePly;
                const isBlackSelected = currentPly === blackPly;

                return (
                  <tr key={pair.moveNumber} className="hover:bg-slate-800/40">
                    <td className="py-1.5 px-3 text-slate-400">{pair.moveNumber}.</td>
                    <td
                      onClick={() => onSelectPly(whitePly)}
                      className={`py-1.5 px-3 cursor-pointer transition-colors ${
                        isWhiteSelected
                          ? "bg-amber-500/20 text-amber-300 font-bold"
                          : "text-slate-200 hover:text-amber-300"
                      }`}
                    >
                      {pair.whiteSan}
                    </td>
                    <td
                      onClick={() => pair.blackSan && onSelectPly(blackPly)}
                      className={`py-1.5 px-3 cursor-pointer transition-colors ${
                        isBlackSelected
                          ? "bg-amber-500/20 text-amber-300 font-bold"
                          : pair.blackSan
                          ? "text-slate-200 hover:text-amber-300"
                          : "text-slate-400"
                      }`}
                    >
                      {pair.blackSan || ""}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
