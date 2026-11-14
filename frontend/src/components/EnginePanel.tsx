"use client";

import React from "react";
import { CandidateMove, StockfishEvalData, ExplanationData } from "@/lib/types";
import {
  Cpu,
  Brain,
  TrendingUp,
  MessageSquare,
  Sparkles,
  Layers,
  Check,
  Zap,
} from "lucide-react";

interface EnginePanelProps {
  candidates: CandidateMove[];
  selectedMove?: CandidateMove | null;
  stockfishEval?: StockfishEvalData | null;
  explanation?: ExplanationData | null;
  onSelectCandidate?: (move: CandidateMove) => void;
}

export function EnginePanel({
  candidates = [],
  selectedMove,
  stockfishEval,
  explanation,
  onSelectCandidate,
}: EnginePanelProps) {
  // Format Stockfish evaluation text
  const formatEval = (scoreCp?: number, mate?: number) => {
    if (mate !== undefined && mate !== null) {
      return mate > 0 ? `+M${mate}` : `-M${Math.abs(mate)}`;
    }
    if (scoreCp !== undefined && scoreCp !== null) {
      const formatted = (scoreCp / 100).toFixed(2);
      return scoreCp > 0 ? `+${formatted}` : formatted;
    }
    return "0.00";
  };

  return (
    <div className="flex flex-col bg-slate-900/90 border border-slate-800 rounded-xl p-4 sm:p-5 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/90 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              Engine & MultiPV Analysis
            </h2>
            <p className="text-[11px] text-slate-400">
              Stockfish 19 UCI vs Lexicographic Adversarial Goal Evaluator
            </p>
          </div>
        </div>

        {/* Engine Telemetry */}
        {stockfishEval && (
          <div className="flex items-center gap-3 text-right">
            <div>
              <div className="text-[10px] font-mono text-slate-400 uppercase">
                Stockfish Eval
              </div>
              <div
                className={`text-sm font-mono font-bold ${
                  (stockfishEval.scoreCp ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {formatEval(stockfishEval.scoreCp, stockfishEval.mate)}
              </div>
            </div>
            <div className="hidden sm:block pl-3 border-l border-slate-800 text-[10px] font-mono text-slate-400">
              <div>Depth: {stockfishEval.depth}</div>
              <div>Nodes: {(stockfishEval.nodes / 1000).toFixed(0)}k</div>
            </div>
          </div>
        )}
      </div>

      {/* Plain-Language Decision Explanation */}
      <div className="mb-4 p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs">
        <div className="flex items-center gap-1.5 text-amber-300 font-semibold mb-1 text-[11px] uppercase tracking-wider">
          <Brain className="w-3.5 h-3.5" />
          <span>Planner Intent & Rationale</span>
          {explanation?.milestoneName && (
            <span className="ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
              Target: {explanation.milestoneName}
            </span>
          )}
        </div>
        <p className="text-slate-200 text-xs leading-relaxed font-mono">
          {explanation?.text ||
            "Evaluating candidate lines. Balancing tactical safety against active milestone promotion paths without universal centipawn veto."}
        </p>

        {explanation?.tradeOffAnalysis && (
          <div className="mt-2 pt-2 border-t border-amber-500/20 text-[11px] text-amber-200/90 font-mono">
            <span className="text-amber-400 font-semibold">Trade-off: </span>
            {explanation.tradeOffAnalysis}
          </div>
        )}
      </div>

      {/* MultiPV Candidate Lines */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 mb-1">
          <span className="flex items-center gap-1">
            <TrendingUp className="w-3.5 h-3.5 text-sky-400" />
            <span>MultiPV Candidate Lines (Stockfish vs Machiavelli)</span>
          </span>
          <span className="text-[10px] text-slate-400">Lexicographical Vector V(s)</span>
        </div>

        <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
          {candidates.length === 0 ? (
            <div className="text-center py-6 border border-dashed border-slate-800 rounded-lg text-slate-400 text-xs font-mono">
              Waiting for engine evaluation...
            </div>
          ) : (
            candidates.map((cand, idx) => {
              const isSelected = selectedMove?.uci === cand.uci;
              const hasMilestoneScore =
                cand.machiavelliScore && cand.machiavelliScore.milestone > 0;

              return (
                <div
                  key={cand.uci || idx}
                  onClick={() => onSelectCandidate && onSelectCandidate(cand)}
                  className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-all flex items-center justify-between gap-3 ${
                    isSelected
                      ? "bg-amber-500/15 border-amber-500/70 shadow-md shadow-amber-500/10 ring-1 ring-amber-500/30"
                      : "bg-slate-950/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900"
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-[11px] text-slate-400 w-4">
                      #{idx + 1}
                    </span>

                    <div className="flex items-center gap-1.5">
                      <span className="font-mono font-bold text-sm text-slate-100">
                        {cand.san || cand.uci}
                      </span>
                      {cand.isObjectiveMove && (
                        <span className="flex items-center gap-0.5 text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold">
                          <Sparkles className="w-2.5 h-2.5" /> Objective
                        </span>
                      )}
                    </div>

                    {cand.intentTag && (
                      <span className="text-[10px] text-slate-400 truncate max-w-[120px] hidden sm:inline">
                        [{cand.intentTag}]
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 shrink-0 font-mono text-[11px]">
                    {/* Stockfish Eval */}
                    <div className="text-right">
                      <span className="text-[10px] text-slate-400 block text-right">
                        SF Eval
                      </span>
                      <span
                        className={`font-semibold ${
                          (cand.stockfishScoreCp ?? 0) >= 0
                            ? "text-emerald-400"
                            : "text-rose-400"
                        }`}
                      >
                        {formatEval(cand.stockfishScoreCp, cand.stockfishMate)}
                      </span>
                    </div>

                    {/* Lexicographic Score */}
                    {cand.machiavelliScore && (
                      <div className="text-right pl-2 border-l border-slate-800">
                        <span className="text-[10px] text-slate-400 block text-right">
                          Goal V(s)
                        </span>
                        <span className="text-amber-300 font-bold">
                          {cand.machiavelliScore.milestone} pts
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
