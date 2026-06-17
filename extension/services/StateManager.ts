/**
 * StateManager - Manages extension state with persistence.
 */

const SERVER_URL = "https://openbox.getu.ai";

const STORAGE_KEY = "devBrowserActiveState";
const CONFIG_KEY = "devBrowserConfig";

export interface ExtensionState {
  isActive: boolean;
}

export interface ExtensionConfig {
  /** Unique client ID (auto-generated on first enable) */
  clientId: string;
}

const DEFAULT_CONFIG: ExtensionConfig = {
  clientId: "",
};

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
  getServerUrl(): string {
    return SERVER_URL;
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
