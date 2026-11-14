"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { Chess } from "chess.js";
import { wsClient } from "@/lib/websocket";
import {
  Milestone,
  ObjectiveDefinition,
  CandidateMove,
  StockfishEvalData,
  ExplanationData,
  FallbackPromptData,
  PieceTrackerStats,
  FeasibilityStatus,
} from "@/lib/types";
import { BENCHMARK_GOALS } from "@/lib/benchmarkData";
import { ChessboardView } from "@/components/ChessboardView";
import { ObjectivePanel } from "@/components/ObjectivePanel";
import { StrategyPanel } from "@/components/StrategyPanel";
import { EnginePanel } from "@/components/EnginePanel";
import { GameControls } from "@/components/GameControls";
import { ReplayInspector } from "@/components/ReplayInspector";
import { Wifi, WifiOff } from "lucide-react";

export default function MissionControlPage() {
  // Game & Board State
  const [fen, setFen] = useState<string>("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
  const [turn, setTurn] = useState<"w" | "b">("w");
  const [lastMove, setLastMove] = useState<{ from: string; to: string; san?: string } | undefined>(
    undefined
  );
  const [moveHistory, setMoveHistory] = useState<string[]>([]);
  const [currentPly, setCurrentPly] = useState<number>(0);
  const [inCheck, setInCheck] = useState<boolean>(false);
  const [isCheckmate, setIsCheckmate] = useState<boolean>(false);
  const [isDraw, setIsDraw] = useState<boolean>(false);
  const [winner, setWinner] = useState<"white" | "black" | "draw" | null>(null);
  const [playerColor, setPlayerColor] = useState<"white" | "black">("white");
  const [boardOrientation, setBoardOrientation] = useState<"white" | "black">("white");

  // Objective & Milestones
  const [currentGoal, setCurrentGoal] = useState<ObjectiveDefinition>(BENCHMARK_GOALS[0]);
  const [milestones, setMilestones] = useState<Milestone[]>(BENCHMARK_GOALS[0].milestones);
  const [activeMilestoneId, setActiveMilestoneId] = useState<string>(
    BENCHMARK_GOALS[0].milestones[0]?.id || ""
  );
  const [isGeneratingPlan, setIsGeneratingPlan] = useState<boolean>(false);

  // Strategy & Feasibility
  const [feasibilityStatus, setFeasibilityStatus] = useState<FeasibilityStatus>("FEASIBLE");
  const [feasibilityReason, setFeasibilityReason] = useState<string>(
    "Initial mathematical state verified: 8 pawns intact, all minor/major pieces present."
  );
  const [threatenedEntities, setThreatenedEntities] = useState<string[]>([]);
  const [activePhase, setActivePhase] = useState<string>("Phase 1: Minor Piece Liquidation");

  // Piece Tracking Stats
  const [pieceStats, setPieceStats] = useState<PieceTrackerStats>({
    survivingPawns: 8,
    totalOriginalPawns: 8,
    sacrificedOriginalPieces: 0,
    totalOriginalMajorMinor: 7,
    promotedKnights: 0,
    promotedPiecesTotal: 0,
    genuineSacrifices: [],
  });

  // Engine MultiPV & Explanation
  const [candidates, setCandidates] = useState<CandidateMove[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateMove | null>(null);
  const [bestTacticalCandidate, setBestTacticalCandidate] = useState<CandidateMove | null>(null);
  const [stockfishEval, setStockfishEval] = useState<StockfishEvalData | null>({
    scoreCp: 25,
    depth: 18,
    nodes: 840000,
  });
  const [explanation, setExplanation] = useState<ExplanationData | null>({
    text: "Machiavelli initialized. Stockfish 19 UCI standing by. Ready to execute goal-directed adversarial planner.",
    move: "",
    milestoneName: "Sacrifice Original Minor Pieces",
  });

  // Game Play State
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [isEngineThinking, setIsEngineThinking] = useState<boolean>(false);
  const [fallbackPrompt, setFallbackPrompt] = useState<FallbackPromptData | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [pgnText, setPgnText] = useState<string>("");

  // Store ply history of FENs for scrubbing
  const fenHistoryRef = useRef<string[]>([
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  ]);

  // Connect WebSocket on mount
  useEffect(() => {
    wsClient.connect();

    const unsubConn = wsClient.on("CONNECTION_STATE", (data: any) => {
      setIsConnected(data.connected);
    });

    const unsubSync = wsClient.on("SYNC_STATE", (data: any) => {
      if (data.fen) {
        setFen(data.fen);
        fenHistoryRef.current = [data.start_fen || data.fen];
      }
      if (data.turn) {
        setTurn(data.turn === "white" || data.turn === "w" ? "w" : "b");
      }
      if (data.move_history_san) {
        setMoveHistory(data.move_history_san);
        setCurrentPly(data.move_history_san.length);
      }
      if (data.is_check !== undefined) {
        setInCheck(data.is_check);
      }
      if (data.is_game_over) {
        setIsPlaying(false);
        if (data.result === "1-0") setWinner("white");
        else if (data.result === "0-1") setWinner("black");
        else if (data.result === "1/2-1/2") setWinner("draw");
      }
      if (data.piece_metrics) {
        setPieceStats((prev) => ({
          ...prev,
          survivingPawns: data.piece_metrics.surviving_pawns ?? prev.survivingPawns,
          sacrificedOriginalPieces: data.piece_metrics.confirmed_sacrifices ?? prev.sacrificedOriginalPieces,
          promotedKnights: data.piece_metrics.promoted_knights ?? prev.promotedKnights,
        }));
      }
      if (data.goal) {
        if (data.goal.milestones) {
          setMilestones(data.goal.milestones);
        }
        if (data.goal.active_milestone_id) {
          setActiveMilestoneId(data.goal.active_milestone_id);
          const active = data.goal.milestones?.find((m: any) => m.id === data.goal.active_milestone_id);
          if (active) {
            setActivePhase(`Phase: ${active.title || active.name || active.id}`);
          }
        }
        if (data.goal.feasibility_status) {
          setFeasibilityStatus(data.goal.feasibility_status);
        }
        if (data.goal.status_reason) {
          setFeasibilityReason(data.goal.status_reason);
        }
      }
      if (data.last_candidate_moves) {
        const cands: CandidateMove[] = data.last_candidate_moves.map((c: any) => ({
          uci: c.uci,
          san: c.san || c.uci,
          stockfishScoreCp: c.cp,
          stockfishMate: c.mate,
          isObjectiveMove: false,
          pv: c.pv,
        }));
        setCandidates(cands);
      }
      if (data.last_explanation) {
        setExplanation({
          text: typeof data.last_explanation.explanation === "string" 
            ? data.last_explanation.explanation 
            : data.last_explanation.explanation?.reasoning || JSON.stringify(data.last_explanation),
          move: data.last_explanation.move_san || data.last_explanation.move_uci || "",
        });
      }
    });

    const unsubBoard = wsClient.on("BOARD_STATE", (data: any) => {
      setFen(data.fen);
      const turnCode = data.turn === "white" || data.turn === "w" ? "w" : "b";
      setTurn(turnCode);

      if (data.uci) {
        setLastMove({
          from: data.uci.slice(0, 2),
          to: data.uci.slice(2, 4),
          san: data.san || data.uci,
        });
      }

      if (data.san) {
        setMoveHistory((prev) => {
          const next = [...prev, data.san];
          setCurrentPly(next.length);
          return next;
        });
      }

      setInCheck(Boolean(data.is_check));
      setIsCheckmate(Boolean(data.is_game_over && data.is_check));
      setIsDraw(Boolean(data.is_game_over && !data.is_check && data.result === "1/2-1/2"));

      if (data.result === "1-0") setWinner("white");
      else if (data.result === "0-1") setWinner("black");
      else if (data.result === "1/2-1/2") setWinner("draw");

      if (data.surviving_pawns_count !== undefined) {
        setPieceStats((prev) => ({
          ...prev,
          survivingPawns: data.surviving_pawns_count,
          sacrificedOriginalPieces: data.sacrificed_pieces_count ?? prev.sacrificedOriginalPieces,
          promotedKnights: data.promoted_knights_count ?? prev.promotedKnights,
        }));
      }

      fenHistoryRef.current.push(data.fen);
      setIsEngineThinking(false);
    });

    const unsubCand = wsClient.on("CANDIDATE_MOVES", (data: any) => {
      const rawList = data.candidates || [];
      const parsed: CandidateMove[] = rawList.map((c: any) => ({
        uci: c.uci,
        san: c.san || c.uci,
        stockfishScoreCp: c.cp ?? c.stockfishScoreCp,
        stockfishMate: c.mate ?? c.stockfishMate,
        isObjectiveMove: Boolean(c.is_objective_move || c.isObjectiveMove),
        pv: c.pv,
        intentTag: c.intent_tag || c.intentTag,
      }));

      setCandidates(parsed);
      if (parsed.length > 0) {
        const objMove = parsed.find((c) => c.isObjectiveMove) || parsed[0];
        setSelectedCandidate(objMove);
        setBestTacticalCandidate(parsed[0]);
      }
    });

    const unsubEval = wsClient.on("STOCKFISH_EVAL", (data: any) => {
      setStockfishEval({
        scoreCp: data.cp ?? data.scoreCp,
        mate: data.mate,
        depth: data.depth ?? 18,
        nodes: data.nodes ?? 500000,
        nps: data.nps,
        bestMove: data.best_move ?? data.bestMove,
      });
    });

    const unsubMilestone = wsClient.on("MILESTONE_UPDATE", (data: any) => {
      if (data.milestones) {
        setMilestones(data.milestones);
      }
      if (data.active_milestone_id) {
        setActiveMilestoneId(data.active_milestone_id);
        const active = data.milestones?.find((m: any) => m.id === data.active_milestone_id);
        if (active) {
          setActivePhase(`Phase: ${active.title || active.name || active.id}`);
        }
      }
    });

    const unsubFeas = wsClient.on("FEASIBILITY_CHANGE", (data: any) => {
      if (data.status) setFeasibilityStatus(data.status);
      if (data.reason) setFeasibilityReason(data.reason);
      if (data.threatened_entities) setThreatenedEntities(data.threatened_entities);
    });

    const unsubExp = wsClient.on("EXPLANATION", (data: any) => {
      const expText = typeof data === "string" 
        ? data 
        : typeof data.explanation === "string"
        ? data.explanation
        : data.explanation?.reasoning || data.text || "Machiavelli candidate line analyzed.";

      setExplanation({
        text: expText,
        move: data.move_san || data.move_uci || data.move || "",
        milestoneName: data.milestoneName,
        tradeOffAnalysis: data.tradeOffAnalysis,
      });
    });

    const unsubFallback = wsClient.on("FALLBACK_PROMPT", (data: any) => {
      setFallbackPrompt({
        reason: data.reason || "Mathematical invariant broken",
        brokenConstraint: data.broken_invariant_id || data.brokenConstraint,
        availableChoices: ["RELAX_CONSTRAINT", "CONVENTIONAL_WIN", "RESIGN"],
      });
    });

    const unsubGameOver = wsClient.on("GAME_OVER", (data: any) => {
      setIsPlaying(false);
      if (data.pgn) setPgnText(data.pgn);
      if (data.winner) setWinner(data.winner);
    });

    return () => {
      unsubConn();
      unsubSync();
      unsubBoard();
      unsubCand();
      unsubEval();
      unsubMilestone();
      unsubFeas();
      unsubExp();
      unsubFallback();
      unsubGameOver();
    };
  }, []);

  // Update PGN and Game history locally if in standalone or simulation mode
  const updateLocalMove = useCallback(
    (sourceSquare: string, targetSquare: string) => {
      try {
        const chess = new Chess(fen);
        const move = chess.move({
          from: sourceSquare,
          to: targetSquare,
          promotion: "n", // default underpromotion to Knight for Machiavelli!
        });

        if (!move) return false;

        const nextFen = chess.fen();
        const san = move.san;
        const uci = `${sourceSquare}${targetSquare}${move.promotion || ""}`;

        setFen(nextFen);
        setTurn(chess.turn());
        setLastMove({ from: sourceSquare, to: targetSquare, san });
        const nextHistory = [...moveHistory, san];
        setMoveHistory(nextHistory);
        setCurrentPly(nextHistory.length);
        fenHistoryRef.current.push(nextFen);

        setInCheck(chess.inCheck());
        setIsCheckmate(chess.isCheckmate());
        setIsDraw(chess.isDraw());
        if (chess.isCheckmate()) {
          setWinner(chess.turn() === "w" ? "black" : "white");
          setIsPlaying(false);
        }

        // Send move to backend if connected
        wsClient.sendMove(uci);

        // Update piece counters if pawn or sacrifice
        if (move.piece === "p" && (targetSquare.endsWith("8") || targetSquare.endsWith("1"))) {
          setPieceStats((prev) => ({
            ...prev,
            promotedKnights: prev.promotedKnights + 1,
          }));
        }

        return true;
      } catch (e) {
        console.warn("Invalid move:", e);
        return false;
      }
    },
    [fen, moveHistory]
  );

  // User Drop handler
  const handlePieceDrop = useCallback(
    (sourceSquare: string, targetSquare: string) => {
      return updateLocalMove(sourceSquare, targetSquare);
    },
    [updateLocalMove]
  );

  // Scrubber ply selection
  const handleSelectPly = (ply: number) => {
    setCurrentPly(ply);
    if (ply >= 0 && ply < fenHistoryRef.current.length) {
      setFen(fenHistoryRef.current[ply]);
    }
  };

  // Set Objective Handler
  const handleSetObjective = (text: string, goalId?: string) => {
    setIsGeneratingPlan(true);
    const matched = BENCHMARK_GOALS.find((g) => g.id === goalId || g.prompt === text);
    if (matched) {
      setCurrentGoal(matched);
      setMilestones(matched.milestones);
      setActiveMilestoneId(matched.milestones[0]?.id || "");
      setActivePhase(`Phase 1: ${matched.milestones[0]?.title || matched.milestones[0]?.name}`);
    }

    wsClient.sendGoal(text, goalId);

    setTimeout(() => {
      setIsGeneratingPlan(false);
      setExplanation({
        text: `Mission plan compiled for: "${text}". Initialized 5-stage milestone DAG with invariant bounds.`,
        move: "",
        milestoneName: matched?.milestones[0]?.title || "Stage 1",
      });
    }, 600);
  };

  // Game Control handlers
  const handleNewGame = () => {
    const initialFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
    setFen(initialFen);
    setTurn("w");
    setLastMove(undefined);
    setMoveHistory([]);
    setCurrentPly(0);
    setInCheck(false);
    setIsCheckmate(false);
    setIsDraw(false);
    setWinner(null);
    setIsPlaying(false);
    setIsPaused(false);
    fenHistoryRef.current = [initialFen];

    setPieceStats({
      survivingPawns: 8,
      totalOriginalPawns: 8,
      sacrificedOriginalPieces: 0,
      totalOriginalMajorMinor: 7,
      promotedKnights: 0,
      promotedPiecesTotal: 0,
      genuineSacrifices: [],
    });

    setFeasibilityStatus("FEASIBLE");
    setFeasibilityReason("New game initialized. All mathematical invariants intact.");
    setFallbackPrompt(null);

    wsClient.startNewGame({
      objectiveText: currentGoal.prompt,
      goalId: currentGoal.id,
      playerColor,
    });
  };

  const handleStart = () => {
    setIsPlaying(true);
    setIsPaused(false);
    wsClient.resumeGame();
  };

  const handlePause = () => {
    setIsPaused(true);
    wsClient.pauseGame();
  };

  const handleResume = () => {
    setIsPaused(false);
    wsClient.resumeGame();
  };

  const handleStepMove = () => {
    setIsEngineThinking(true);
    wsClient.requestEngineStep();

    // Fallback simulation if disconnected
    if (!isConnected) {
      setTimeout(() => {
        try {
          const chess = new Chess(fen);
          const moves = chess.moves({ verbose: true });
          if (moves.length > 0) {
            const randomMove = moves[Math.floor(Math.random() * Math.min(3, moves.length))];
            updateLocalMove(randomMove.from, randomMove.to);
          }
        } finally {
          setIsEngineThinking(false);
        }
      }, 300);
    }
  };

  const handleResign = () => {
    setIsPlaying(false);
    setWinner(playerColor === "white" ? "black" : "white");
    wsClient.resignGame();
  };

  const handleDualModeDecision = (
    decision: "RELAX_CONSTRAINT" | "CONVENTIONAL_WIN" | "RESIGN",
    revisedObjective?: string
  ) => {
    wsClient.sendDualModeDecision(decision, revisedObjective);
    setFallbackPrompt(null);
    if (decision === "RESIGN") {
      setIsPlaying(false);
      setWinner(playerColor === "white" ? "black" : "white");
    } else if (decision === "CONVENTIONAL_WIN") {
      setExplanation({
        text: "Objective constraints disengaged. Stockfish 19 UCI now playing with unrestricted tactical strength.",
        move: "",
      });
      setFeasibilityStatus("UNRESOLVED");
      setFeasibilityReason("Reverted to conventional Stockfish win mode.");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Top Telemetry & Status Ribbon */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/90 border border-slate-800 rounded-xl px-4 py-3 shadow-lg backdrop-blur-md">
        <div className="flex items-center gap-3">
          {/* Connection Status Pill */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono font-semibold border ${
              isConnected
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                : "bg-amber-500/10 text-amber-400 border-amber-500/30"
            }`}
          >
            {isConnected ? (
              <>
                <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                <span>WS CONNECTED</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5 text-amber-400" />
                <span>STANDALONE / RECONNECTING</span>
              </>
            )}
          </div>

          <div className="h-4 w-[1px] bg-slate-800 hidden sm:block" />

          {/* Active Mission Title */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-slate-400 uppercase hidden sm:inline">
              Mission:
            </span>
            <span className="text-xs font-bold text-amber-300">
              {currentGoal.title}
            </span>
          </div>
        </div>

        {/* Engine and Opponent Settings */}
        <div className="flex items-center gap-3 text-xs font-mono">
          <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800">
            <span className="text-slate-400">Opponent:</span>
            <span className="text-slate-200 font-semibold">Stockfish 19 (1950 Elo)</span>
          </div>

          <button
            onClick={() => {
              const next = playerColor === "white" ? "black" : "white";
              setPlayerColor(next);
              setBoardOrientation(next);
            }}
            className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 px-2.5 py-1 rounded-lg border border-slate-700 transition-colors"
          >
            <span className="text-slate-400">Play As:</span>
            <span className="font-semibold capitalize text-amber-300">{playerColor}</span>
          </button>
        </div>
      </div>

      {/* Main Mission Control Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Objective & Strategy Panels (4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-6 order-2 lg:order-1">
          <ObjectivePanel
            currentGoal={currentGoal}
            milestones={milestones}
            activeMilestoneId={activeMilestoneId}
            onSetObjective={handleSetObjective}
            isGeneratingPlan={isGeneratingPlan}
          />

          <StrategyPanel
            feasibilityStatus={feasibilityStatus}
            feasibilityReason={feasibilityReason}
            threatenedEntities={threatenedEntities}
            activePhase={activePhase}
            pieceStats={pieceStats}
          />
        </div>

        {/* Center Column: Interactive Chessboard (4 cols) */}
        <div className="lg:col-span-4 flex flex-col items-center gap-4 order-1 lg:order-2">
          <ChessboardView
            fen={fen}
            turn={turn}
            lastMove={lastMove}
            inCheck={inCheck}
            isCheckmate={isCheckmate}
            isDraw={isDraw}
            winner={winner}
            selectedCandidate={selectedCandidate}
            bestTacticalCandidate={bestTacticalCandidate}
            onPieceDrop={handlePieceDrop}
            orientation={boardOrientation}
            onOrientationToggle={() =>
              setBoardOrientation(boardOrientation === "white" ? "black" : "white")
            }
          />
        </div>

        {/* Right Column: Engine Analysis & Game Controls (4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-6 order-3">
          <EnginePanel
            candidates={candidates}
            selectedMove={selectedCandidate}
            stockfishEval={stockfishEval}
            explanation={explanation}
            onSelectCandidate={(cand) => setSelectedCandidate(cand)}
          />

          <GameControls
            isPlaying={isPlaying}
            isPaused={isPaused}
            onNewGame={handleNewGame}
            onStart={handleStart}
            onPause={handlePause}
            onResume={handleResume}
            onStepMove={handleStepMove}
            onResign={handleResign}
            fallbackPrompt={fallbackPrompt}
            onDualModeDecision={handleDualModeDecision}
            onCloseFallbackPrompt={() => setFallbackPrompt(null)}
            isEngineThinking={isEngineThinking}
          />
        </div>
      </div>

      {/* Bottom Row: Move Scrubber & Replay Inspector */}
      <div className="w-full">
        <ReplayInspector
          moveHistory={moveHistory}
          currentPly={currentPly}
          onSelectPly={handleSelectPly}
          pgnText={pgnText}
          objectiveSummary={{
            goalTitle: currentGoal.title,
            feasibility: feasibilityStatus,
            milestonesCompleted: milestones.filter((m) => m.status === "COMPLETED").length,
            totalMilestones: milestones.length,
            pieceStats,
          }}
        />
      </div>
    </div>
  );
}
