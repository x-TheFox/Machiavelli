import chess
import pytest

from backend.app.chess_engine.piece_tracker import PieceTracker, PIECE_VALUES


def test_piece_tracker_initialization():
    tracker = PieceTracker()

    # White pieces
    white_orig = tracker.get_original_major_minor_pieces(chess.WHITE)
    assert len(white_orig) == 7, "Should have exactly 7 major/minor pieces (King strictly excluded)"
    types = {p.piece_type for p in white_orig}
    assert chess.KING not in types, "King must never be in original major/minor pieces"
    assert types == {chess.ROOK, chess.KNIGHT, chess.BISHOP, chess.QUEEN}

    # White pawns
    white_pawns = tracker.get_original_pawns(chess.WHITE)
    assert len(white_pawns) == 8
    surviving = tracker.get_surviving_pawns(chess.WHITE)
    assert len(surviving) == 8

    # Black pieces
    black_orig = tracker.get_original_major_minor_pieces(chess.BLACK)
    assert len(black_orig) == 7
    black_pawns = tracker.get_original_pawns(chess.BLACK)
    assert len(black_pawns) == 8


def test_king_strictly_excluded_from_sacrifice():
    tracker = PieceTracker()
    board = chess.Board()

    # Find White King
    king_piece = tracker.get_piece_at(chess.E1)
    assert king_piece is not None
    assert king_piece.is_king is True

    # Attempting to register sacrifice intent for King must raise ValueError
    with pytest.raises(ValueError, match="King is strictly excluded"):
        tracker.register_sacrifice_intent(
            piece_id=king_piece.piece_id,
            milestone_id="m1_sacrifice",
            move=chess.Move.from_uci("e1e2"),
            board=board,
        )


def test_move_execution_and_castling():
    board = chess.Board()
    tracker = PieceTracker()

    # 1. e2e4
    move1 = chess.Move.from_uci("e2e4")
    tracker.apply_move(move1, board, is_our_move=True)
    board.push(move1)

    pawn = tracker.get_piece_at(chess.E4)
    assert pawn is not None
    assert pawn.piece_type == chess.PAWN
    assert tracker.get_piece_at(chess.E2) is None

    # Set up castling position: FEN with king and rooks ready
    fen_castling = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
    b_castling = chess.Board(fen_castling)
    t_castling = PieceTracker(fen_castling)

    # Kingside castling: e1g1
    castle_ks = chess.Move.from_uci("e1g1")
    t_castling.apply_move(castle_ks, b_castling, is_our_move=True)
    b_castling.push(castle_ks)

    king = t_castling.get_piece_at(chess.G1)
    assert king is not None and king.is_king
    rook = t_castling.get_piece_at(chess.F1)
    assert rook is not None and rook.piece_type == chess.ROOK
    assert t_castling.get_piece_at(chess.H1) is None


def test_en_passant_capture():
    fen = "rnbqkbnr/pppp1ppp/8/4pP2/8/8/PPPPP1PP/RNBQKBNR w KQkq e6 0 3"
    # Black just played e7e5, White can capture f5xe6 en passant
    board = chess.Board(fen)
    tracker = PieceTracker(fen)

    f5_pawn = tracker.get_piece_at(chess.F5)
    e5_pawn = tracker.get_piece_at(chess.E5)
    assert f5_pawn is not None
    assert e5_pawn is not None

    ep_move = chess.Move.from_uci("f5e6")
    tracker.apply_move(ep_move, board, is_our_move=True)
    board.push(ep_move)

    assert tracker.get_piece_at(chess.E6) == f5_pawn
    assert tracker.get_piece_at(chess.E5) is None
    assert e5_pawn.is_captured is True


def test_promotion_and_lineage():
    fen = "8/4P3/8/8/8/8/8/4K2k w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)

    pawn = tracker.get_piece_at(chess.E7)
    assert pawn is not None

    # Promote to Knight
    prom_move = chess.Move.from_uci("e7e8n")
    tracker.apply_move(prom_move, board, is_our_move=True)
    board.push(prom_move)

    assert pawn.is_promoted is True
    assert pawn.current_square is None

    promoted_piece = tracker.get_piece_at(chess.E8)
    assert promoted_piece is not None
    assert promoted_piece.piece_type == chess.KNIGHT
    assert promoted_piece.is_promoted is True
    assert promoted_piece.promoted_from_id == pawn.piece_id

    promoted_knights = tracker.get_promoted_pieces(chess.WHITE, chess.KNIGHT)
    assert len(promoted_knights) == 1
    assert promoted_knights[0].piece_id == promoted_piece.piece_id


