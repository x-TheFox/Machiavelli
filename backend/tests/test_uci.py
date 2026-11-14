"""Unit tests for Stockfish UCI client."""

import asyncio
import pytest
import chess

from backend.app.chess_engine.uci_client import (
    StockfishUCIClient,
    AnalysisResult,
    CandidateMove,
    UCIScore,
    UCIError,
)
from backend.app.core.config import settings


@pytest.mark.asyncio
async def test_uci_client_lifecycle():
    """Verify startup, handshake, and shutdown of Stockfish UCI process."""
    client = StockfishUCIClient()
    assert not client.is_alive
    await client.start()
    assert client.is_alive

    # Shutdown
    await client.close()
    assert not client.is_alive


@pytest.mark.asyncio
async def test_uci_client_context_manager():
    """Verify async context manager behavior."""
    async with StockfishUCIClient() as client:
        assert client.is_alive
    assert not client.is_alive


@pytest.mark.asyncio
async def test_uci_options_configuration():
    """Verify setoption calls for Threads, Hash, and Elo limiting."""
    async with StockfishUCIClient() as client:
        await client.set_option("Threads", 1)
        await client.set_option("Hash", 32)
        assert client._options_cache["Threads"] == 1
        assert client._options_cache["Hash"] == 32

        # Configure calibrated Elo
        await client.configure_elo(1650)
        assert client._options_cache["UCI_LimitStrength"] is True
        assert client._options_cache["UCI_Elo"] == 1650

        # Reset to full strength
        await client.configure_elo(None)
        assert client._options_cache["UCI_LimitStrength"] is False


@pytest.mark.asyncio
async def test_standard_analysis():
    """Verify basic analysis returns bestmove, depth, and candidates."""
    async with StockfishUCIClient() as client:
        result = await client.analyze(fen="startpos", depth=5)
        assert isinstance(result, AnalysisResult)
        assert result.best_move is not None
        # Verify best_move is legal in startpos
        board = chess.Board()
        move = chess.Move.from_uci(result.best_move)
        assert move in board.legal_moves

        assert result.depth_reached >= 5
        assert len(result.candidates) >= 1
        top = result.top_candidate
        assert top is not None
        assert top.multipv == 1
        assert top.move == result.best_move
        assert len(top.pv) >= 1
        assert top.score.cp is not None or top.score.mate is not None


@pytest.mark.asyncio
async def test_multipv_candidate_parsing():
    """Verify MultiPV returns distinct candidates sorted by rank."""
    async with StockfishUCIClient() as client:
        result = await client.analyze(fen="startpos", depth=5, multipv=3)
        assert len(result.candidates) == 3
        ranks = [c.multipv for c in result.candidates]
        assert ranks == [1, 2, 3]

        moves = [c.move for c in result.candidates]
        # MultiPV moves must be distinct
        assert len(set(moves)) == 3
        # All candidate moves must be legal starting moves
        board = chess.Board()
        for m_str in moves:
            assert chess.Move.from_uci(m_str) in board.legal_moves


@pytest.mark.asyncio
async def test_mate_score_detection():
    """Verify mate score parsing in forced mate positions."""
    # Scholar's mate threat: White has Qxf7# (mate 1)
    fen = "r1bqkb1r/pppp1ppp/2n5/4p2Q/2B1n3/8/PPPP1PPP/RNB1K1NR w KQkq - 0 5"
    async with StockfishUCIClient() as client:
        result = await client.analyze(fen=fen, depth=5)
        assert result.best_move == "h5f7"
        top = result.top_candidate
        assert top is not None
        assert top.score.mate == 1
        assert top.score.to_cp() >= 9000


@pytest.mark.asyncio
async def test_checkmated_position():
    """Verify terminal checkmate position returns None best_move or (none)."""
    # Scholar's mate delivered
    fen = "r1bqkb1r/pppp1Qpp/2n5/4p3/2B1n3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 5"
    async with StockfishUCIClient() as client:
        result = await client.analyze(fen=fen, depth=2)
        assert result.best_move is None


@pytest.mark.asyncio
async def test_uci_stop_command():
    """Verify engine search can be interrupted with stop()."""
    async with StockfishUCIClient() as client:
        # Position and go depth 25 (which would take several seconds without stop)
        await client.position("startpos")
        task = asyncio.create_task(client.go(depth=25))
        await asyncio.sleep(0.1)
        await client.stop()
        result = await task
        assert result is not None
        assert result.best_move is not None


@pytest.mark.asyncio
async def test_crash_recovery_restart():
    """Verify client recovers automatically when subprocess is killed."""
    async with StockfishUCIClient() as client:
        await client.set_option("Threads", 1)
        # Kill the underlying process to simulate a sudden crash
        assert client._process is not None
        client._process.kill()
        await client._process.wait()

        # Next analysis should recover automatically via restart retry
        result = await client.analyze(fen="startpos", depth=4)
        assert client.is_alive
        assert result.best_move is not None
        # Cached options should be preserved after recovery
        assert client._options_cache.get("Threads") == 1
