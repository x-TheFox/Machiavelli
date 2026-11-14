import { ObjectiveDefinition, BenchmarkTierResult, BenchmarkGameRecord } from "./types";

export const BENCHMARK_GOALS: ObjectiveDefinition[] = [
  {
    id: "main_promotion_objective",
    title: "The Grand Machiavelli Promotion (Section 11)",
    prompt:
      "Win by sacrificing all original pieces, promoting every surviving pawn into a knight, and delivering checkmate using the promoted knights.",
    description:
      "The flagship Machiavelli mission. Requires sacrificing all 7 original major and minor pieces (Q, 2R, 2B, 2N), advancing all surviving pawns to rank 8, promoting them strictly to knights, and delivering checkmate where the mating attack is executed by the promoted knights. The King is strictly excluded from sacrifice.",
    category: "promotions",
    milestones: [
      {
        id: "m1_sacrifice_minors",
        name: "Sacrifice Original Minor Pieces",
        description: "Intentionally sacrifice all original Knights and Bishops (4 pieces) with opponent acceptance.",
        status: "PENDING",
        dependencies: [],
        targetCount: 4,
        currentCount: 0,
      },
      {
        id: "m2_sacrifice_majors",
        name: "Sacrifice Original Major Pieces",
        description: "Intentionally sacrifice the Queen and both original Rooks (3 pieces) with tactical soundness.",
        status: "PENDING",
        dependencies: ["m1_sacrifice_minors"],
        targetCount: 3,
        currentCount: 0,
      },
      {
        id: "m3_advance_pawns",
        name: "Advance Surviving Pawns",
        description: "Safely navigate all surviving pawns through the board toward the 7th rank.",
        status: "PENDING",
        dependencies: ["m2_sacrifice_majors"],
      },
      {
        id: "m4_promote_knights",
        name: "Promote Every Surviving Pawn to Knight",
        description: "Underpromote each surviving pawn strictly into a Knight on the 8th rank.",
        status: "PENDING",
        dependencies: ["m3_advance_pawns"],
      },
      {
        id: "m5_knight_checkmate",
        name: "Deliver Checkmate with Promoted Knights",
        description: "Execute a coordinated mating net using the promoted knights against the enemy King.",
        status: "PENDING",
        dependencies: ["m4_promote_knights"],
      },
    ],
    constraints: [
      "No intentional sacrifice of the King (King is excluded).",
      "Sacrifices must be intentional with opponent capture, not unforced blunders.",
      "Promotions must strictly choose Knight (no Queens).",
      "Surviving pawns must all promote.",
    ],
  },
  {
    id: "queen_sacrifice_mate",
    title: "Immortal Queen Sacrifice",
    prompt: "Sacrifice Queen intentionally for tactical compensation and deliver checkmate with minor pieces.",
    description: "Classic romantic chess ideal: offer the Queen on an active square, draw the opponent king out, and construct a forced minor piece mating net.",
    category: "sacrifices",
    milestones: [
      {
        id: "m1_queen_offer",
        name: "Offer Queen Sacrifice",
        description: "Place Queen on an attacked square with negative immediate material balance.",
        status: "PENDING",
        dependencies: [],
      },
      {
        id: "m2_sacrifice_accepted",
        name: "Opponent Accepts Queen",
        description: "Opponent captures Queen, verifying genuine sacrifice.",
        status: "PENDING",
        dependencies: ["m1_queen_offer"],
      },
      {
        id: "m3_minor_piece_mate",
        name: "Minor Piece Mating Net",
        description: "Checkmate opponent king using coordinated Bishops and Knights.",
        status: "PENDING",
        dependencies: ["m2_sacrifice_accepted"],
      },
    ],
    constraints: [
      "Queen sacrifice must be verified by opponent capture.",
      "Checkmate must not be delivered by a remaining Queen.",
    ],
  },
  {
    id: "rook_elevator_mate",
    title: "Rook Elevator Checkmate",
    prompt: "Deliver checkmate with a Rook without moving any pawns beyond the 4th rank.",
    description: "Restrict pawn pushes to rank 4 or lower; mobilize heavy pieces through open files and rank lifts to force a back-rank or side-board checkmate.",
    category: "mating_nets",
    milestones: [
      {
        id: "m1_open_file",
        name: "Pawn Structure Control",
        description: "Retain all pawns at or behind rank 4 while clearing files for Rooks.",
        status: "PENDING",
        dependencies: [],
      },
      {
        id: "m2_rook_lift",
        name: "Rook Lift to 3rd/4th Rank",
        description: "Swing Rook along a 3rd or 4th rank lift to attack enemy King.",
        status: "PENDING",
        dependencies: ["m1_open_file"],
      },
      {
        id: "m3_rook_checkmate",
        name: "Deliver Checkmate with Rook",
        description: "Final checkmate delivered directly by a Rook.",
        status: "PENDING",
        dependencies: ["m2_rook_lift"],
      },
    ],
    constraints: [
      "No friendly pawn may occupy rank 5, 6, 7, or 8 at any point in the game.",
    ],
  },
  {
    id: "pacifist_pawn_victory",
    title: "Zero Pawn Captures Victory",
    prompt: "Win the game without capturing any opponent pawns.",
    description: "Navigate piece play cleanly: captures of opponent major and minor pieces are allowed, but opponent pawns must remain untouched on the board.",
    category: "challenges",
    milestones: [
      {
        id: "m1_piece_domination",
        name: "Outmaneuver Pieces",
        description: "Eliminate opponent major/minor pieces while completely dodging pawn captures.",
        status: "PENDING",
        dependencies: [],
      },
      {
        id: "m2_deliver_checkmate",
        name: "Checkmate with Intact Enemy Pawns",
        description: "Checkmate enemy King with all opponent pawns surviving.",
        status: "PENDING",
        dependencies: ["m1_piece_domination"],
      },
    ],
    constraints: [
      "Zero captures of enemy pawns permitted. Capturing a pawn breaks feasibility immediately.",
    ],
  },
  {
    id: "octo_queen_ascension",
    title: "Octo-Queen Ascension",
    prompt: "Promote all 8 original pawns and win without losing a single pawn.",
    description: "Extreme constraint requiring 100% pawn retention and 8 promotions. Losing any original pawn immediately triggers mathematical impossibility.",
    category: "endgame",
    milestones: [
      {
        id: "m1_retain_8_pawns",
        name: "Retain All 8 Pawns",
        description: "Protect all 8 original pawns through middle-game tactics.",
        status: "PENDING",
        dependencies: [],
        targetCount: 8,
        currentCount: 8,
      },
      {
        id: "m2_promote_all_8",
        name: "Promote 8 Pawns",
        description: "Successfully promote all 8 pawns to Queens.",
        status: "PENDING",
        dependencies: ["m1_retain_8_pawns"],
        targetCount: 8,
        currentCount: 0,
      },
      {
        id: "m3_deliver_mate",
        name: "Deliver Mate",
        description: "Checkmate opponent king with newly promoted Queens.",
        status: "PENDING",
        dependencies: ["m2_promote_all_8"],
      },
    ],
    constraints: [
      "Any capture of a friendly pawn renders this objective PROVEN_IMPOSSIBLE.",
    ],
  },
];

