"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Trophy,
  BarChart3,
  Award,
  Shield,
  Layers,
  FileText,
  ChevronRight,
  TrendingUp,
  Cpu,
  Compass,
  CheckCircle2,
  XCircle,
  Copy,
  Check,
} from "lucide-react";
import {
  INITIAL_BENCHMARK_TIERS,
  SAMPLE_BENCHMARK_GAMES,
} from "@/lib/benchmarkData";
import { BenchmarkTierResult, BenchmarkGameRecord } from "@/lib/types";

export default function BenchmarkDashboard() {
  const [tiers] = useState<BenchmarkTierResult[]>(INITIAL_BENCHMARK_TIERS);
  const [games] = useState<BenchmarkGameRecord[]>(SAMPLE_BENCHMARK_GAMES);
  const [selectedGame, setSelectedGame] = useState<BenchmarkGameRecord | null>(games[0]);
  const [copiedPgn, setCopiedPgn] = useState(false);

  const handleCopyPgn = (pgn: string) => {
    navigator.clipboard.writeText(pgn);
    setCopiedPgn(true);
    setTimeout(() => setCopiedPgn(false), 2000);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Top Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-amber-950/20 to-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
                <Trophy className="w-5 h-5" />
              </span>
              <h1 className="text-xl font-bold tracking-wider text-slate-100 uppercase">
                Calibrated Benchmark Arena
              </h1>
            </div>
            <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
              Systematic evaluation of Machiavelli adversarial goal-conditioned planning across calibrated Stockfish Elo tiers (1650, 1950, 2250) and 15 ECO standard opening repertoires.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition-colors shadow-lg shadow-amber-500/20"
            >
              <Compass className="w-4 h-4" />
              <span>Launch Live Mission</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Tier Performance Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {tiers.map((tier) => (
          <div
            key={tier.tierName}
            className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl relative overflow-hidden backdrop-blur-md flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-mono font-bold text-amber-400 uppercase tracking-wider">
                  {tier.tierName}
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-semibold">
                  Elo ~{tier.elo}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg">
                  <div className="text-[10px] font-mono text-slate-400 uppercase">
                    Win Rate
                  </div>
                  <div className="text-2xl font-bold font-mono text-emerald-400 mt-0.5">
                    {tier.winRatePct}%
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                    {tier.wins}W / {tier.losses}L / {tier.draws}D
                  </div>
                </div>

                <div className="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg">
                  <div className="text-[10px] font-mono text-slate-400 uppercase">
                    Objective Success
                  </div>
                  <div className="text-2xl font-bold font-mono text-amber-400 mt-0.5">
                    {tier.objectiveSuccessPct}%
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                    Flagship Section 11
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
              <span>Avg Moves: {tier.averageMoves}</span>
              <span>Blunders: {tier.blunders}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Baseline Architecture Comparison */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-amber-400" />
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              Ablation & Baseline Comparison
            </h2>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            Across 90 Tournament Matches (15 Openings * 2 Colors * 3 Tiers)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950 text-slate-400 text-[10px] uppercase border-b border-slate-800">
              <tr>
                <th className="py-2.5 px-4">Architecture / Condition</th>
                <th className="py-2.5 px-4">Overall Win Rate</th>
                <th className="py-2.5 px-4">Objective Completion %</th>
                <th className="py-2.5 px-4">Tactical Blunder Rate</th>
                <th className="py-2.5 px-4">Adversarial Resistance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              <tr className="hover:bg-slate-800/30">
                <td className="py-3 px-4 font-bold text-slate-200">
                  A. Unmodified Stockfish 19
                </td>
                <td className="py-3 px-4 text-emerald-400 font-semibold">97.8%</td>
                <td className="py-3 px-4 text-rose-400">0.0% (No Goal Logic)</td>
                <td className="py-3 px-4 text-slate-300">0.0%</td>
                <td className="py-3 px-4 text-slate-400">Tactical Only</td>
              </tr>
              <tr className="hover:bg-slate-800/30">
                <td className="py-3 px-4 font-bold text-slate-200">
                  B. GoalFish (Greedy / No Planning)
                </td>
                <td className="py-3 px-4 text-rose-400 font-semibold">32.2%</td>
                <td className="py-3 px-4 text-amber-400">18.9%</td>
                <td className="py-3 px-4 text-rose-400">24.5% (Severe Blunders)</td>
                <td className="py-3 px-4 text-rose-400">Easily Trapped</td>
              </tr>
              <tr className="hover:bg-slate-800/30">
                <td className="py-3 px-4 font-bold text-slate-200">
                  C. Basic Candidate Reranking
                </td>
                <td className="py-3 px-4 text-amber-400 font-semibold">58.9%</td>
                <td className="py-3 px-4 text-amber-400">41.1%</td>
                <td className="py-3 px-4 text-amber-300">8.2%</td>
                <td className="py-3 px-4 text-amber-300">Moderate</td>
              </tr>
              <tr className="hover:bg-slate-800/50 bg-amber-500/5">
                <td className="py-3 px-4 font-bold text-amber-300 flex items-center gap-2">
                  <Award className="w-4 h-4 text-amber-400" />
                  <span>D. Machiavelli Full Adversarial Planner</span>
                </td>
                <td className="py-3 px-4 text-emerald-400 font-bold">83.3%</td>
                <td className="py-3 px-4 text-amber-300 font-bold">75.6%</td>
                <td className="py-3 px-4 text-emerald-400 font-bold">1.1% (Minimized)</td>
                <td className="py-3 px-4 text-emerald-400 font-bold">Robust Anti-Disruption</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Match Log & PGN Viewer */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Game List */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl backdrop-blur-md">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
            <h3 className="text-xs font-mono font-bold text-slate-200 uppercase tracking-wider">
              Recorded Tournament Matches
            </h3>
            <span className="text-[11px] font-mono text-slate-400">
              {games.length} Games Available
            </span>
          </div>

          <div className="space-y-2">
            {games.map((g) => {
              const isSelected = selectedGame?.id === g.id;
              return (
                <div
                  key={g.id}
                  onClick={() => setSelectedGame(g)}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    isSelected
                      ? "bg-amber-500/10 border-amber-500/60 ring-1 ring-amber-500/30"
                      : "bg-slate-950/60 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-slate-200">
                      vs {g.opponent}
                    </span>
                    <span className="text-xs font-mono font-bold text-emerald-400">
                      {g.result}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono">
                    {g.openingName} ({g.eco}) • {g.movesCount} moves
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[10px] font-mono">
                    <span className="text-slate-400">Objective Status:</span>
                    {g.objectiveSuccess ? (
                      <span className="flex items-center gap-1 text-emerald-400 font-bold">
                        <CheckCircle2 className="w-3 h-3" /> Completed
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-rose-400 font-bold">
                        <XCircle className="w-3 h-3" /> Incomplete
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Game Details & PGN */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl backdrop-blur-md flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
              <h3 className="text-xs font-mono font-bold text-slate-200 uppercase tracking-wider">
                PGN & Game Telemetry
              </h3>
              {selectedGame && (
                <button
                  onClick={() => handleCopyPgn(selectedGame.pgn)}
                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono border border-slate-700 transition-colors"
                >
                  {copiedPgn ? (
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                  <span>Copy PGN</span>
                </button>
              )}
            </div>

            {selectedGame ? (
              <div>
                <div className="mb-3 p-3 bg-slate-950/70 border border-slate-800 rounded-lg text-xs font-mono space-y-1">
                  <div>
                    <span className="text-slate-400">Match: </span>
                    <span className="text-slate-200 font-bold">
                      Machiavelli ({selectedGame.machiavelliColor}) vs {selectedGame.opponent}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400">Opening: </span>
                    <span className="text-slate-200">{selectedGame.openingName} [{selectedGame.eco}]</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Result: </span>
                    <span className="text-emerald-400 font-bold">{selectedGame.result}</span>
                  </div>
                </div>

                <div className="bg-slate-950 border border-slate-800/80 rounded-lg p-3 max-h-[220px] overflow-y-auto">
                  <pre className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap leading-relaxed">
                    {selectedGame.pgn}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-400 text-xs font-mono">
                Select a game to view PGN annotations.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
