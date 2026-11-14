"use client";

import React from "react";
import { FeasibilityStatus, PieceTrackerStats } from "@/lib/types";
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  AlertOctagon,
  HelpCircle,
  CheckCircle,
  Crown,
  Flame,
  ArrowUpRight,
  Info,
} from "lucide-react";

interface StrategyPanelProps {
  feasibilityStatus: FeasibilityStatus;
  feasibilityReason?: string;
  threatenedEntities?: string[];
  activePhase?: string;
  pieceStats: PieceTrackerStats;
}

export function StrategyPanel({
  feasibilityStatus = "FEASIBLE",
  feasibilityReason,
  threatenedEntities = [],
  activePhase = "Phase 1: Piece Liquidation & Maneuvering",
  pieceStats,
}: StrategyPanelProps) {
  // Render badge configuration based on feasibility status
  const statusBadgeConfig = {
    FEASIBLE: {
      label: "FEASIBLE",
      subtext: "Continuations Exist (Proof Verified)",
      icon: ShieldCheck,
      badgeColor: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
      accentBg: "border-emerald-500/30 bg-emerald-950/10",
    },
    AT_RISK: {
      label: "AT_RISK",
      subtext: "Immediate Tactical Threat to Milestones",
      icon: ShieldAlert,
      badgeColor: "bg-amber-500/20 text-amber-400 border-amber-500/40 animate-pulse",
      accentBg: "border-amber-500/30 bg-amber-950/10",
    },
    UNRESOLVED: {
      label: "UNRESOLVED",
      subtext: "Search Inconclusive (Never Assumed Impossible)",
      icon: HelpCircle,
      badgeColor: "bg-indigo-500/20 text-indigo-300 border-indigo-500/40",
      accentBg: "border-indigo-500/30 bg-indigo-950/10",
    },
    PROVEN_IMPOSSIBLE: {
      label: "PROVEN_IMPOSSIBLE",
      subtext: "Formal Mathematical Invariant Broken",
      icon: AlertOctagon,
      badgeColor: "bg-rose-500/25 text-rose-300 border-rose-500/50",
      accentBg: "border-rose-500/40 bg-rose-950/20",
    },
    COMPLETED: {
      label: "COMPLETED",
      subtext: "All Objectives & Constraints Satisfied",
      icon: CheckCircle,
      badgeColor: "bg-teal-500/25 text-teal-300 border-teal-500/50",
      accentBg: "border-teal-500/30 bg-teal-950/10",
    },
  }[feasibilityStatus] || {
    label: feasibilityStatus,
    subtext: "Status Active",
    icon: Shield,
    badgeColor: "bg-slate-700 text-slate-300 border-slate-600",
    accentBg: "border-slate-800 bg-slate-900/40",
  };

  const StatusIcon = statusBadgeConfig.icon;

  return (
    <div className="flex flex-col bg-slate-900/90 border border-slate-800 rounded-xl p-4 sm:p-5 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/90 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Shield className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              Strategy & Feasibility Engine
            </h2>
            <p className="text-[11px] text-slate-400">
              Proof-Based Invariant Verification & Persistent Piece Lineage
            </p>
          </div>
        </div>
      </div>

      {/* Active Phase Bar */}
      <div className="mb-4 p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold">
            Phase
          </span>
          <span className="font-semibold text-slate-200">{activePhase}</span>
        </div>
      </div>

      {/* Feasibility Status Card */}
      <div
        className={`p-3.5 rounded-lg border mb-4 flex flex-col gap-2 transition-all ${statusBadgeConfig.accentBg}`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <StatusIcon className="w-5 h-5 text-current" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold tracking-wider text-slate-100">
                  FEASIBILITY:
                </span>
                <span
                  className={`text-xs font-mono font-black px-2 py-0.5 rounded border uppercase ${statusBadgeConfig.badgeColor}`}
                >
                  {statusBadgeConfig.label}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {statusBadgeConfig.subtext}
              </p>
            </div>
          </div>
        </div>

        {feasibilityReason && (
          <div className="text-[11px] font-mono text-slate-300 pt-2 border-t border-slate-800/80 bg-slate-950/40 p-2 rounded">
            <span className="text-slate-400">Proof Rationale: </span>
            {feasibilityReason}
          </div>
        )}

        {threatenedEntities && threatenedEntities.length > 0 && (
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-rose-300 bg-rose-950/30 p-2 rounded border border-rose-500/20">
            <ShieldAlert className="w-3.5 h-3.5 shrink-0 text-rose-400" />
            <span>Threatened Entities: {threatenedEntities.join(", ")}</span>
          </div>
        )}
      </div>

      {/* Persistent Piece Tracking Counters */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 mb-1">
          <span className="flex items-center gap-1">
            <Crown className="w-3.5 h-3.5 text-amber-400" />
            <span>Piece Lineage & Taxonomy Tracking</span>
          </span>
          <span className="text-[10px] text-slate-400">King strictly excluded</span>
        </div>

        <div className="grid grid-cols-3 gap-2.5">
          {/* Surviving Pawns */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 flex flex-col items-center justify-center text-center">
            <div className="text-[10px] font-mono uppercase text-slate-400 mb-1">
              Surviving Pawns
            </div>
            <div className="text-xl font-bold font-mono text-emerald-400">
              {pieceStats.survivingPawns}
              <span className="text-xs text-slate-400 font-normal"> / {pieceStats.totalOriginalPawns}</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              {pieceStats.totalOriginalPawns - pieceStats.survivingPawns} captured
            </div>
          </div>

          {/* Sacrificed Original Pieces */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 flex flex-col items-center justify-center text-center relative overflow-hidden">
            <div className="text-[10px] font-mono uppercase text-slate-400 mb-1 flex items-center gap-1">
              <Flame className="w-3 h-3 text-amber-500" />
              <span>Sacrificed</span>
            </div>
            <div className="text-xl font-bold font-mono text-amber-400">
              {pieceStats.sacrificedOriginalPieces}
              <span className="text-xs text-slate-400 font-normal"> / {pieceStats.totalOriginalMajorMinor}</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              Major/Minor only
            </div>
          </div>

          {/* Promoted Knights */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 flex flex-col items-center justify-center text-center">
            <div className="text-[10px] font-mono uppercase text-slate-400 mb-1 flex items-center gap-1">
              <ArrowUpRight className="w-3 h-3 text-indigo-400" />
              <span>Knights Promoted</span>
            </div>
            <div className="text-xl font-bold font-mono text-indigo-300">
              {pieceStats.promotedKnights}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">
              Underpromotions
            </div>
          </div>
        </div>

        {/* Genuine Sacrifice Footnote */}
        <div className="mt-3 p-2.5 rounded bg-slate-950/50 border border-slate-800/80 text-[10px] text-slate-400 leading-relaxed font-mono flex items-start gap-2">
          <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
          <span>
            Sacrifice Contract: Requires deliberate pre-move milestone intent tag and opponent capture response. Unforced blunders and equal trades are disqualified.
          </span>
        </div>
      </div>
    </div>
  );
}
