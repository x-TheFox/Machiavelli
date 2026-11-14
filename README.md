# Machiavelli ♟️

> **Goal-Conditioned Chess Intelligence Engine & Adversarial Mission Planner**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Next.js 15](https://img.shields.io/badge/next.js-15-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![Stockfish 19](https://img.shields.io/badge/stockfish-19-orange.svg)](https://stockfishchess.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Machiavelli is an adversarial, goal-conditioned chess intelligence engine capable of pursuing complex, non-standard mission objectives (e.g., *"Sacrifice all original pieces, promote every surviving pawn to a knight, and deliver checkmate using the promoted knights"*) while defending against and checkmating calibrated Stockfish opponents.

---

## 🏛️ System Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │          Next.js 15 Web Dashboard           │
                  │   (ChessboardView, ObjectivePanel, etc.)     │
                  └──────────────────────┬───────────────────────┘
                                         │ WebSocket / REST
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │            FastAPI Server Layer              │
                  │   (/api/games, /ws/game/{session_id})        │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │             GameSession Manager              │
                  │  (Authoritative State, Fallbacks, Database)  │
                  └──────┬───────────────────────┬───────────────┘
                         │                       │
           ┌─────────────┴─────────────┐  ┌──────┴───────────────┐
           │   Goal & Feasibility      │  │  Adversarial Search  │
           ├───────────────────────────┤  ├──────────────────────┤
           │ • Goal Interpreter (LLM)  │  │ • Lexicographical    │
           │ • AST Deterministic Parser│  │   Multi-Attribute    │
           │ • Piece Tracker (UUIDs)   │  │   Vector Evaluator   │
           │ • Invariant Proof Engine  │  │ • Alpha-Beta Search  │
           └───────────────────────────┘  │ • Hybrid Candidate   │
                                          │   Generator          │
                                          └──────────┬───────────┘
                                                     │
                                                     ▼
                                          ┌──────────────────────┐
                                          │ Stockfish UCI Client │
                                          │ (MultiPV, Crash Rec) │
                                          └──────────────────────┘
```

---

## ⚡ Core Capabilities

1. **Natural Language & AST Goal Interpretation**
   - Translates natural language strategic constraints into structured milestone DAGs.
   - Dual-mode processing: LLM client (with automatic Gemini/OpenAI failover chaining) + deterministic AST parser for certified benchmark objectives.

2. **Persistent Piece Tracking & Sacrifice Verification**
   - Assigns immutable UUID identifiers to all starting back-rank pieces and original pawns.
   - Differentiates intentional sacrifice gambits from tactical blunders or equal exchanges.
   - Preserves promotion lineages (originating pawn, turn, square, promoted piece type).

3. **Proof-Based Mathematical Feasibility Engine**
   - Strictly distinguishes between search failures and mathematical impossibility.
   - Enforces invariant proofs (e.g. piece preservation parity, square color constraints, mate-in-N limits).

4. **Lexicographical Multi-Attribute Evaluator**
   - Evaluates positions using a strict priority vector:
     $$\mathbf{V}(s) = \langle V_{\text{safety}}, V_{\text{feasibility}}, V_{\text{milestone}}, V_{\text{positional}} \rangle$$
   - Eliminates arbitrary evaluation hard-caps while maintaining tactical King safety.

5. **Iterative Deepening Search & Hybrid Candidate Generation**
   - Integrates Stockfish MultiPV tactical lines with goal-directed candidate moves (pawn pushes, sacrificial incursions, clearance maneuvers).
   - Dynamic transposition tables and quiescence search for move stability.

6. **Dual-Mode Impossibility Handling**
   - **Interactive Mode**: Emits real-time WebSocket prompts offering constraint relaxation, conventional conversion, or resignation.
   - **Benchmark Mode**: Generates cryptographic SHA256 invariant evidence digests and automatically converts to conventional play for tournament scoring.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- Stockfish UCI engine installed (`brew install stockfish` on macOS)

### 2. Environment Configuration
Clone the repository and copy the environment template:
```bash
git clone https://github.com/x-TheFox/Machiavelli.git
cd Machiavelli
cp .env.example .env
```
Edit `.env` to configure your Stockfish path and API credentials:
```env
STOCKFISH_PATH=/opt/homebrew/bin/stockfish
OPENAI_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
OPENAI_API_KEY=your_gemini_or_openai_api_key_here
OPENAI_MODEL=gemini-2.5-flash
```

### 3. Backend Setup
```bash
# Navigate to backend and install dependencies
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the FastAPI server
python run_server.py
```
Backend API will be running at `http://localhost:8000` (API Docs at `http://localhost:8000/docs`).

### 4. Frontend Setup
```bash
# In a separate terminal
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to access the interactive web dashboard.

---

## 🧪 Testing & Benchmarks

### Running the Test Suite
Machiavelli includes 77 unit and integration tests covering UCI communication, piece tracking, feasibility proofs, search heuristics, and server concurrency:
```bash
pytest backend/tests -v
```

### Running Tournament Benchmarks
Execute calibrated matches against 1650, 1950, and 2250 Elo Stockfish configurations across 15 standard ECO openings:
```bash
python backend/run_tournament.py --games 30 --depth 6 --output reports/benchmark
```

---

## 📂 Repository Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI routes & WebSocket endpoints
│   │   ├── benchmark/       # Tournament runner, openings, and baseline comparison
│   │   ├── chess_engine/    # UCI client, piece tracker, planner, evaluator, search
│   │   ├── core/            # Settings, SQLAlchemy database models, persistence
│   │   └── main.py          # Application entrypoint
│   ├── tests/               # 77 unit & integration tests
│   ├── run_server.py        # Server runner CLI
│   └── run_tournament.py    # Benchmark runner CLI
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js App Router (dashboard & benchmark pages)
│   │   ├── components/      # ChessboardView, ObjectivePanel, EnginePanel, etc.
│   │   └── lib/             # WebSocket client, TypeScript types, data
│   ├── package.json
│   └── tailwind.config.ts
├── reports/                 # Benchmark tournament PGNs, CSVs, and markdown reports
├── .env.example             # Safe environment variable template
└── .gitignore               # Strict secret and build artifact exclusion rules
```

---

## 🛡️ Security
This repository strictly enforces gitignore rules prohibiting `.env` files, API keys, SQLite databases, and bytecode artifacts from being tracked. See `.env.example` for safe configuration guidelines.

---

## 📜 License
Licensed under the [MIT License](LICENSE).
