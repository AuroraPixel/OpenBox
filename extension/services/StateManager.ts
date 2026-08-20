/**
 * StateManager - Manages extension state with persistence.
 */

/**
 * Default OpenBox origin. Points at the local dev frontend, which proxies both
 * /api and /ws through to the backend — and, importantly, is the origin the
 * refresh_token cookie is set on when you sign in, which is what the extension
 * reads to authenticate. Override it from the popup's Advanced section when
 * running against a deployed instance.
 */
export const DEFAULT_SERVER_URL = "http://localhost:3000";

const STORAGE_KEY = "devBrowserActiveState";
const CONFIG_KEY = "devBrowserConfig";

export interface ExtensionState {
  isActive: boolean;
}

export interface ExtensionConfig {
  /** Unique client ID (auto-generated on first enable) */
  clientId: string;
  /** OpenBox origin, no trailing slash. Empty means DEFAULT_SERVER_URL. */
  serverUrl: string;
}

const DEFAULT_CONFIG: ExtensionConfig = {
  clientId: "",
  serverUrl: "",
};

/**
 * Coerce user input into an origin the rest of the extension can rely on:
 * scheme + host + optional port, no trailing slash, no path.
 * Returns null when the input can't be read as an http(s) URL.
 */
export function normalizeServerUrl(input: string): string | null {
  const trimmed = (input || "").trim();
  if (!trimmed) return null;

  // Only supply a scheme when the input genuinely lacks one — "localhost:3000"
  // is a natural thing to type. Blindly prefixing would turn "ftp://host" into
  // "http://ftp://host", which URL happily parses as host "ftp": a wrong-scheme
  // input would come back looking valid instead of being rejected.
  const scheme = /^([a-z][a-z0-9+.\-]*):\/\//i.exec(trimmed)?.[1]?.toLowerCase();
  if (scheme && scheme !== "http" && scheme !== "https") return null;
  // A scheme-like prefix with no "//" (e.g. "javascript:alert(1)") is not an
  // origin either; "localhost:3000" is distinguishable by its all-digit port.
  if (!scheme && /^[a-z][a-z0-9+.\-]*:/i.test(trimmed) && !/^[^:]+:\d+(\/|$)/.test(trimmed)) {
    return null;
  }

  try {
    const url = new URL(scheme ? trimmed : `http://${trimmed}`);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (!url.hostname) return null;
    return url.origin;
  } catch {
    return null;
  }
}

function generateClientId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export class StateManager {
  async getServerUrl(): Promise<string> {
    const config = await this.getConfig();
    return normalizeServerUrl(config.serverUrl) ?? DEFAULT_SERVER_URL;
  }

  /**
   * Persist a new origin. Pass an empty string to fall back to the default.
   * Returns the normalized value actually stored, or null when the input was
   * not a usable http(s) URL (in which case nothing is written).
   */
  async setServerUrl(input: string): Promise<string | null> {
    const config = await this.getConfig();
    if (!input.trim()) {
      config.serverUrl = "";
      await this.setConfig(config);
      return DEFAULT_SERVER_URL;
    }
    const normalized = normalizeServerUrl(input);
    if (!normalized) return null;
    config.serverUrl = normalized;
    await this.setConfig(config);
    return normalized;
  }

  async getState(): Promise<ExtensionState> {
    const result = await chrome.storage.local.get(STORAGE_KEY);
    const state = result[STORAGE_KEY] as ExtensionState | undefined;
    return state ?? { isActive: false };
  }

  async setState(state: ExtensionState): Promise<void> {
    await chrome.storage.local.set({ [STORAGE_KEY]: state });
  }

  async getConfig(): Promise<ExtensionConfig> {
    const result = await chrome.storage.local.get(CONFIG_KEY);
    const config = result[CONFIG_KEY] as ExtensionConfig | undefined;
    return config ?? { ...DEFAULT_CONFIG };
  }

  async setConfig(config: ExtensionConfig): Promise<void> {
    await chrome.storage.local.set({ [CONFIG_KEY]: config });
  }

  /** Ensure clientId exists, generate if missing. Called on first enable. */
  async ensureClientId(): Promise<string> {
    const config = await this.getConfig();
    if (!config.clientId) {
      config.clientId = generateClientId();
      await this.setConfig(config);
    }
    return config.clientId;
  }
}
