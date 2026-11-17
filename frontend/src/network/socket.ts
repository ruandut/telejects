/**
 * The events websocket: the only place in the app that opens a WebSocket.
 *
 * The server holds it to the API's rules: a JWT as the first message (a browser can't put it on
 * the handshake), membership of the company, and a permission check for every topic subscribed
 * to, again before every message. It sends either the data that changed, built with the API's own
 * serializers ("data"), or just that something changed ("changed"), and the page refetches.
 *
 * The server closes the socket when its token expires (4401); we reconnect with a fresh one and
 * subscribe again. 4403 means we aren't in the company, so we stop. After a reconnect anything may
 * have been missed, so listeners get a "reconnected" message and refetch.
 */
import { useAuth } from "@/stores/auth";

import { refreshAccessToken } from "./auth";

const UNAUTHENTICATED = 4401;
const NOT_A_MEMBER = 4403;
const MAX_WAIT = 15_000;

export type LiveMessage =
  | { type: "data"; topic: string; subject: number | null; data: unknown }
  | { type: "changed"; topic: string; subject: number | null }
  | { type: "refused"; topic: string; subject: number | null }
  | { type: "reconnected" };

type Listener = (message: LiveMessage) => void;
type ServerMessage =
  | { type: "ready" }
  | { type: "subscribed" | "refused" | "changed"; topic: string; subject: number | null }
  | { type: "data"; topic: string; subject: number | null; data: unknown };

const keyOf = (topic: string, subject: number | null) => `${topic}:${subject ?? ""}`;

class LiveSocket {
  private realmId: number | null = null;
  private socket: WebSocket | null = null;
  private ready = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private attempts = 0;
  private connectedBefore = false;
  private listeners = new Map<string, Set<Listener>>();

  /** Work in this company (null: none). Called by RealmGate. */
  setRealm(realmId: number | null) {
    if (realmId === this.realmId) return;
    this.close();
    this.realmId = realmId;
    this.connectedBefore = false;
    if (realmId !== null && this.listeners.size) void this.open();
  }

  /** Listen to one topic (and subject, such as a run's id). Returns the function that stops. */
  subscribe(topic: string, subject: number | null, listener: Listener): () => void {
    const key = keyOf(topic, subject);
    let set = this.listeners.get(key);
    if (!set) {
      set = new Set();
      this.listeners.set(key, set);
      if (this.ready) this.send({ type: "subscribe", topic, subject });
    }
    set.add(listener);
    if (!this.socket && this.realmId !== null) void this.open();
    return () => {
      set.delete(listener);
      if (set.size) return;
      this.listeners.delete(key);
      if (this.ready) this.send({ type: "unsubscribe", topic, subject });
    };
  }

  private send(message: object) {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(message));
  }

  private emit(key: string, message: LiveMessage) {
    this.listeners.get(key)?.forEach((listener) => listener(message));
  }

  private close() {
    clearTimeout(this.timer);
    const socket = this.socket;
    this.socket = null;
    this.ready = false;
    socket?.close();
  }

  private retry() {
    if (this.realmId === null) return;
    this.attempts += 1;
    this.timer = setTimeout(() => void this.open(), Math.min(500 * 2 ** this.attempts, MAX_WAIT));
  }

  private async open(fresh = false) {
    const realmId = this.realmId;
    if (realmId === null) return;
    const token = fresh ? await refreshAccessToken() : useAuth.getState().access;
    if (realmId !== this.realmId) return;
    if (!token) {
      // Signed out, or the session is over: the next API call sends the tab to sign in.
      if (!fresh && useAuth.getState().refresh) void this.open(true);
      return;
    }
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${window.location.host}/ws/events/`);
    this.socket = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "auth", token, realm: realmId }));
    ws.onmessage = (event) => {
      let message: ServerMessage;
      try {
        message = JSON.parse(String(event.data)) as ServerMessage;
      } catch {
        return;
      }
      if (message.type === "ready") {
        this.ready = true;
        this.attempts = 0;
        for (const key of this.listeners.keys()) {
          const [topic, subject] = key.split(":");
          this.send({ type: "subscribe", topic, subject: subject ? Number(subject) : null });
        }
        if (this.connectedBefore) {
          for (const key of this.listeners.keys()) this.emit(key, { type: "reconnected" });
        }
        this.connectedBefore = true;
      } else if (message.type !== "subscribed") {
        this.emit(keyOf(message.topic, message.subject), message as LiveMessage);
      }
    };
    ws.onclose = (event) => {
      if (this.socket !== ws) return;
      this.socket = null;
      this.ready = false;
      if (event.code === NOT_A_MEMBER) return;
      if (event.code === UNAUTHENTICATED && this.attempts < 3) {
        this.attempts += 1;
        void this.open(true);
      } else this.retry();
    };
  }
}

export const liveSocket = new LiveSocket();
