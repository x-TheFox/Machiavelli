export type FeasibilityStatus =
  | "FEASIBLE"
  | "AT_RISK"
  | "UNRESOLVED"
  | "PROVEN_IMPOSSIBLE"
  | "COMPLETED";

export type MilestoneStatus = "PENDING" | "ACTIVE" | "COMPLETED" | "FAILED";

export interface Milestone {
  id: string;
  title?: string;
  name?: string;
  description: string;
  milestone_type?: string;
  milestoneType?: string;
  status: MilestoneStatus;
  dependencies: string[];
  target_piece_types?: string[];
  targetPieceTypes?: string[];
  target_count?: number;
  targetCount?: number;
  current_count?: number;
  currentCount?: number;
  conditions?: Record<string, unknown>;
  details?: Record<string, unknown>;
}

export interface Invariant {
  id: string;
  name: string;
  description: string;
  max_our_captures?: number;
  max_moves?: number;
  no_pawn_losses?: boolean;
  disallowed_piece_types?: string[];
  protected_piece_ids?: string[];
  custom_rules?: Record<string, unknown>;
}

export interface PieceState {
  id: string;
  pieceType: string;
  color: "white" | "black";
  isOriginal: boolean;
  isOriginalPawn: boolean;
  isOriginalMajorMinor: boolean;
  square?: string;
  isCaptured: boolean;
  isSacrificed: boolean;
  isPromoted: boolean;
  promotedTo?: string;
  originatingPawnId?: string;
}

export interface PieceTrackerStats {
  survivingPawns: number;
  totalOriginalPawns: number;
  sacrificedOriginalPieces: number;
  totalOriginalMajorMinor: number;
  promotedKnights: number;
  promotedPiecesTotal: number;
  genuineSacrifices: Array<{
    pieceId: string;
    pieceType: string;
    move: string;
    turn: number;
    intentTag: string;
    capturedBy: string;
  }>;
}

export interface LexicographicalScore {
  safety: number; // 0 = safe, negative = mate threat/blunder
  feasibility: number; // 1 = feasible, 0 = at risk, -1 = proven impossible
  milestone: number; // progress score (e.g. 0 to 100)
  tacticalCompensation: number; // Stockfish centipawns
}

export interface CandidateMove {
  uci: string;
  san: string;
  stockfishScoreCp?: number;
  stockfishMate?: number;
  machiavelliScore?: LexicographicalScore;
  pv?: string[];
  intentTag?: string;
  isObjectiveMove: boolean;
  rank?: number;
}

export interface StockfishEvalData {
  scoreCp?: number;
  mate?: number;
  depth: number;
  nodes: number;
  nps?: number;
  bestMove?: string;
  hashFull?: number;
}

export interface ExplanationData {
  text: string;
  move: string;
  milestoneId?: string;
  milestoneName?: string;
  tradeOffAnalysis?: string;
  intent?: string;
}

export interface FallbackPromptData {
  reason: string;
  brokenConstraint?: string;
  brokenInvariantId?: string;
  availableChoices: Array<"RELAX_CONSTRAINT" | "CONVENTIONAL_WIN" | "RESIGN">;
}

export interface BoardStateData {
  fen: string;
  turn: "w" | "b";
  lastMove?: { from: string; to: string; san?: string };
  moveHistory: string[];
  inCheck: boolean;
  isCheckmate: boolean;
  isDraw: boolean;
  isGameOver: boolean;
  winner?: "white" | "black" | "draw" | null;
  movesPlayed: number;
  pgn?: string;
}

export interface ObjectiveDefinition {
  id: string;
  title: string;
  prompt: string;
  raw_instruction?: string;
  description: string;
  category: "promotions" | "sacrifices" | "mating_nets" | "endgame" | "challenges";
  milestones: Milestone[];
  constraints: string[];
  invariants?: Invariant[];
  activeMilestoneId?: string;
  feasibilityStatus?: FeasibilityStatus;
  statusReason?: string;
}

export interface BenchmarkTierResult {
  tierName: string;
  elo: number;
  gamesPlayed: number;
  wins: number;
  losses: number;
  draws: number;
  winRatePct: number;
  objectiveSuccessPct: number;
  averageMoves: number;
  blunders: number;
}

export interface BenchmarkGameRecord {
  id: string;
  opponent: string;
  opponentElo: number;
  openingName: string;
  eco: string;
  result: "1-0" | "0-1" | "1/2-1/2" | "*";
  machiavelliColor: "white" | "black";
  objectiveSuccess: boolean;
  movesCount: number;
  pgn: string;
  date: string;
}

export type WebSocketServerEvent =
  | { type: "BOARD_STATE"; data: BoardStateData }
  | { type: "CANDIDATE_MOVES"; data: { candidates: CandidateMove[]; selectedMove?: CandidateMove } }
  | { type: "STOCKFISH_EVAL"; data: StockfishEvalData }
  | {
      type: "MILESTONE_UPDATE";
      data: {
        milestones: Milestone[];
        activeMilestoneId?: string;
        progressPct: number;
        allCompleted: boolean;
      };
    }
  | {
      type: "FEASIBILITY_CHANGE";
      data: {
        status: FeasibilityStatus;
        reason?: string;
        threatenedEntities?: string[];
        brokenInvariantId?: string;
      };
    }
  | { type: "EXPLANATION"; data: ExplanationData }
  | { type: "FALLBACK_PROMPT"; data: FallbackPromptData }
  | {
      type: "GAME_OVER";
      data: {
        result: string;
        winner?: "white" | "black" | "draw" | null;
        reason: string;
        objectiveCompleted: boolean;
        pgn: string;
      };
    }
  | { type: "PIECE_TRACKER_UPDATE"; data: PieceTrackerStats }
  | { type: "CONNECTION_STATE"; data: { connected: boolean; latencyMs?: number; sessionId?: string } };
