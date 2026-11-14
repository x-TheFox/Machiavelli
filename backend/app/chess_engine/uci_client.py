"""Stockfish UCI Client.

Manages an asynchronous Stockfish UCI subprocess, handling:
- Subprocess lifecycle (start, quit, health check, restart, crash recovery)
- UCI configuration options (Threads, Hash, MultiPV, UCI_LimitStrength, UCI_Elo, etc.)
- Position setups (startpos, FEN, moves history)
- Asynchronous analysis with MultiPV candidate move parsing, centipawn/mate scores, and PV extraction
- Graceful stop and timeout handling
"""

import asyncio
import logging
import os
import shutil
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class UCIError(Exception):
    """Base exception for UCI engine errors."""
    pass


class UCITimeoutError(UCIError):
    """Raised when engine fails to respond within the expected timeout."""
    pass


class UCICrashError(UCIError):
    """Raised when engine process crashes and cannot be recovered."""
    pass


class UCIScore(BaseModel):
    """Represents a score from Stockfish (perspective of the side to move)."""
    cp: Optional[int] = None
    mate: Optional[int] = None
    lowerbound: bool = False
    upperbound: bool = False
    wdl: Optional[Tuple[int, int, int]] = None

    def to_cp(self, mate_score: int = 10000) -> int:
        """Convert score to centipawns.

        Mate scores are mapped to large values scaled by distance to mate.
        """
        if self.cp is not None:
            return self.cp
        if self.mate is not None:
            if self.mate > 0:
                return mate_score - (self.mate * 10)
            elif self.mate < 0:
                return -mate_score - (self.mate * 10)
            return 0
        return 0

    def score_for_white(self, is_white_turn: bool, mate_score: int = 10000) -> int:
        """Get score from White's perspective."""
        val = self.to_cp(mate_score)
        return val if is_white_turn else -val