def test_genuine_sacrifice_vs_blunder_vs_exchange():
    # Setup position where White Queen can be sacrificed or exchanged
    # White: Kh1, Qd1, Nf3. Black: Kh8, Nd4, pawn e7.
    fen = "7k/4p3/8/8/3n4/5N2/8/3Q3K w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    queen = tracker.get_piece_at(chess.D1)
    assert queen is not None

    # Scenario 1: Intentional Queen sacrifice on d4 (capturing nothing or moving to attacked square)
    # White plays Qd3 (quiet move onto d3 where Black knight on d4 attacks it)
    # Pre-move intent registered!
    move_offer = chess.Move.from_uci("d1d3")
    intent = tracker.register_sacrifice_intent(
        piece_id=queen.piece_id,
        milestone_id="m1_sac_queen",
        move=move_offer,
        board=board,
    )
    tracker.apply_move(move_offer, board, is_our_move=True, declared_intent=intent)
    board.push(move_offer)

    # Black accepts: Nxd3
    move_accept = chess.Move.from_uci("d4d3")
    tracker.apply_move(move_accept, board, is_our_move=False)
    board.push(move_accept)

    assert queen.is_captured is True
    sacrifices = tracker.get_confirmed_sacrifices(chess.WHITE)
    assert len(sacrifices) == 1
    assert sacrifices[0].is_genuine is True
    assert sacrifices[0].piece_type == chess.QUEEN
    assert sacrifices[0].material_sacrificed == 9
    assert tracker.is_queen_sacrificed(chess.WHITE) is True


def test_blunder_not_counted_as_sacrifice():
    # Setup position: White Knight on f3 left hanging, Black captures it without White intent
    fen = "7k/8/8/8/3q4/5N2/8/7K w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    knight = tracker.get_piece_at(chess.F3)
    assert knight is not None

    # White makes a quiet king move Kh2 WITHOUT registering sacrifice intent for knight
    move_white = chess.Move.from_uci("h1h2")
    tracker.apply_move(move_white, board, is_our_move=True)
    board.push(move_white)

    # Black captures hanging knight: Qxd4
    move_black = chess.Move.from_uci("d4f3")
    tracker.apply_move(move_black, board, is_our_move=False)
    board.push(move_black)

    assert knight.is_captured is True
    # Must NOT be in confirmed genuine sacrifices
    sacrifices = tracker.get_confirmed_sacrifices(chess.WHITE)
    assert len(sacrifices) == 0, "Unintended piece loss must NOT be counted as genuine sacrifice"


def test_equal_exchange_rejected():
    # Position: White Knight on f3, Black Knight on d4
    fen = "7k/8/8/8/3n4/5N2/8/7K w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    white_knight = tracker.get_piece_at(chess.F3)
    # White captures Black Knight with intent: Nxd4 (capturing 3 points)
    move_white = chess.Move.from_uci("f3d4")
    intent = tracker.register_sacrifice_intent(
        piece_id=white_knight.piece_id,
        milestone_id="m1_sac",
        move=move_white,
        board=board,
    )
    tracker.apply_move(move_white, board, is_our_move=True, declared_intent=intent)
    board.push(move_white)

    # Black plays e.g. pawn or king move, wait, what if Black plays a move that captures back?
    # Let's say Black has pawn on e5 that captures exd4
    # Set up with pawn on e5
    fen2 = "7k/8/8/4p3/3n4/5N2/8/7K w - - 0 1"
    board2 = chess.Board(fen2)
    tracker2 = PieceTracker(fen2)
    tracker2.set_our_color(chess.WHITE)

    wn = tracker2.get_piece_at(chess.F3)
    m_white = chess.Move.from_uci("f3d4")  # captures knight (3 pts)
    intent2 = tracker2.register_sacrifice_intent(
        piece_id=wn.piece_id,
        milestone_id="m1_sac",
        move=m_white,
        board=board2,
    )
    tracker2.apply_move(m_white, board2, is_our_move=True, declared_intent=intent2)
    board2.push(m_white)

    # Black recaptures: exd4
    m_black = chess.Move.from_uci("e5d4")
    tracker2.apply_move(m_black, board2, is_our_move=False)
    board2.push(m_black)

    # Net material loss = 3 (Knight) - 3 (Knight captured) = 0! Equal exchange.
    assert wn.is_captured is True
    sacrifices = tracker2.get_confirmed_sacrifices(chess.WHITE)
    assert len(sacrifices) == 0, "Equal exchange must NOT be accepted as genuine sacrifice"
    all_events = [s for s in tracker2.confirmed_sacrifices if s.color == chess.WHITE]
    assert len(all_events) == 1
    assert all_events[0].is_genuine is False
    assert all_events[0].rejection_reason == "equal_exchange"


def test_declined_sacrifice_clears_intent():
    fen = "7k/8/8/8/3n4/8/8/3Q3K w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    queen = tracker.get_piece_at(chess.D1)
    offer_move = chess.Move.from_uci("d1d3")
    intent = tracker.register_sacrifice_intent(
        piece_id=queen.piece_id,
        milestone_id="m1_sac",
        move=offer_move,
        board=board,
    )
    tracker.apply_move(offer_move, board, is_our_move=True, declared_intent=intent)
    board.push(offer_move)

    # Opponent ignores sacrifice and moves King: h8g8
    decline_move = chess.Move.from_uci("h8g8")
    tracker.apply_move(decline_move, board, is_our_move=False)
    board.push(decline_move)

    assert len(tracker.pending_intents) == 0, "Declined intent must be cleared"
    assert len(tracker.confirmed_sacrifices) == 0
    assert queen.is_captured is False
