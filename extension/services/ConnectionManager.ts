/**
 * ConnectionManager - Manages WebSocket connection to OpenBox backend relay.
 *
 * Auth flow: read refresh_token cookie → POST /api/auth/extension-auth → get ticket → connect WS.
 * Sends client_id with the WS connection so the server can track active clients
 * and prevent connection competition between multiple browsers.
 */

import type { Logger } from "../utils/logger";
import type { ExtensionCommandMessage, ExtensionResponseMessage } from "../utils/types";
import { StateManager } from "./StateManager";

const RECONNECT_INTERVAL = 3000;
const RECONNECT_INTERVAL_AUTH_ERROR = 10000;
/** Close code 4001 = replaced by another client. Do NOT reconnect. */
const CLOSE_CODE_REPLACED = 4001;
/** Close code 4003 = authentication failed */
const CLOSE_CODE_AUTH_FAILED = 4003;
/** Close code 4004 = no running container */
const CLOSE_CODE_NO_CONTAINER = 4004;

export interface ConnectionManagerDeps {
  logger: Logger;
  onMessage: (message: ExtensionCommandMessage) => Promise<unknown>;
  onDisconnect: () => void;
}

export class ConnectionManager {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldMaintain = false;
  private replaced = false;
  private connecting = false;
  private _authError: string | null = null;
  private _username: string | null = null;
  private logger: Logger;
  private onMessage: (message: ExtensionCommandMessage) => Promise<unknown>;
  private onDisconnect: () => void;
  private stateManager = new StateManager();

  constructor(deps: ConnectionManagerDeps) {
    this.logger = deps.logger;
    this.onMessage = deps.onMessage;
    this.onDisconnect = deps.onDisconnect;
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  isReplaced(): boolean {
    return this.replaced;
  }

  getAuthError(): string | null {
    return this._authError;
  }

  getUsername(): string | null {
    return this._username;
  }

  async checkConnection(): Promise<boolean> {
    return this.isConnected();
  }

  send(message: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(message));
      } catch (error) {
        console.debug("Error sending message:", error);
      }
    }
  }

  startMaintaining(): void {
    if (this.replaced) return;
    this.shouldMaintain = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.scheduleConnect();
  }

  private scheduleConnect(): void {
    if (!this.shouldMaintain || this.replaced) return;
    if (this.isConnected() || this.connecting) return;

    this.tryConnect()
      .catch(() => {})
      .finally(() => {
        if (this.shouldMaintain && !this.replaced && !this.isConnected()) {
          const interval = this._authError ? RECONNECT_INTERVAL_AUTH_ERROR : RECONNECT_INTERVAL;
          this.reconnectTimer = setTimeout(() => this.scheduleConnect(), interval);
        }
      });
  }

  stopMaintaining(): void {
    this.shouldMaintain = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  disconnect(): void {
    this.stopMaintaining();
    this.replaced = false;
    this.connecting = false;
    this._authError = null;
    this._username = null;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.onDisconnect();
  }

  async ensureConnected(): Promise<void> {
    if (this.isConnected()) return;

    await this.tryConnect();

    if (!this.isConnected()) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      await this.tryConnect();
    }

    if (!this.isConnected()) {
      throw new Error("Could not connect to relay server");
    }
  }

  /** Check if refresh_token cookie exists for the server domain. */
  async checkCookie(): Promise<boolean> {
    const serverUrl = this.stateManager.getServerUrl();
    const cookie = await chrome.cookies.get({
      url: `${serverUrl}/api/auth`,
      name: "refresh_token",
    });
    return !!cookie;
  }

  private async tryConnect(): Promise<void> {
    if (this.isConnected()) return;
    if (this.replaced) return;
    if (this.connecting) return;

    this.connecting = true;

    try {
      await this.doConnect();
    } finally {
      this.connecting = false;
    }
  }

  private async doConnect(): Promise<void> {
    const serverUrl = this.stateManager.getServerUrl();
    const config = await this.stateManager.getConfig();

    // Step 1: Read refresh_token cookie
    const cookie = await chrome.cookies.get({
      url: `${serverUrl}/api/auth`,
      name: "refresh_token",
    });

    if (!cookie) {
      this._authError = "not_logged_in";
      this.logger.debug("No refresh_token cookie found");
      return;
    }

    // Step 2: Exchange refresh_token for a one-time ticket
    let ticket: string;
    try {
      const resp = await fetch(`${serverUrl}/api/auth/extension-auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: cookie.value }),
        signal: AbortSignal.timeout(5000),
      });

      if (!resp.ok) {
        this._authError = resp.status === 401 ? "token_expired" : "auth_failed";
        this.logger.debug("Extension auth failed:", resp.status);
        return;
      }

      const data = await resp.json();
      ticket = data.ticket;
      this._username = data.user?.username || null;
      this._authError = null;
    } catch {
      this._authError = "server_unreachable";
      this.logger.debug("Server unreachable for extension auth");
      return;
    }

    // Step 3: Connect WebSocket with ticket
    const wsBase = serverUrl.replace(/^http/, "ws");
    let relayUrl = `${wsBase}/ws/dev-browser/auto?ticket=${encodeURIComponent(ticket)}`;
    if (config.clientId) {
      relayUrl += `&client_id=${encodeURIComponent(config.clientId)}`;
    }

    this.logger.debug("Connecting to relay:", relayUrl);
    const socket = new WebSocket(relayUrl);

    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error("Connection timeout"));
      }, 5000);

      socket.onopen = () => {
        clearTimeout(timeout);
        resolve();
      };

      socket.onerror = () => {
        clearTimeout(timeout);
        reject(new Error("WebSocket connection failed"));
      };

      socket.onclose = (event) => {
        clearTimeout(timeout);
        if (event.code === CLOSE_CODE_NO_CONTAINER) {
          this._authError = "no_container";
        }
        reject(new Error(`WebSocket closed: ${event.reason || event.code}`));
      };
    });

    this.ws = socket;
    this.replaced = false;
    this._authError = null;
    this.setupSocketHandlers(socket);
    this.logger.log("Connected to relay server");
  }

  private setupSocketHandlers(socket: WebSocket): void {
    socket.onmessage = async (event: MessageEvent) => {
      let message: ExtensionCommandMessage;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        this.logger.debug("Error parsing message:", error);
        this.send({
          error: { code: -32700, message: "Parse error" },
        });
        return;
      }

      const response: ExtensionResponseMessage = { id: message.id };
      try {
        response.result = await this.onMessage(message);
      } catch (error) {
        this.logger.debug("Error handling command:", error);
        response.error = (error as Error).message;
      }
      this.send(response);
    };

    socket.onclose = (event: CloseEvent) => {
      this.logger.debug("Connection closed:", event.code, event.reason);
      this.ws = null;
      this.onDisconnect();

      if (event.code === CLOSE_CODE_REPLACED) {
        this.logger.log(`Replaced by another client: ${event.reason}. Not reconnecting.`);
        this.replaced = true;
        this.stopMaintaining();
        return;
      }

      if (event.code === CLOSE_CODE_AUTH_FAILED) {
        this._authError = "auth_failed";
      } else if (event.code === CLOSE_CODE_NO_CONTAINER) {
        this._authError = "no_container";
      }

      if (this.shouldMaintain) {
        const interval = this._authError ? RECONNECT_INTERVAL_AUTH_ERROR : RECONNECT_INTERVAL;
        this.reconnectTimer = setTimeout(() => this.scheduleConnect(), interval);
      }
    };

    socket.onerror = (event: Event) => {
      this.logger.debug("WebSocket error:", event);
    };
  }
}