class CandidateMove(BaseModel):
    """Analysis data for a single candidate move line (MultiPV)."""
    multipv: int = 1
    move: str
    san: Optional[str] = None
    score: UCIScore = Field(default_factory=UCIScore)
    depth: int = 0
    seldepth: int = 0
    nodes: int = 0
    time_ms: int = 0
    nps: int = 0
    pv: List[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Comprehensive result of an engine analysis run."""
    best_move: Optional[str] = None
    ponder_move: Optional[str] = None
    candidates: List[CandidateMove] = Field(default_factory=list)
    depth_reached: int = 0
    nodes_evaluated: int = 0
    time_ms: int = 0
    raw_lines: List[str] = Field(default_factory=list)

    @property
    def top_candidate(self) -> Optional[CandidateMove]:
        """Returns the primary (multipv 1) candidate move if available."""
        for cand in self.candidates:
            if cand.multipv == 1:
                return cand
        return self.candidates[0] if self.candidates else None


class StockfishUCIClient:
    """Asynchronous UCI process manager for Stockfish."""

    def __init__(
        self,
        stockfish_path: Optional[str] = None,
        threads: Optional[int] = None,
        hash_size_mb: Optional[int] = None,
        default_timeout: float = 30.0,
    ):
        self.stockfish_path = stockfish_path or settings.STOCKFISH_PATH
        self.threads = threads or settings.STOCKFISH_THREADS
        self.hash_size_mb = hash_size_mb or settings.STOCKFISH_HASH
        self.default_timeout = default_timeout

        self._process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._options_cache: Dict[str, Any] = {}
        if self.threads > 0:
            self._options_cache["Threads"] = self.threads
        if self.hash_size_mb > 0:
            self._options_cache["Hash"] = self.hash_size_mb
        self._active_multipv: int = 1
        self._is_started: bool = False

    @property
    def is_alive(self) -> bool:
        """Checks if the subprocess is active and running."""
        return self._process is not None and self._process.returncode is None

    @property
    def is_running(self) -> bool:
        """Alias for is_alive."""
        return self.is_alive

    async def start(self) -> None:
        """Starts the Stockfish engine process and establishes UCI handshake."""
        async with self._lock:
            await self._start_process()

    async def _start_process(self) -> None:
        if self.is_alive:
            return

        resolved_path = shutil.which(self.stockfish_path) or self.stockfish_path
        if not os.path.exists(resolved_path):
            raise UCIError(f"Stockfish binary not found at: {resolved_path}")

        logger.info(f"Starting Stockfish UCI process: {resolved_path}")
        try:
            self._process = await asyncio.create_subprocess_exec(
                resolved_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            raise UCICrashError(f"Failed to spawn Stockfish process: {e}") from e

        # Handshake: 'uci' -> wait for 'uciok'
        await self._send_raw("uci")
        uciok_received = False
        while True:
            line = await self._read_line(timeout=5.0)
            if not line:
                break
            if line.strip() == "uciok":
                uciok_received = True
                break
        if not uciok_received:
            await self._force_kill()
            raise UCIError("Failed to receive 'uciok' from Stockfish")

        # Handshake: 'isready' -> wait for 'readyok'
        await self._send_raw("isready")
        readyok_received = False
        while True:
            line = await self._read_line(timeout=5.0)
            if not line:
                break
            if line.strip() == "readyok":
                readyok_received = True
                break
        if not readyok_received:
            await self._force_kill()
            raise UCIError("Failed to receive 'readyok' from Stockfish")

        # Apply/restore options from options cache
        for opt_name, opt_val in list(self._options_cache.items()):
            await self._set_option_internal(opt_name, opt_val)

        self._is_started = True
        logger.info("Stockfish UCI handshake completed successfully")

    async def _send_raw(self, cmd: str) -> None:
        if not self.is_alive or self._process.stdin is None:
            raise UCICrashError("Stockfish process is not running")
        line = f"{cmd.strip()}\n"
        try:
            self._process.stdin.write(line.encode("utf-8"))
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            raise UCICrashError(f"Pipe broken while sending command '{cmd}': {e}") from e

    async def _read_line(self, timeout: Optional[float] = None) -> str:
        if not self.is_alive or self._process.stdout is None:
            raise UCICrashError("Stockfish process is not running")
        to = timeout or self.default_timeout
        try:
            raw_line = await asyncio.wait_for(self._process.stdout.readline(), timeout=to)
            if not raw_line:
                # EOF reached
                raise UCICrashError("Stockfish process closed stdout stream unexpectedly (EOF)")
            return raw_line.decode("utf-8", errors="replace")
        except asyncio.TimeoutError as e:
            raise UCITimeoutError(f"Stockfish read timed out after {to}s") from e

    async def _force_kill(self) -> None:
        if self._process is not None:
            try:
                self._process.kill()
                await self._process.wait()
            except Exception:
                pass
            finally:
                self._process = None

    async def restart(self) -> None:
        """Kills any existing process and launches a fresh Stockfish engine."""
        async with self._lock:
            logger.warning("Restarting Stockfish UCI process...")
            await self._force_kill()
            await self._start_process()

    async def close(self) -> None:
        """Gracefully shuts down Stockfish engine process."""
        async with self._lock:
            if not self.is_alive:
                self._process = None
                return
            try:
                if self._process.stdin:
                    self._process.stdin.write(b"quit\n")
                    await self._process.stdin.drain()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except Exception:
                await self._force_kill()
            finally:
                self._process = None
                self._is_started = False
                logger.info("Stockfish UCI process closed")

    async def __aenter__(self) -> "StockfishUCIClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def set_option(self, name: str, value: Any) -> None:
        """Sets a UCI option on Stockfish and confirms with readyok."""
        async with self._lock:
            await self._ensure_alive()
            await self._set_option_internal(name, value)

    async def _set_option_internal(self, name: str, value: Any) -> None:
        val_str: str
        if isinstance(value, bool):
            val_str = "true" if value else "false"
        else:
            val_str = str(value)

        self._options_cache[name] = value
        if name.lower() == "multipv":
            try:
                self._active_multipv = int(value)
            except (ValueError, TypeError):
                pass

        await self._send_raw(f"setoption name {name} value {val_str}")
        await self._send_raw("isready")
        while True:
            line = await self._read_line(timeout=5.0)
            if line.strip() == "readyok":
                break

    async def set_options(self, options: Dict[str, Any]) -> None:
        """Sets multiple UCI options at once."""
        async with self._lock:
            await self._ensure_alive()
            for name, val in options.items():
                await self._set_option_internal(name, val)

    async def configure_elo(self, elo: Optional[int] = None) -> None:
        """Configures UCI_LimitStrength and UCI_Elo for calibrated difficulty tiers.

        If elo is None, standard full-strength Stockfish is enabled.
        Stockfish 19 UCI_Elo range: 1320 to 3190.
        """
        async with self._lock:
            await self._ensure_alive()
            if elo is None:
                await self._set_option_internal("UCI_LimitStrength", False)
            else:
                clamped_elo = max(1320, min(3190, elo))
                await self._set_option_internal("UCI_LimitStrength", True)
                await self._set_option_internal("UCI_Elo", clamped_elo)

    async def position(
        self,
        fen: Optional[str] = None,
        moves: Optional[Sequence[str]] = None,
    ) -> None:
        """Sets the board position via UCI command."""
        async with self._lock:
            await self._ensure_alive()
            await self._position_internal(fen, moves)

    async def _position_internal(
        self,
        fen: Optional[Any] = None,
        moves: Optional[Sequence[str]] = None,
    ) -> None:
        fen_str = fen.fen() if hasattr(fen, "fen") else (str(fen) if fen else None)
        if fen_str and fen_str != "startpos":
            cmd = f"position fen {fen_str}"
        else:
            cmd = "position startpos"

        if moves:
            cmd += f" moves {' '.join(moves)}"

        await self._send_raw(cmd)

    async def stop(self) -> None:
        """Sends 'stop' command to interrupt an active search."""
        async with self._lock:
            if self.is_alive:
                try:
                    await self._send_raw("stop")
                except Exception:
                    pass

    async def go(
        self,
        depth: Optional[int] = None,
        movetime_ms: Optional[int] = None,
        nodes: Optional[int] = None,
        multipv: Optional[int] = None,
        searchmoves: Optional[Sequence[str]] = None,
        timeout: Optional[float] = None,
    ) -> AnalysisResult:
        """Executes 'go' search command and parses candidate moves and evaluation."""
        async with self._lock:
            return await self._execute_go_with_retry(
                depth=depth,
                movetime_ms=movetime_ms,
                nodes=nodes,
                multipv=multipv,
                searchmoves=searchmoves,
                timeout=timeout,
            )

    async def analyze(
        self,
        fen: Optional[str] = None,
        moves: Optional[Sequence[str]] = None,
        depth: Optional[int] = None,
        movetime_ms: Optional[int] = None,
        nodes: Optional[int] = None,
        multipv: Optional[int] = None,
        searchmoves: Optional[Sequence[str]] = None,
        timeout: Optional[float] = None,
    ) -> AnalysisResult:
        """Convenience method: sets position then executes go analysis."""
        async with self._lock:
            await self._ensure_alive()
            await self._position_internal(fen, moves)
            return await self._execute_go_with_retry(
                depth=depth,
                movetime_ms=movetime_ms,
                nodes=nodes,
                multipv=multipv,
                searchmoves=searchmoves,
                timeout=timeout,
            )

    async def _ensure_alive(self) -> None:
        if not self.is_alive:
            await self._start_process()

    async def _execute_go_with_retry(
        self,
        depth: Optional[int] = None,
        movetime_ms: Optional[int] = None,
        nodes: Optional[int] = None,
        multipv: Optional[int] = None,
        searchmoves: Optional[Sequence[str]] = None,
        timeout: Optional[float] = None,
    ) -> AnalysisResult:
        try:
            await self._ensure_alive()
            return await self._execute_go(
                depth=depth,
                movetime_ms=movetime_ms,
                nodes=nodes,
                multipv=multipv,
                searchmoves=searchmoves,
                timeout=timeout,
            )
        except (UCICrashError, BrokenPipeError, ConnectionResetError) as e:
            logger.warning(f"UCI crash detected during search ({e}), attempting recovery restart...")
            await self._force_kill()
            await self._start_process()
            # Retry once after restart
            return await self._execute_go(
                depth=depth,
                movetime_ms=movetime_ms,
                nodes=nodes,
                multipv=multipv,
                searchmoves=searchmoves,
                timeout=timeout,
            )

    async def _execute_go(
        self,
        depth: Optional[int] = None,
        movetime_ms: Optional[int] = None,
        nodes: Optional[int] = None,
        multipv: Optional[int] = None,
        searchmoves: Optional[Sequence[str]] = None,
        timeout: Optional[float] = None,
    ) -> AnalysisResult:
        # MultiPV adjustment if requested
        target_multipv = multipv or self._active_multipv
        if target_multipv != self._active_multipv:
            await self._set_option_internal("MultiPV", target_multipv)

        cmd_parts = ["go"]
        if searchmoves:
            cmd_parts.extend(["searchmoves", *searchmoves])
        if depth is not None:
            cmd_parts.extend(["depth", str(depth)])
        if movetime_ms is not None:
            cmd_parts.extend(["movetime", str(movetime_ms)])
        if nodes is not None:
            cmd_parts.extend(["nodes", str(nodes)])

        if len(cmd_parts) == 1:
            # Fallback to default depth if nothing specified
            cmd_parts.extend(["depth", str(settings.DEFAULT_SEARCH_DEPTH)])

        cmd = " ".join(cmd_parts)
        await self._send_raw(cmd)

        # Calculate read timeout: movetime + buffer or default_timeout
        effective_timeout = timeout
        if effective_timeout is None:
            if movetime_ms is not None:
                effective_timeout = (movetime_ms / 1000.0) + 5.0
            else:
                effective_timeout = self.default_timeout

        candidates_map: Dict[int, CandidateMove] = {}
        raw_lines: List[str] = []
        best_move: Optional[str] = None
        ponder_move: Optional[str] = None
        max_depth = 0
        total_nodes = 0
        total_time = 0

        while True:
            try:
                line = await self._read_line(timeout=effective_timeout)
            except UCITimeoutError:
                # Search timed out without bestmove: try sending stop
                logger.warning(f"Search timed out ({effective_timeout}s), sending 'stop'")
                try:
                    await self._send_raw("stop")
                    line = await self._read_line(timeout=3.0)
                except Exception:
                    await self._force_kill()
                    raise UCITimeoutError("Engine unresponsive after stop command")

            raw_lines.append(line.strip())
            stripped = line.strip()

            if stripped.startswith("info "):
                parsed_cand = self._parse_info_line(stripped)
                if parsed_cand:
                    candidates_map[parsed_cand.multipv] = parsed_cand
                    if parsed_cand.depth > max_depth:
                        max_depth = parsed_cand.depth
                    if parsed_cand.nodes > total_nodes:
                        total_nodes = parsed_cand.nodes
                    if parsed_cand.time_ms > total_time:
                        total_time = parsed_cand.time_ms

            elif stripped.startswith("bestmove "):
                parts = stripped.split()
                if len(parts) >= 2 and parts[1] != "(none)":
                    best_move = parts[1]
                if len(parts) >= 4 and parts[2] == "ponder":
                    ponder_move = parts[3]
                break

        # Sort candidates by multipv rank (1, 2, ...)
        sorted_candidates = [candidates_map[k] for k in sorted(candidates_map.keys())]

        # If best_move found but no candidate registered (e.g. depth 0 mate/repetition), create default candidate
        if best_move and not sorted_candidates:
            sorted_candidates.append(
                CandidateMove(
                    multipv=1,
                    move=best_move,
                    score=UCIScore(),
                    depth=max_depth,
                    pv=[best_move],
                )
            )

        return AnalysisResult(
            best_move=best_move,
            ponder_move=ponder_move,
            candidates=sorted_candidates,
            depth_reached=max_depth,
            nodes_evaluated=total_nodes,
            time_ms=total_time,
            raw_lines=raw_lines,
        )

    def _parse_info_line(self, line: str) -> Optional[CandidateMove]:
        tokens = line.split()
        if len(tokens) < 2:
            return None

        depth = 0
        seldepth = 0
        multipv = 1
        nodes = 0
        nps = 0
        time_ms = 0
        score = UCIScore()
        pv_moves: List[str] = []

        i = 1
        n = len(tokens)
        while i < n:
            tok = tokens[i]
            if tok == "depth" and i + 1 < n:
                try:
                    depth = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
            elif tok == "seldepth" and i + 1 < n:
                try:
                    seldepth = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
            elif tok == "multipv" and i + 1 < n:
                try:
                    multipv = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
            elif tok == "score" and i + 2 < n:
                score_type = tokens[i + 1]
                try:
                    score_val = int(tokens[i + 2])
                    if score_type == "cp":
                        score.cp = score_val
                    elif score_type == "mate":
                        score.mate = score_val
                except ValueError:
                    pass
                i += 3
                # Check for lowerbound / upperbound
                if i < n and tokens[i] == "lowerbound":
                    score.lowerbound = True
                    i += 1
                elif i < n and tokens[i] == "upperbound":
                    score.upperbound = True
                    i += 1
            elif tok == "nodes" and i + 1 < n:
                try:
                    nodes = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
            elif tok == "nps" and i + 1 < n:
                try:
                    nps = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
            elif tok == "time" and i + 1 < n:
                try:
                    time_ms = int(tokens[i + 1])
                except ValueError:
                    pass
                i += 2
            elif tok == "wdl" and i + 3 < n:
                try:
                    score.wdl = (int(tokens[i + 1]), int(tokens[i + 2]), int(tokens[i + 3]))
                except ValueError:
                    pass
                i += 4
            elif tok == "pv":
                pv_moves = tokens[i + 1:]
                break
            else:
                i += 1

        if not pv_moves:
            return None

        primary_move = pv_moves[0]
        return CandidateMove(
            multipv=multipv,
            move=primary_move,
            score=score,
            depth=depth,
            seldepth=seldepth,
            nodes=nodes,
            time_ms=time_ms,
            nps=nps,
            pv=pv_moves,
        )
