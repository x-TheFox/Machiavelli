from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
import openai

logger = logging.getLogger(__name__)

from backend.app.core.config import settings
from backend.app.chess_engine.goal_schema import (
    FeasibilityStatus,
    GoalDefinition,
    Invariant,
    Milestone,
    MilestoneStatus,
    MilestoneType,
)


SYSTEM_PROMPT = """You are Machiavelli's Mission Commander and Objective Compiler.
Your role is to translate natural language chess goals into a structured GoalDefinition JSON object.

Output MUST be a single valid JSON object with the following schema:
{
  "goal_id": "string",
  "title": "string",
  "description": "string",
  "milestones": [
    {
      "id": "string (e.g. m1_sacrifice_queen)",
      "title": "string",
      "description": "string",
      "milestone_type": "SACRIFICE_PIECE" | "SACRIFICE_ALL_ORIGINAL_PIECES" | "SACRIFICE_QUEEN" | "PROMOTE_PAWN" | "PROMOTE_SURVIVING_PAWNS" | "PROMOTE_ALL_8_PAWNS" | "CHECKMATE_WITH_PIECE" | "WIN_GAME" | "CUSTOM",
      "target_piece_types": ["string" (e.g. "queen", "knight", "rook")],
      "target_piece_ids": [],
      "target_count": int,
      "dependencies": ["string" (IDs of prerequisite milestones)],
      "conditions": { "require_promoted_lineage": bool, "exclude_king": bool, "promote_to": "string" }
    }
  ],
  "invariants": [
    {
      "id": "string",
      "name": "string",
      "description": "string",
      "max_our_captures": int or null,
      "max_moves": int or null,
      "no_pawn_losses": bool
    }
  ],
  "is_ambiguous": bool,
  "clarification_prompt": string or null
}

STRICT CHESS RULES:
1. The King CAN NEVER BE SACRIFICED. If the user asks to sacrifice the king, set is_ambiguous=true and clarify that king sacrifice is illegal in chess.
2. Distinguish "every surviving pawn" (only pawns currently alive) vs "all 8 original pawns" (requires no pawn losses).
3. Ensure milestones form a valid Directed Acyclic Graph (DAG) with explicit dependencies.
"""


