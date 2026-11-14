"use client";

import React, { useState } from "react";
import { FallbackPromptData } from "@/lib/types";
import {
  Play,
  Pause,
  StepForward,
  RotateCcw,
  Flag,
  AlertTriangle,
  Check,
  Shield,
  Layers,
  Sparkles,
} from "lucide-react";

interface GameControlsProps {
  isPlaying: boolean;
  isPaused: boolean;
  onNewGame: () => void;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStepMove: () => void;
  onResign: () => void;
  fallbackPrompt?: FallbackPromptData | null;
  onDualModeDecision?: (
    decision: "RELAX_CONSTRAINT" | "CONVENTIONAL_WIN" | "RESIGN",
    revisedObjective?: string
  ) => void;
  onCloseFallbackPrompt?: () => void;
  isEngineThinking?: boolean;
}

export function GameControls({
  isPlaying,
  isPaused,
  onNewGame,
  onStart,
  onPause,
  onResume,
  onStepMove,
  onResign,
  fallbackPrompt,
  onDualModeDecision,
  onCloseFallbackPrompt,
  isEngineThinking = false,
}: GameControlsProps) {
  const [relaxedText, setRelaxedText] = useState("");

  return (
    <div className="flex flex-col gap-3 bg-slate-900/90 border border-slate-800 rounded-xl p-4 sm:p-5 shadow-xl backdrop-blur-md">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
        <h3 className="text-xs font-mono uppercase font-bold text-slate-300 tracking-wider">
          Game & Adversarial Controls
        </h3>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
          Stockfish 19 UCI
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {/* Play / Pause Toggle */}
        {!isPlaying || isPaused ? (
          <button
            onClick={isPlaying ? onResume : onStart}
            disabled={isEngineThinking}
            className="flex items-center justify-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs py-2.5 px-3 rounded-lg shadow-sm transition-all cursor-pointer disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{isPlaying ? "Resume" : "Start"}</span>
          </button>
        ) : (
          <button
            onClick={onPause}
            className="flex items-center justify-center gap-1.5 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs py-2.5 px-3 rounded-lg shadow-sm transition-all cursor-pointer"
          >
            <Pause className="w-3.5 h-3.5 fill-current" />
            <span>Pause</span>
          </button>
        )}

        {/* Step Move */}
        <button
          onClick={onStepMove}
          disabled={isEngineThinking}
          title="Force engine or opponent to execute one ply"
          className="flex items-center justify-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs py-2.5 px-3 rounded-lg border border-slate-700 transition-all cursor-pointer disabled:opacity-50"
        >
          {isEngineThinking ? (
            <div className="w-3.5 h-3.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <StepForward className="w-3.5 h-3.5" />
          )}
          <span>Step Move</span>
        </button>

        {/* New Game */}
        <button
          onClick={onNewGame}
          className="flex items-center justify-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs py-2.5 px-3 rounded-lg border border-slate-700 transition-all cursor-pointer"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>New Game</span>
        </button>

        {/* Resign */}
        <button
          onClick={onResign}
          disabled={!isPlaying}
          className="flex items-center justify-center gap-1.5 bg-rose-950/60 hover:bg-rose-900/80 text-rose-300 font-semibold text-xs py-2.5 px-3 rounded-lg border border-rose-800/60 transition-all cursor-pointer disabled:opacity-40"
        >
          <Flag className="w-3.5 h-3.5" />
          <span>Resign</span>
        </button>
      </div>

      {/* Dual-Mode Impossibility Prompt Modal */}
      {fallbackPrompt && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-amber-500/50 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-100">
                  Dual-Mode Impossibility Handler
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  Proof Engine: Mathematical Invariant Broken
                </p>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs font-mono text-amber-200 mb-5 leading-relaxed">
              <span className="font-bold text-amber-400">Trigger Reason: </span>
              {fallbackPrompt.reason}
              {fallbackPrompt.brokenConstraint && (
                <div className="mt-1 text-slate-300">
                  Constraint: {fallbackPrompt.brokenConstraint}
                </div>
              )}
            </div>

            <div className="space-y-3 mb-5">
              <p className="text-xs text-slate-300 font-semibold">
                Select an intervention strategy to proceed:
              </p>

              {/* Option 1: Relax Constraint */}
              <div className="p-3 rounded-lg border border-slate-700 bg-slate-950/60 flex flex-col gap-2">
                <button
                  onClick={() => {
                    if (onDualModeDecision) {
                      onDualModeDecision(
                        "RELAX_CONSTRAINT",
                        relaxedText || "Promote remaining surviving pawns to knights and checkmate"
                      );
                    }
                  }}
                  className="w-full flex items-center justify-between text-left text-xs font-bold text-amber-300 hover:text-amber-200 transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-amber-400" />
                    1. Relax Constraint & Continue
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300">
                    Adaptive Plan
                  </span>
                </button>
                <p className="text-[11px] text-slate-400">
                  Re-condition the planner on remaining pieces, adjusting active milestones without conceding the game.
                </p>
              </div>

              {/* Option 2: Fallback to Conventional Win */}
              <div className="p-3 rounded-lg border border-slate-700 bg-slate-950/60 flex flex-col gap-2">
                <button
                  onClick={() => {
                    if (onDualModeDecision) {
                      onDualModeDecision("CONVENTIONAL_WIN");
                    }
                  }}
                  className="w-full flex items-center justify-between text-left text-xs font-bold text-emerald-300 hover:text-emerald-200 transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-emerald-400" />
                    2. Revert to Conventional Stockfish Win
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300">
                    Engine Takeover
                  </span>
                </button>
                <p className="text-[11px] text-slate-400">
                  Disengage objective constraints. Authorize full Stockfish 19 tactical engine to maximize win probability.
                </p>
              </div>

              {/* Option 3: Resign */}
              <div className="p-3 rounded-lg border border-slate-700 bg-slate-950/60 flex flex-col gap-2">
                <button
                  onClick={() => {
                    if (onDualModeDecision) {
                      onDualModeDecision("RESIGN");
                    }
                  }}
                  className="w-full flex items-center justify-between text-left text-xs font-bold text-rose-400 hover:text-rose-300 transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Flag className="w-4 h-4 text-rose-400" />
                    3. Resign Match
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-500/20 text-rose-300">
                    Concede
                  </span>
                </button>
                <p className="text-[11px] text-slate-400">
                  Concede match immediately and log objective impossibility to database.
                </p>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={onCloseFallbackPrompt}
                className="text-xs text-slate-400 hover:text-slate-200 underline font-mono cursor-pointer"
              >
                Dismiss Modal
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
