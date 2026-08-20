/**
 * Types for extension-relay communication
 */

export type ConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error";

export type TabState = "connecting" | "connected" | "error";

export interface TabInfo {
  sessionId?: string;
  targetId?: string;
  state: TabState;
  errorText?: string;
}

export interface ExtensionState {
  tabs: Map<number, TabInfo>;
  connectionState: ConnectionState;
  currentTabId?: number;
  errorText?: string;
}

// Messages from relay to extension
export interface ExtensionCommandMessage {
  id: number;
  method: "forwardCDPCommand";
  params: {
    method: string;
    params?: Record<string, unknown>;
    sessionId?: string;
  };
}

// Messages from extension to relay (responses)
export interface ExtensionResponseMessage {
  id: number;
  result?: unknown;
  error?: string;
}

// Messages from extension to relay (events)
export interface ExtensionEventMessage {
  method: "forwardCDPEvent";
  params: {
    method: string;
    params?: Record<string, unknown>;
    sessionId?: string;
  };
}

// Log message from extension to relay
export interface ExtensionLogMessage {
  method: "log";
  params: {
    level: string;
    args: string[];
  };
}

export type ExtensionMessage =
  | ExtensionResponseMessage
  | ExtensionEventMessage
  | ExtensionLogMessage;

// Chrome debugger target info
export interface TargetInfo {
  targetId: string;
  type: string;
  title: string;
  url: string;
  attached?: boolean;
}

// Popup <-> Background messaging
export interface GetStateMessage {
  type: "getState";
}

export interface SetStateMessage {
  type: "setState";
  isActive: boolean;
}

export interface CheckAuthMessage {
  type: "checkAuth";
}

export interface SetServerUrlMessage {
  type: "setServerUrl";
  /** Empty string resets to the built-in default. */
  serverUrl: string;
}

export interface StateResponse {
  isActive: boolean;
  isConnected: boolean;
  isReplaced?: boolean;
  authError?: string | null;
  username?: string | null;
  clientId?: string;
  /** Origin currently in use (resolved, never empty). */
  serverUrl?: string;
  /** True when serverUrl is the built-in default rather than a saved override. */
  isDefaultServerUrl?: boolean;
}

export interface AuthStatusResponse {
  isLoggedIn: boolean;
  username?: string | null;
}

export interface SetServerUrlResponse {
  ok: boolean;
  /** Normalized origin now in effect (present when ok). */
  serverUrl?: string;
  error?: string;
}

export type PopupMessage =
  | GetStateMessage
  | SetStateMessage
  | CheckAuthMessage
  | SetServerUrlMessage;
