"use client";

import React, { useState } from "react";
import { Milestone, ObjectiveDefinition } from "@/lib/types";
import { BENCHMARK_GOALS } from "@/lib/benchmarkData";
import {
  Sparkles,
  CheckCircle2,
  Clock,
  AlertCircle,
  XCircle,
  ArrowRight,
  Target,
  Layers,
  HelpCircle,
  Send,
} from "lucide-react";

interface ObjectivePanelProps {
  currentGoal?: ObjectiveDefinition | null;
  milestones: Milestone[];
  activeMilestoneId?: string;
  onSetObjective: (text: string, goalId?: string) => void;
  isGeneratingPlan?: boolean;
}

export function ObjectivePanel({
  currentGoal,
  milestones,
  activeMilestoneId,
  onSetObjective,
  isGeneratingPlan = false,
}: ObjectivePanelProps) {
  const [customInput, setCustomInput] = useState<string>("");
  const [selectedPresetId, setSelectedPresetId] = useState<string>(
    currentGoal?.id || "main_promotion_objective"
  );

  const handleSelectPreset = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setSelectedPresetId(val);
    const found = BENCHMARK_GOALS.find((g) => g.id === val);
    if (found) {
      setCustomInput(found.prompt);
    }
  };

  const handleGeneratePlan = (e: React.FormEvent) => {
    e.preventDefault();
    const promptToSend = customInput.trim() || currentGoal?.prompt || BENCHMARK_GOALS[0].prompt;
    onSetObjective(promptToSend, selectedPresetId);
  };

  // Calculate completion percentage
  const completedCount = milestones.filter((m) => m.status === "COMPLETED").length;
  const progressPct =
    milestones.length > 0 ? Math.round((completedCount / milestones.length) * 100) : 0;

  return (
    <div className="flex flex-col bg-slate-900/90 border border-slate-800 rounded-xl p-4 sm:p-5 shadow-xl backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/90 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Target className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              Objective & Milestone DAG
            </h2>
            <p className="text-[11px] text-slate-400">
              Natural Language Mission Commander & Directed Acyclic Graph
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-amber-400 font-bold">
            {progressPct}% Done
          </span>
          <div className="w-16 h-2 bg-slate-800 rounded-full overflow-hidden border border-slate-700/60">
            <div
              className="h-full bg-gradient-to-r from-amber-500 to-emerald-400 transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      </div>

      {/* Preset Selector & NL Input */}
      <form onSubmit={handleGeneratePlan} className="flex flex-col gap-3 mb-5">
        <div>
          <label className="text-[11px] font-mono text-slate-400 mb-1 flex items-center justify-between">
            <span>Benchmark Preset Objectives</span>
            <span className="text-[10px] text-slate-400">OpenAI LLM + AST Validated</span>
          </label>
          <select
            value={selectedPresetId}
            onChange={handleSelectPreset}
            className="w-full bg-slate-950/80 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-amber-500/80 focus:ring-1 focus:ring-amber-500/50"
          >
            {BENCHMARK_GOALS.map((bg) => (
              <option key={bg.id} value={bg.id}>
                {bg.title}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-[11px] font-mono text-slate-400 mb-1 flex items-center justify-between">
            <span>Natural Language Objective</span>
            <span className="text-[10px] text-slate-400">Deconstructs into verifiable milestones</span>
          </label>
          <textarea
            rows={2}
            value={customInput || currentGoal?.prompt || ""}
            onChange={(e) => setCustomInput(e.target.value)}
            placeholder="e.g. Sacrifice all original pieces, promote every surviving pawn to a knight, and checkmate..."
            className="w-full bg-slate-950/80 border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500/80 focus:ring-1 focus:ring-amber-500/50 resize-none font-mono leading-relaxed"
          />
        </div>

        <button
          type="submit"
          disabled={isGeneratingPlan}
          className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-amber-600 via-amber-500 to-amber-600 hover:from-amber-500 hover:to-amber-500 text-slate-950 font-bold text-xs py-2.5 px-4 rounded-lg shadow-md shadow-amber-500/10 hover:shadow-amber-500/20 transition-all disabled:opacity-60 cursor-pointer disabled:cursor-not-allowed"
        >
          {isGeneratingPlan ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" />
              <span>Decomposing Milestones & Invariants...</span>
            </>
          ) : (
            <>
              <Sparkles className="w-3.5 h-3.5" />
              <span>Generate Plan & Compile DAG</span>
            </>
          )}
        </button>
      </form>

      {/* Constraints Callout */}
      {currentGoal?.constraints && currentGoal.constraints.length > 0 && (
        <div className="mb-4 p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/20 text-xs">
          <div className="flex items-center gap-1.5 text-amber-400 font-semibold mb-1 text-[11px] uppercase tracking-wider">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>Formal Constraints & Invariants</span>
          </div>
          <ul className="list-disc list-inside text-slate-300 text-[11px] space-y-0.5 font-mono">
            {currentGoal.constraints.map((c, idx) => (
              <li key={idx} className="leading-snug">
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Visual Milestone DAG Progression */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
          <span className="flex items-center gap-1">
            <Layers className="w-3 h-3 text-amber-400" />
            <span>Milestone Progression DAG</span>
          </span>
          <span>{completedCount} / {milestones.length} Milestones</span>
        </div>

        <div className="space-y-2 mt-1">
          {milestones.length === 0 ? (
            <div className="text-center py-6 border border-dashed border-slate-800 rounded-lg text-slate-400 text-xs font-mono">
              No active milestones compiled. Click &quot;Generate Plan&quot; to initialize mission.
            </div>
          ) : (
            milestones.map((milestone, idx) => {
              const isActive =
                milestone.id === activeMilestoneId || milestone.status === "ACTIVE";
              const isCompleted = milestone.status === "COMPLETED";
              const isFailed = milestone.status === "FAILED";
              const isPending = milestone.status === "PENDING" && !isActive;

              return (
                <div
                  key={milestone.id}
                  className={`p-3 rounded-lg border transition-all relative ${
                    isActive
                      ? "bg-amber-500/10 border-amber-500/60 shadow-lg shadow-amber-500/10 ring-1 ring-amber-500/40"
                      : isCompleted
                      ? "bg-emerald-950/20 border-emerald-500/40 text-slate-200"
                      : isFailed
                      ? "bg-rose-950/25 border-rose-500/40 text-slate-300"
                      : "bg-slate-950/50 border-slate-800 text-slate-400"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2.5">
                      <div className="mt-0.5">
                        {isCompleted && (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        )}
                        {isActive && (
                          <div className="w-4 h-4 rounded-full border-2 border-amber-400 border-t-transparent animate-spin shrink-0" />
                        )}
                        {isFailed && <XCircle className="w-4 h-4 text-rose-400 shrink-0" />}
                        {isPending && <Clock className="w-4 h-4 text-slate-400 shrink-0" />}
                      </div>

                      <div>
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-xs font-bold ${
                              isActive
                                ? "text-amber-300 font-semibold"
                                : isCompleted
                                ? "text-emerald-300"
                                : isFailed
                                ? "text-rose-400"
                                : "text-slate-300"
                            }`}
                          >
                            {idx + 1}. {milestone.title || milestone.name || milestone.id}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                          {milestone.description}
                        </p>
                      </div>
                    </div>

                    <div className="shrink-0 flex flex-col items-end gap-1">
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded uppercase font-bold tracking-wider ${
                          isActive
                            ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse"
                            : isCompleted
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : isFailed
                            ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                            : "bg-slate-800 text-slate-400 border border-slate-700"
                        }`}
                      >
                        {milestone.status}
                      </span>

                      {milestone.target_count !== undefined && milestone.target_count > 1 && (
                        <span className="text-[10px] font-mono text-slate-400">
                          {milestone.current_count ?? 0} / {milestone.target_count}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Dependencies indicator */}
                  {milestone.dependencies && milestone.dependencies.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[10px] font-mono text-slate-400">
                      <ArrowRight className="w-3 h-3 text-slate-400" />
                      <span>Depends on: {milestone.dependencies.join(", ")}</span>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
