// API request/response types - shared between client and server

export interface ServeOptions {
  port?: number;
  headless?: boolean;
  cdpPort?: number;
  /** Directory to store persistent browser profiles (cookies, localStorage, etc.) */
  profileDir?: string;
}

export interface ViewportSize {
  width: number;
  height: number;
}

export interface GetPageRequest {
  name: string;
  /** Optional viewport size for new pages */
  viewport?: ViewportSize;
}

export interface GetPageResponse {
  wsEndpoint: string;
  name: string;
  targetId: string; // CDP target ID for reliable page matching
}

export interface ListPagesResponse {
  pages: string[];
}

export interface ServerInfoResponse {
  /** CDP WebSocket endpoint Playwright connects to. Null in local mode when Chrome is unreachable. */
  wsEndpoint: string | null;
  /** Effective mode after "auto" resolution. */
  mode?: "extension" | "local";
  /** Mode originally requested via options (may still be "auto"). */
  configuredMode?: "extension" | "local" | "auto";
  /** Whether a Chrome extension is currently connected (extension/auto modes). */
  extensionConnected?: boolean;
  /** Local mode: whether Chrome's CDP endpoint was reachable. */
  chromeAvailable?: boolean;
  /** Human-readable error, set when chromeAvailable is false. */
  error?: string;
}
