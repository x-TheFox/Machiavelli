import { WebSocketServerEvent } from "./types";

type EventCallback<T = any> = (data: T) => void;

class MachiavelliWebSocketClient {
  private socket: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectDelay = 10000;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private listeners: Map<string, Set<EventCallback>> = new Map();
  private isExplicitlyClosed = false;
  private sessionId: string = "main_session";
  private lastSeq: number = 0;

  constructor() {
    const envWs = process.env.NEXT_PUBLIC_WS_URL;
    if (envWs) {
      this.url = envWs;
    } else if (typeof window !== "undefined") {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.hostname || "localhost";
      this.url = `${protocol}//${host}:8000/ws/game/${this.sessionId}`;
    } else {
      this.url = "ws://localhost:8000/ws/game/main_session";
    }
  }

  public setSessionId(id: string) {
    this.sessionId = id;
    if (typeof window !== "undefined") {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.hostname || "localhost";
      this.url = `${protocol}//${host}:8000/ws/game/${this.sessionId}`;
    }
  }

  public connect(customUrl?: string) {
    if (typeof window === "undefined") return;
    if (customUrl) this.url = customUrl;

    this.isExplicitlyClosed = false;
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      this.socket = new WebSocket(this.url);

      this.socket.onopen = () => {
        this.reconnectAttempts = 0;
        this.notify("CONNECTION_STATE", { connected: true, sessionId: this.sessionId });
        // Request synchronization
        this.send("SYNC", { last_seq: this.lastSeq });
      };

      this.socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          const type = (parsed.type || parsed.event || "").toUpperCase();
          if (parsed.seq !== undefined && parsed.seq > this.lastSeq) {
            this.lastSeq = parsed.seq;
          }
          const payload = parsed.payload !== undefined ? parsed.payload : parsed.data !== undefined ? parsed.data : parsed;
          
          if (type) {
            this.notify(type, payload);
          }
        } catch (err) {
          console.warn("[Machiavelli WS] Failed to parse message:", event.data, err);
        }
      };

      this.socket.onerror = (err) => {
        console.warn("[Machiavelli WS] Connection error:", err);
      };

      this.socket.onclose = () => {
        this.notify("CONNECTION_STATE", { connected: false, sessionId: this.sessionId });
        if (!this.isExplicitlyClosed) {
          this.scheduleReconnect();
        }
      };
    } catch (e) {
      console.warn("[Machiavelli WS] Init exception:", e);
      this.notify("CONNECTION_STATE", { connected: false, sessionId: this.sessionId });
      this.scheduleReconnect();
    }
  }

  public disconnect() {
    this.isExplicitlyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.notify("CONNECTION_STATE", { connected: false, sessionId: this.sessionId });
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  public send(type: string, payload: Record<string, unknown> = {}) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type, payload }));
    } else {
      console.warn("[Machiavelli WS] Cannot send message, socket not open:", type, payload);
    }
  }

  // Typed Command Actions matching FastAPI WebSocket
  public sendMove(move: string) {
    this.send("PLAYER_MOVE", { move });
  }

  public sendGoal(goalText: string, goalId?: string) {
    this.send("START_GAME", { goal: goalText, goal_id: goalId });
  }

  public startNewGame(options?: {
    objectiveText?: string;
    goalId?: string;
    playerColor?: "white" | "black";
    initialFen?: string;
    mode?: "interactive" | "benchmark";
    elo?: number;
  }) {
    this.send("START_GAME", {
      goal: options?.objectiveText,
      goal_id: options?.goalId,
      color: options?.playerColor || "white",
      start_fen: options?.initialFen,
      mode: options?.mode || "interactive",
      elo: options?.elo || 1950,
    });
  }

  public requestEngineStep() {
    this.send("STEP", {});
  }

  public pauseGame() {
    this.send("PAUSE", {});
  }

  public resumeGame() {
    this.send("RESUME", {});
  }

  public resetGame(startFen?: string) {
    this.send("RESET", { start_fen: startFen });
  }

  public resignGame() {
    this.send("FALLBACK_CHOICE", { choice: "resign" });
  }

  public sendDualModeDecision(
    decision: "RELAX_CONSTRAINT" | "CONVENTIONAL_WIN" | "RESIGN",
    revisedObjective?: string
  ) {
    const choiceMapping: Record<string, string> = {
      RELAX_CONSTRAINT: "relax_constraint",
      CONVENTIONAL_WIN: "conventional_win",
      RESIGN: "resign",
    };
    const choice = choiceMapping[decision] || decision.toLowerCase();
    this.send("FALLBACK_CHOICE", {
      choice,
      params: revisedObjective ? { revised_goal: revisedObjective } : undefined,
    });
  }

  // Event Subscription
  public on(event: string, callback: EventCallback): () => void {
    const upper = event.toUpperCase();
    if (!this.listeners.has(upper)) {
      this.listeners.set(upper, new Set());
    }
    const set = this.listeners.get(upper)!;
    set.add(callback);

    return () => {
      set.delete(callback);
    };
  }

  public off(event: string, callback: EventCallback) {
    const set = this.listeners.get(event.toUpperCase());
    if (set) {
      set.delete(callback);
    }
  }

  public notify(event: string, data: unknown) {
    const set = this.listeners.get(event.toUpperCase());
    if (set) {
      set.forEach((cb) => {
        try {
          cb(data);
        } catch (e) {
          console.error(`[Machiavelli WS] Listener error on event ${event}:`, e);
        }
      });
    }
  }

  public getSessionId(): string {
    return this.sessionId;
  }
}

export const wsClient = new MachiavelliWebSocketClient();