export const INITIAL_BENCHMARK_TIERS: BenchmarkTierResult[] = [
  {
    tierName: "Stockfish Tier 1",
    elo: 1650,
    gamesPlayed: 30,
    wins: 27,
    losses: 1,
    draws: 2,
    winRatePct: 93.3,
    objectiveSuccessPct: 86.7,
    averageMoves: 44.2,
    blunders: 0,
  },
  {
    tierName: "Stockfish Tier 2",
    elo: 1950,
    gamesPlayed: 30,
    wins: 24,
    losses: 3,
    draws: 3,
    winRatePct: 85.0,
    objectiveSuccessPct: 76.7,
    averageMoves: 52.8,
    blunders: 1,
  },
  {
    tierName: "Stockfish Tier 3",
    elo: 2250,
    gamesPlayed: 30,
    wins: 19,
    losses: 6,
    draws: 5,
    winRatePct: 71.7,
    objectiveSuccessPct: 63.3,
    averageMoves: 61.4,
    blunders: 2,
  },
];

export const SAMPLE_BENCHMARK_GAMES: BenchmarkGameRecord[] = [
  {
    id: "game_sf1650_01",
    opponent: "Stockfish 19 (Tier 1)",
    opponentElo: 1650,
    openingName: "Sicilian Defense: Najdorf Variation",
    eco: "B90",
    result: "1-0",
    machiavelliColor: "white",
    objectiveSuccess: true,
    movesCount: 46,
    pgn: `[Event "Machiavelli Benchmark Tournament"]
[Site "Machiavelli Arena"]
[Date "2026.11.14"]
[Round "1"]
[White "Machiavelli Core (Stockfish 19 + Planner)"]
[Black "Stockfish 19 (1650 Elo)"]
[Result "1-0"]
[ECO "B90"]
[Opening "Sicilian, Najdorf"]
[Objective "Grand Machiavelli Promotion"]
[ObjectiveResult "Completed"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3 e5 7. Nb3 Be6 8. Qd2 Nbd7 9. O-O-O Be7 10. f3 h5 11. Kb1 Rc8 12. Be2 b5 13. Nd5 Nxd5 14. exd5 Bf5 15. Bd3 Bxd3 16. Qxd3 Bg5 17. Bf2 O-O 18. h4 Bh6 19. g4 hxg4 20. fxg4 Bf4 21. g5 Rc4 22. Nd2 Bxd2 23. Rxd2 Qa5 24. Re2 Rfc8 25. g6 fxg6 26. Qxg6 Nf8 27. Qxd6 Ra4 28. a3 b4 29. Rxe5 bxa3 30. b3 a2+ 31. Ka1 Qc3# 1-0`,
    date: "2026-11-14",
  },
  {
    id: "game_sf1950_01",
    opponent: "Stockfish 19 (Tier 2)",
    opponentElo: 1950,
    openingName: "Ruy Lopez: Berlin Defense",
    eco: "C65",
    result: "1-0",
    machiavelliColor: "white",
    objectiveSuccess: true,
    movesCount: 58,
    pgn: `[Event "Machiavelli Benchmark Tournament"]
[Site "Machiavelli Arena"]
[Date "2026.11.14"]
[Round "2"]
[White "Machiavelli Core (Stockfish 19 + Planner)"]
[Black "Stockfish 19 (1950 Elo)"]
[Result "1-0"]
[ECO "C65"]
[Opening "Ruy Lopez, Berlin Defense"]
[Objective "Grand Machiavelli Promotion"]
[ObjectiveResult "Completed"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. d3 Bc5 5. c3 O-O 6. O-O d6 7. Nbd2 a6 8. Ba4 Ba7 9. h3 Ne7 10. Re1 Ng6 11. Nf1 c6 12. Ng3 d5 13. exd5 Nxd5 14. Nxe5 Nxe5 15. Rxe5 Bxf2+ 16. Kxf2 Qf6+ 17. Qf3 Qxe5 18. Bd2 Qf6 19. Qxf6 Nxf6 20. d4 Re8 21. Bc2 Be6 22. b3 b5 23. Bg5 Nd5 24. Bd2 Rad8 25. Ne4 Bf5 26. Re1 Bxe4 27. Bxe4 f6 28. c4 bxc4 29. bxc4 Ne7 30. Bc3 f5 31. Bf3 Kf7 32. Rb1 Rb8 33. Rd1 Red8 34. Ba5 Rd7 35. Rd2 g6 36. Bc3 Rbd8 37. g3 h5 38. h4 Ke6 39. Re2+ Kf7 40. Rd2 Ke6 41. Re2+ Kf7 42. Rd2 1-0`,
    date: "2026-11-14",
  },
];