class GoalInterpreter:
    """
    Translates natural-language chess objectives into structured GoalDefinition DAGs
    using deterministic AST parsing for benchmark goals with LLM fallback.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.api_base = api_base or settings.OPENAI_API_BASE
        self.model = model or settings.OPENAI_MODEL

    def parse_objective(
        self,
        instruction: str,
        color: str = "white",
        force_deterministic: bool = False,
    ) -> GoalDefinition:
        """
        Parses a natural-language chess instruction into a GoalDefinition.
        First tries deterministic AST parser; if unsupported, falls back to OpenAI LLM.
        """
        clean_inst = instruction.strip()
        lower_inst = clean_inst.lower()

        # Check for illegal king sacrifice
        if re.search(r"\bsacrifice\s+(the\s+)?king\b", lower_inst):
            return GoalDefinition(
                goal_id=f"goal_{uuid.uuid4().hex[:8]}",
                raw_instruction=clean_inst,
                color=color,
                title="Illegal King Sacrifice Rejected",
                description="The King cannot be sacrificed in chess rules.",
                milestones=[],
                invariants=[],
                feasibility_status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                status_reason="The King cannot be sacrificed in chess (illegal/impossible).",
                is_ambiguous=True,
                clarification_prompt=(
                    "The King cannot be sacrificed in chess. Did you mean to sacrifice "
                    "major/minor pieces or queen instead?"
                ),
            )

        # Attempt deterministic AST parse
        ast_result = self._try_deterministic_parse(clean_inst, lower_inst, color)
        if ast_result is not None:
            return ast_result

        # If deterministic parse did not match and force_deterministic is set or no API key
        if force_deterministic or not self.api_key:
            return GoalDefinition(
                goal_id=f"goal_{uuid.uuid4().hex[:8]}",
                raw_instruction=clean_inst,
                color=color,
                title="Ambiguous / Unsupported Objective",
                description=f"Could not parse '{clean_inst}' deterministically.",
                milestones=[],
                invariants=[],
                feasibility_status=FeasibilityStatus.UNRESOLVED,
                status_reason="Objective is ambiguous or unsupported by AST parser.",
                is_ambiguous=True,
                clarification_prompt=(
                    f"Objective '{clean_inst}' could not be compiled. Please choose from standard "
                    "benchmark goals (e.g. 'Sacrifice all original pieces, promote surviving pawns to "
                    "knights, and checkmate using the promoted knights', 'Sacrifice queen', 'Knight checkmate', "
                    "'Zero captures', 'Win under 30 moves') or configure OPENAI_API_KEY."
                ),
            )

        # Fallback to OpenAI-compatible LLM
        return self._parse_with_llm(clean_inst, color)

    def _try_deterministic_parse(
        self, original: str, text: str, color: str
    ) -> Optional[GoalDefinition]:
        """
        Deterministic AST pattern matcher for the documented benchmark suite:
        1. Section 11: Sacrifice all original pieces + promote surviving pawns to knights + mate with promoted knights.
        2. Promote surviving pawns to knights.
        3. Promote all 8 pawns (to queens/knights).
        4. Sacrifice queen.
        5. Sacrifice all original pieces.
        6. Rook checkmate.
        7. Knight checkmate.
        8. Zero captures constraint.
        9. Win under move limit.
        """
        gid = f"goal_{uuid.uuid4().hex[:8]}"

        # 1. Section 11 Benchmark Goal
        # "Sacrifice all original pieces, promote every surviving pawn into a knight, and checkmate using the promoted knights"
        has_sac_all = ("sacrifice" in text and ("all original" in text or "all major" in text))
        has_prom_knights = ("promote" in text and "knight" in text)
        has_mate_promoted = ("checkmate" in text and ("promoted knight" in text or "knight" in text))

        if has_sac_all and has_prom_knights and has_mate_promoted:
            m1 = Milestone(
                id="m1_sacrifice_original_pieces",
                title="Sacrifice All Original Pieces",
                description="Genuinely sacrifice all 7 original major and minor pieces (King strictly excluded).",
                milestone_type=MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                target_piece_types=["rook", "knight", "bishop", "queen"],
                target_count=7,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
                conditions={"exclude_king": True},
            )
            m2 = Milestone(
                id="m2_promote_surviving_pawns",
                title="Promote Every Surviving Pawn into a Knight",
                description="Promote all surviving pawns into knights.",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_piece_types=["knight"],
                target_count=0,  # Dynamically resolved by PieceTracker
                status=MilestoneStatus.PENDING,
                dependencies=["m1_sacrifice_original_pieces"],
                conditions={"promote_to": "knight", "all_surviving": True},
            )
            m3 = Milestone(
                id="m3_checkmate_promoted_knights",
                title="Checkmate Using Promoted Knights",
                description="Deliver checkmate against the enemy king using the promoted knight(s).",
                milestone_type=MilestoneType.CHECKMATE_WITH_PIECE,
                target_piece_types=["knight"],
                target_count=1,
                status=MilestoneStatus.PENDING,
                dependencies=["m2_promote_surviving_pawns"],
                conditions={"require_promoted_lineage": True},
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title="Machiavelli Grand Challenge: Sacrificial Knight Ascension",
                description="Sacrifice all original pieces, promote surviving pawns to knights, and deliver checkmate with promoted knights.",
                milestones=[m1, m2, m3],
                invariants=[],
                active_milestone_id="m1_sacrifice_original_pieces",
                feasibility_status=FeasibilityStatus.FEASIBLE,
            )

        # 2. Promote surviving pawns to knights
        if "promote" in text and "surviving" in text and "knight" in text:
            m1 = Milestone(
                id="m1_promote_surviving_knights",
                title="Promote Surviving Pawns to Knights",
                description="Promote all surviving pawns into knights.",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_piece_types=["knight"],
                target_count=0,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
                conditions={"promote_to": "knight", "all_surviving": True},
            )
            m2 = Milestone(
                id="m2_win",
                title="Win the Game",
                description="Win the game after promotions.",
                milestone_type=MilestoneType.WIN_GAME,
                target_count=1,
                status=MilestoneStatus.PENDING,
                dependencies=["m1_promote_surviving_knights"],
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title="Promote Surviving Pawns to Knights",
                description="Promote all surviving pawns to knights and win.",
                milestones=[m1, m2],
                active_milestone_id="m1_promote_surviving_knights",
            )

        # 3. Promote all 8 pawns
        if "promote" in text and ("8 pawn" in text or "all eight" in text or "all 8" in text):
            promote_to = "queen"
            if "knight" in text:
                promote_to = "knight"
            elif "rook" in text:
                promote_to = "rook"
            elif "bishop" in text:
                promote_to = "bishop"

            inv = Invariant(
                id="inv_no_pawn_losses",
                name="Zero Pawn Losses",
                description="All 8 original pawns must be preserved for promotion.",
                no_pawn_losses=True,
            )
            m1 = Milestone(
                id="m1_promote_all_8_pawns",
                title=f"Promote All 8 Pawns to {promote_to.capitalize()}s",
                description=f"Promote all 8 original pawns into {promote_to}s without losing any.",
                milestone_type=MilestoneType.PROMOTE_ALL_8_PAWNS,
                target_piece_types=[promote_to],
                target_count=8,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
                conditions={"all_8_original": True, "promote_to": promote_to},
            )
            m2 = Milestone(
                id="m2_win",
                title="Win the Game",
                description="Deliver checkmate and win.",
                milestone_type=MilestoneType.WIN_GAME,
                target_count=1,
                status=MilestoneStatus.PENDING,
                dependencies=["m1_promote_all_8_pawns"],
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title=f"Promote All 8 Pawns to {promote_to.capitalize()}s",
                description=f"Promote all 8 pawns to {promote_to}s without losing any pawn.",
                milestones=[m1, m2],
                invariants=[inv],
                active_milestone_id="m1_promote_all_8_pawns",
            )

        # 4. Sacrifice Queen
        if "sacrifice" in text and "queen" in text and "all" not in text:
            m1 = Milestone(
                id="m1_sacrifice_queen",
                title="Sacrifice the Queen",
                description="Genuinely sacrifice the Queen for lesser or zero material.",
                milestone_type=MilestoneType.SACRIFICE_QUEEN,
                target_piece_types=["queen"],
                target_count=1,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
                conditions={"exclude_king": True},
            )
            m2 = Milestone(
                id="m2_win",
                title="Win the Game",
                description="Deliver checkmate and win after the queen sacrifice.",
                milestone_type=MilestoneType.WIN_GAME,
                target_count=1,
                status=MilestoneStatus.PENDING,
                dependencies=["m1_sacrifice_queen"],
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title="Queen Sacrifice",
                description="Genuinely sacrifice the Queen and win.",
                milestones=[m1, m2],
                active_milestone_id="m1_sacrifice_queen",
            )

        # 5. Sacrifice all original pieces
        if "sacrifice" in text and ("all original" in text or "all major and minor" in text):
            m1 = Milestone(
                id="m1_sacrifice_all_original",
                title="Sacrifice All Original Pieces",
                description="Genuinely sacrifice all 7 original major and minor pieces.",
                milestone_type=MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                target_piece_types=["rook", "knight", "bishop", "queen"],
                target_count=7,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
                conditions={"exclude_king": True},
            )
            m2 = Milestone(
                id="m2_win",
                title="Win the Game",
                description="Win the game after sacrificing all original pieces.",
                milestone_type=MilestoneType.WIN_GAME,
                target_count=1,
                status=MilestoneStatus.PENDING,
                dependencies=["m1_sacrifice_all_original"],
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title="Sacrifice All Original Pieces",
                description="Sacrifice all 7 original major and minor pieces and win.",
                milestones=[m1, m2],
                active_milestone_id="m1_sacrifice_all_original",
            )

        # 6. Rook checkmate
        if ("checkmate" in text or "mate" in text) and "rook" in text:
            m1 = Milestone(
                id="m1_checkmate_rook",
                title="Checkmate with a Rook",
                description="Deliver checkmate against the enemy king using a Rook.",
                milestone_type=MilestoneType.CHECKMATE_WITH_PIECE,
                target_piece_types=["rook"],
                target_count=1,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title="Rook Checkmate",
                description="Deliver checkmate with a Rook.",
                milestones=[m1],
                active_milestone_id="m1_checkmate_rook",
            )

        # 7. Knight checkmate
        if ("checkmate" in text or "mate" in text) and "knight" in text:
            m1 = Milestone(
                id="m1_checkmate_knight",
                title="Checkmate with a Knight",
                description="Deliver checkmate against the enemy king using a Knight.",
                milestone_type=MilestoneType.CHECKMATE_WITH_PIECE,
                target_piece_types=["knight"],
                target_count=1,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title="Knight Checkmate",
                description="Deliver checkmate with a Knight.",
                milestones=[m1],
                active_milestone_id="m1_checkmate_knight",
            )

        # 8. Zero captures
        if "zero capture" in text or "no capture" in text or "without capturing" in text:
            inv = Invariant(
                id="inv_zero_captures",
                name="Zero Captures Constraint",
                description="Do not capture any opponent pieces during the game.",
                max_our_captures=0,
            )
            m1 = Milestone(
                id="m1_win_zero_captures",
                title="Win with Zero Captures",
                description="Deliver checkmate and win without capturing any opponent pieces.",
                milestone_type=MilestoneType.WIN_GAME,
                target_count=1,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title="Zero Captures Victory",
                description="Win the game without capturing any enemy pieces.",
                milestones=[m1],
                invariants=[inv],
                active_milestone_id="m1_win_zero_captures",
            )

        # 9. Win under move limit
        match_moves = re.search(r"\b(?:win|checkmate|mate)?\s*(?:under|in under|within)\s+(\d+)\s+moves?\b", text)
        if match_moves and ("win" in text or "checkmate" in text or "mate" in text):
            limit = int(match_moves.group(1))
            inv = Invariant(
                id="inv_move_limit",
                name=f"Under {limit} Moves Invariant",
                description=f"Game must be won in under {limit} full moves.",
                max_moves=limit,
            )
            m1 = Milestone(
                id="m1_win_fast",
                title=f"Win in Under {limit} Moves",
                description=f"Deliver checkmate within {limit} full moves.",
                milestone_type=MilestoneType.WIN_GAME,
                target_count=1,
                status=MilestoneStatus.ACTIVE,
                dependencies=[],
            )
            return GoalDefinition(
                goal_id=gid,
                raw_instruction=original,
                color=color,
                title=f"Speed Victory (Under {limit} Moves)",
                description=f"Win the game in under {limit} moves.",
                milestones=[m1],
                invariants=[inv],
                active_milestone_id="m1_win_fast",
            )

        # No deterministic AST match
        return None

    def _parse_with_llm(self, instruction: str, color: str) -> GoalDefinition:
        """Invokes the OpenAI-compatible LLM endpoint to parse novel goals with model failover."""
        client = openai.OpenAI(api_key=self.api_key, base_url=self.api_base)

        models_to_try: List[str] = [self.model]
        fallback_list = getattr(settings, "OPENAI_FALLBACK_MODELS", [])
        for m in fallback_list:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error: Optional[Exception] = None
        for model_name in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"Parse the following chess objective for playing side '{color}':\n\"{instruction}\"",
                        },
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
                raw_content = response.choices[0].message.content or "{}"
                data = json.loads(raw_content)

                # Validate and construct GoalDefinition
                milestones = [Milestone(**m) for m in data.get("milestones", [])]
                invariants = [Invariant(**i) for i in data.get("invariants", [])]

                goal = GoalDefinition(
                    goal_id=data.get("goal_id", f"goal_{uuid.uuid4().hex[:8]}"),
                    raw_instruction=instruction,
                    color=color,
                    title=data.get("title", "Interpreted Goal"),
                    description=data.get("description", instruction),
                    milestones=milestones,
                    invariants=invariants,
                    is_ambiguous=data.get("is_ambiguous", False),
                    clarification_prompt=data.get("clarification_prompt"),
                )

                if goal.milestones and not goal.is_ambiguous:
                    goal.advance_dag()

                return goal

            except Exception as e:
                last_error = e
                logger.warning(
                    f"LLM model '{model_name}' failed with {type(e).__name__}: {e}. "
                    "Trying next fallback model if available..."
                )
                continue

        return GoalDefinition(
            goal_id=f"goal_{uuid.uuid4().hex[:8]}",
            raw_instruction=instruction,
            color=color,
            title="LLM Interpretation Failed",
            description=f"Error contacting LLM: {str(last_error)}",
            milestones=[],
            invariants=[],
            feasibility_status=FeasibilityStatus.UNRESOLVED,
            status_reason=f"LLM parsing error across models: {str(last_error)}",
            is_ambiguous=True,
            clarification_prompt="Failed to parse objective with LLM. Please rephrase or use benchmark goals.",
        )
