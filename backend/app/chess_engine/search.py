"""Machiavelli Iterative Deepening Adversarial Search Engine.

Implements:
1. Iterative Deepening Minimax with Alpha-Beta Pruning (depth 2-8+).
2. Lexicographical GoalVector bounds (Alpha/Beta tuples).
3. Transposition Table with Zobrist hashing + active milestone state bits.
4. Multi-Response Opponent Modeling: Evaluates top tactical counter-moves AND
   explicit objective-disruption responses (capturing promotion candidates,
   declining/accepting sacrifices, threatening critical milestone entities).
5. Adaptive Candidate Expansion: Expands candidate beam if no viable goal-advancing
   continuation is found in top candidate set.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import chess
import chess.polyglot

from backend.app.chess_engine.candidate_gen import (
    CandidateCategory,
    CandidateGenerator,
    TaggedCandidate,
)
from backend.app.chess_engine.goal_evaluator import GoalEvaluator, GoalVector
from backend.app.chess_engine.goal_schema import (
    FeasibilityStatus,
    GoalDefinition,
    Milestone,
    MilestoneStatus,
    MilestoneType,
)
from backend.app.chess_engine.piece_tracker import PieceTracker, SacrificeIntent
from backend.app.chess_engine.uci_client import CandidateMove


class TTFlag(str, Enum):
    EXACT = "EXACT"
    LOWERBOUND = "LOWERBOUND"
    UPPERBOUND = "UPPERBOUND"


@dataclass
class TTEntry:
    depth: int
    flag: TTFlag
    score: GoalVector
    best_move: Optional[chess.Move] = None
    age: int = 0


class TranspositionTable:
    """
    Transposition table keyed by Zobrist hash + active milestone state.
    """

    def __init__(self, max_entries: int = 262144):
        self.max_entries = max_entries
        self.table: Dict[Tuple[int, Tuple[Any, ...]], TTEntry] = {}
        self.hits: int = 0
        self.current_age: int = 0

    def get_key(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
    ) -> Tuple[int, Tuple[Any, ...]]:
        zobrist = chess.polyglot.zobrist_hash(board)
        # Capture critical milestone state
        active_id = goal.active_milestone_id or ""
        completed_count = sum(1 for m in goal.milestones if m.is_completed())
        sac_count = len(tracker.confirmed_sacrifices)
        prom_count = len(tracker.get_promoted_pieces(tracker.our_color))
        milestone_state = (active_id, completed_count, sac_count, prom_count)
        return (zobrist, milestone_state)

    def probe(
        self, key: Tuple[int, Tuple[Any, ...]], depth: int
    ) -> Optional[TTEntry]:
        entry = self.table.get(key)
        if entry is not None and entry.depth >= depth:
            self.hits += 1
            return entry
        return None

    def store(
        self,
        key: Tuple[int, Tuple[Any, ...]],
        depth: int,
        flag: TTFlag,
        score: GoalVector,
        best_move: Optional[chess.Move],
    ) -> None:
        if len(self.table) >= self.max_entries:
            # Simple eviction: clear 10% oldest entries
            keys_to_remove = list(self.table.keys())[: (self.max_entries // 10)]
            for k in keys_to_remove:
                self.table.pop(k, None)

        self.table[key] = TTEntry(
            depth=depth,
            flag=flag,
            score=score,
            best_move=best_move,
            age=self.current_age,
        )

    def clear(self) -> None:
        self.table.clear()
        self.hits = 0
        self.current_age = 0


@dataclass
class SearchResult:
    """Comprehensive output of adversarial search."""
    best_move: chess.Move
    score: GoalVector
    depth_reached: int
    nodes_evaluated: int
    time_ms: float
    pv: List[chess.Move] = field(default_factory=list)
    tagged_candidate: Optional[TaggedCandidate] = None
    tt_hits: int = 0
    expanded_candidates: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "best_move": self.best_move.uci(),
            "score": self.score.as_dict(),
            "depth_reached": self.depth_reached,
            "nodes_evaluated": self.nodes_evaluated,
            "time_ms": round(self.time_ms, 2),
            "pv": [m.uci() for m in self.pv],
            "tt_hits": self.tt_hits,
            "expanded_candidates": self.expanded_candidates,
        }


class AdversarialSearch:
    """
    Minimax adversarial search with alpha-beta pruning, opponent disruption modeling,
    and transposition table integration.
    """

    MIN_VECTOR = GoalVector(
        safety=-1e9, feasibility=-1e9, milestone=-1e9, positional=-1e9
    )
    MAX_VECTOR = GoalVector(
        safety=1e9, feasibility=1e9, milestone=1e9, positional=1e9
    )

    def __init__(
        self,
        our_color: chess.Color = chess.WHITE,
        tt_size: int = 262144,
    ):
        self.our_color = our_color
        self.evaluator = GoalEvaluator(our_color=our_color)
        self.candidate_gen = CandidateGenerator(our_color=our_color)
        self.tt = TranspositionTable(max_entries=tt_size)

        # Search execution metrics
        self.nodes_evaluated: int = 0
        self.start_time: float = 0.0
        self.time_limit_sec: float = 2.0
        self.stop_search: bool = False

    def search(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
        candidates: Optional[List[TaggedCandidate]] = None,
        max_depth: int = 4,
        time_limit_ms: int = 2500,
        node_limit: int = 100000,
    ) -> SearchResult:
        """
        Executes iterative deepening adversarial search.
        """
        self.nodes_evaluated = 0
        self.start_time = time.time()
        self.time_limit_sec = max(0.1, time_limit_ms / 1000.0)
        self.stop_search = False
        self.tt.current_age += 1

        legal_moves = list(board.legal_moves)
        if not legal_moves:
            # Terminal board
            v = self.evaluator.evaluate(board, goal, tracker)
            return SearchResult(
                best_move=chess.Move.null(),
                score=v,
                depth_reached=0,
                nodes_evaluated=1,
                time_ms=0.0,
            )

        # 1. Generate root candidate set if not provided
        root_candidates = candidates
        expanded_flag = False
        if not root_candidates:
            root_candidates = self.candidate_gen.generate_candidates(
                board, goal, tracker, max_candidates=16
            )

        # 2. Check if adaptive expansion is needed immediately
        has_goal_advancing = any(
            c.has_category(CandidateCategory.PROMOTION_ADVANCE)
            or c.has_category(CandidateCategory.SACRIFICE_OFFER)
            or c.has_category(CandidateCategory.UNDERPROMOTION)
            or c.has_category(CandidateCategory.MATING_NET)
            for c in root_candidates
        )
        if not has_goal_advancing and len(root_candidates) < len(legal_moves):
            root_candidates = self.candidate_gen.expand_candidates(
                board, goal, tracker, root_candidates, max_expanded=24
            )
            expanded_flag = True

        best_move_overall = root_candidates[0].move
        best_score_overall = self.MIN_VECTOR
        best_pv_overall: List[chess.Move] = [best_move_overall]
        best_tagged: Optional[TaggedCandidate] = root_candidates[0]
        completed_depth = 0

        # -------------------------------------------------------------
        # 3. Iterative Deepening Loop (depth 1 to max_depth)
        # -------------------------------------------------------------
        for current_depth in range(1, max_depth + 1):
            if self._is_time_up():
                break

            alpha = self.MIN_VECTOR
            beta = self.MAX_VECTOR

            best_move_at_depth: Optional[chess.Move] = None
            best_score_at_depth = self.MIN_VECTOR
            current_pv: List[chess.Move] = []

            # Search root moves
            for cand in root_candidates:
                if self._is_time_up() or self.nodes_evaluated >= node_limit:
                    self.stop_search = True
                    break

                move = cand.move
                # Clone tracker and simulate move
                tracker_clone = tracker.clone()
                is_our_move = (board.turn == self.our_color)

                # Register declared intent if move is a sacrifice offer
                declared_intent = cand.sacrifice_intent
                board.push(move)
                tracker_clone.apply_move(
                    move=move,
                    board_before=board,
                    is_our_move=is_our_move,
                    declared_intent=declared_intent,
                )

                # Call minimax for child (opponent's turn)
                score = self._minimax(
                    board=board,
                    goal=goal,
                    tracker=tracker_clone,
                    depth=current_depth - 1,
                    alpha=alpha,
                    beta=beta,
                    is_maximizing=False,
                )

                board.pop()

                if self.stop_search:
                    break

                if score > best_score_at_depth or best_move_at_depth is None:
                    best_score_at_depth = score
                    best_move_at_depth = move
                    best_tagged = cand
                    current_pv = [move]

                if score > alpha:
                    alpha = score

            if not self.stop_search and best_move_at_depth is not None:
                best_move_overall = best_move_at_depth
                best_score_overall = best_score_at_depth
                best_pv_overall = current_pv
                completed_depth = current_depth

        elapsed_ms = (time.time() - self.start_time) * 1000.0

        return SearchResult(
            best_move=best_move_overall,
            score=best_score_overall,
            depth_reached=completed_depth if completed_depth > 0 else 1,
            nodes_evaluated=self.nodes_evaluated,
            time_ms=elapsed_ms,
            pv=best_pv_overall,
            tagged_candidate=best_tagged,
            tt_hits=self.tt.hits,
            expanded_candidates=expanded_flag,
        )

    # -------------------------------------------------------------------------
    # Minimax Adversarial Search with Alpha-Beta
    # -------------------------------------------------------------------------
    def _minimax(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
        depth: int,
        alpha: GoalVector,
        beta: GoalVector,
        is_maximizing: bool,
    ) -> GoalVector:
        self.nodes_evaluated += 1

        if self._is_time_up():
            self.stop_search = True
            return self.evaluator.evaluate(board, goal, tracker)

        # Transposition table probe
        tt_key = self.tt.get_key(board, goal, tracker)
        tt_entry = self.tt.probe(tt_key, depth)
        if tt_entry is not None:
            if tt_entry.flag == TTFlag.EXACT:
                return tt_entry.score
            elif tt_entry.flag == TTFlag.LOWERBOUND and tt_entry.score >= beta:
                return tt_entry.score
            elif tt_entry.flag == TTFlag.UPPERBOUND and tt_entry.score <= alpha:
                return tt_entry.score

        # Leaf / Horizon evaluation
        if depth <= 0 or board.is_game_over():
            score = self.evaluator.evaluate(board, goal, tracker)
            return score

        # -------------------------------------------------------------
        # MAX Node (Machiavelli's Move)
        # -------------------------------------------------------------
        if is_maximizing:
            max_eval = self.MIN_VECTOR
            best_move: Optional[chess.Move] = None

            moves = self._order_our_moves(board, goal, tracker, tt_entry)

            for move in moves:
                tracker_clone = tracker.clone()
                board.push(move)
                tracker_clone.apply_move(
                    move=move,
                    board_before=board,
                    is_our_move=True,
                    declared_intent=None,
                )

                eval_score = self._minimax(
                    board, goal, tracker_clone, depth - 1, alpha, beta, False
                )
                board.pop()

                if self.stop_search:
                    return eval_score

                if eval_score > max_eval:
                    max_eval = eval_score
                    best_move = move

                if eval_score > alpha:
                    alpha = eval_score

                if beta <= alpha:
                    # Beta cutoff
                    break

            flag = (
                TTFlag.EXACT
                if (alpha < max_eval < beta)
                else (TTFlag.LOWERBOUND if max_eval >= beta else TTFlag.UPPERBOUND)
            )
            self.tt.store(tt_key, depth, flag, max_eval, best_move)
            return max_eval

        # -------------------------------------------------------------
        # MIN Node (Opponent's Move with Multi-Response Disruption Model)
        # -------------------------------------------------------------
        else:
            min_eval = self.MAX_VECTOR
            best_move: Optional[chess.Move] = None

            # Multi-response opponent moves: tactical + objective-disrupting
            opp_moves = self._order_opponent_disruption_moves(board, goal, tracker)

            for move in opp_moves:
                tracker_clone = tracker.clone()
                board.push(move)
                tracker_clone.apply_move(
                    move=move,
                    board_before=board,
                    is_our_move=False,
                    declared_intent=None,
                )

                eval_score = self._minimax(
                    board, goal, tracker_clone, depth - 1, alpha, beta, True
                )
                board.pop()

                if self.stop_search:
                    return eval_score

                if eval_score < min_eval:
                    min_eval = eval_score
                    best_move = move

                if eval_score < beta:
                    beta = eval_score

                if beta <= alpha:
                    # Alpha cutoff
                    break

            flag = (
                TTFlag.EXACT
                if (alpha < min_eval < beta)
                else (TTFlag.UPPERBOUND if min_eval <= alpha else TTFlag.LOWERBOUND)
            )
            self.tt.store(tt_key, depth, flag, min_eval, best_move)
            return min_eval

    # -------------------------------------------------------------------------
    # Opponent Disruption Move Modeling
    # -------------------------------------------------------------------------
    def _order_opponent_disruption_moves(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
        max_opp_moves: int = 8,
    ) -> List[chess.Move]:
        """
        Multi-Response Opponent Modeling:
        Evaluates moves that actively challenge Machiavelli's objective:
        1. Capturing our promotion candidate pawns or promoted knights.
        2. Accepting our sacrifice offer vs declining.
        3. Delivering checks or forced mate threats.
        4. Blockading promotion squares.
        5. General captures and tactical moves.
        """
        opp_color = not self.our_color
        surviving_pawns = tracker.get_surviving_pawns(self.our_color)
        pawn_squares = {p.current_square for p in surviving_pawns if p.current_square is not None}
        promoted_knights = tracker.get_promoted_pieces(self.our_color, chess.KNIGHT)
        pk_squares = {p.current_square for p in promoted_knights if p.current_square is not None}

        scored_moves: List[Tuple[float, chess.Move]] = []

        for move in board.legal_moves:
            disruption_score = 0.0

            # 1. Opponent captures our critical promotion candidate pawn!
            if move.to_square in pawn_squares:
                disruption_score += 150.0

            # 2. Opponent captures our promoted knight!
            if move.to_square in pk_squares:
                disruption_score += 140.0

            # 3. Opponent checks our King
            if board.gives_check(move):
                disruption_score += 100.0

            # 4. Opponent accepts sacrifice offer
            target_piece = tracker.get_piece_at(move.to_square)
            if target_piece and target_piece.color == self.our_color and target_piece.is_original:
                # If we have a pending intent on this piece, opponent accepting it is a key branch!
                is_offered = any(it.piece_id == target_piece.piece_id for it in tracker.pending_intents)
                if is_offered:
                    disruption_score += 90.0
                else:
                    disruption_score += 60.0

            # 5. Normal captures (MVV-LVA)
            if board.is_capture(move):
                disruption_score += 40.0

            scored_moves.append((disruption_score, move))

        # Sort highest disruption first
        scored_moves.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored_moves[:max_opp_moves]]

    # -------------------------------------------------------------------------
    # Move Ordering for Our Side
    # -------------------------------------------------------------------------
    def _order_our_moves(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
        tt_entry: Optional[TTEntry],
        max_branch: int = 12,
    ) -> List[chess.Move]:
        """Orders our legal moves to maximize alpha-beta pruning."""
        tt_move = tt_entry.best_move if tt_entry else None
        scored_moves: List[Tuple[float, chess.Move]] = []

        for move in board.legal_moves:
            if move == tt_move:
                scored_moves.append((10000.0, move))
                continue

            score = 0.0
            # Underpromotion to knight or promotion
            if move.promotion == chess.KNIGHT:
                score += 500.0
            elif move.promotion is not None:
                score += 300.0

            # Pawn push towards promotion
            piece = board.piece_at(move.from_square)
            if piece and piece.piece_type == chess.PAWN:
                to_rank = chess.square_rank(move.to_square)
                score += (to_rank * 20.0) if self.our_color == chess.WHITE else ((7 - to_rank) * 20.0)

            # Checks
            if board.gives_check(move):
                score += 80.0

            # Captures
            if board.is_capture(move):
                score += 50.0

            scored_moves.append((score, move))

        scored_moves.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored_moves[:max_branch]]

    def _is_time_up(self) -> bool:
        return (time.time() - self.start_time) >= self.time_limit_sec
