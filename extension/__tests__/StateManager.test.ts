import { describe, it, expect, beforeEach } from "vitest";
import { fakeBrowser } from "wxt/testing";
import {
  StateManager,
  DEFAULT_SERVER_URL,
  normalizeServerUrl,
} from "../services/StateManager";

describe("StateManager", () => {
  let stateManager: StateManager;

  beforeEach(() => {
    fakeBrowser.reset();
    stateManager = new StateManager();
  });

  describe("getState", () => {
    it("should return default inactive state when no stored state", async () => {
      const state = await stateManager.getState();
      expect(state).toEqual({ isActive: false });
    });

    it("should return stored state when available", async () => {
      await fakeBrowser.storage.local.set({
        devBrowserActiveState: { isActive: true },
      });

      const state = await stateManager.getState();
      expect(state).toEqual({ isActive: true });
    });
  });

  describe("setState", () => {
    it("should persist state to storage", async () => {
      await stateManager.setState({ isActive: true });

      const stored = await fakeBrowser.storage.local.get("devBrowserActiveState");
      expect(stored.devBrowserActiveState).toEqual({ isActive: true });
    });

    it("should update state from active to inactive", async () => {
      await stateManager.setState({ isActive: true });
      await stateManager.setState({ isActive: false });

      const state = await stateManager.getState();
      expect(state).toEqual({ isActive: false });
    });
  });

  describe("normalizeServerUrl", () => {
    it("keeps a well-formed origin as-is", () => {
      expect(normalizeServerUrl("http://localhost:3000")).toBe("http://localhost:3000");
      expect(normalizeServerUrl("https://openbox.example.com")).toBe("https://openbox.example.com");
    });

    it("adds a scheme to a bare host:port", () => {
      expect(normalizeServerUrl("localhost:3000")).toBe("http://localhost:3000");
      expect(normalizeServerUrl("127.0.0.1:8080")).toBe("http://127.0.0.1:8080");
    });

    it("strips trailing slashes and any path", () => {
      expect(normalizeServerUrl("http://localhost:3000/")).toBe("http://localhost:3000");
      expect(normalizeServerUrl("http://localhost:3000/api/auth")).toBe("http://localhost:3000");
    });

    it("tolerates surrounding whitespace", () => {
      expect(normalizeServerUrl("  http://localhost:3000  ")).toBe("http://localhost:3000");
    });

    it("rejects empty and non-http schemes", () => {
      expect(normalizeServerUrl("")).toBeNull();
      expect(normalizeServerUrl("   ")).toBeNull();
      expect(normalizeServerUrl("ftp://example.com")).toBeNull();
      expect(normalizeServerUrl("javascript:alert(1)")).toBeNull();
    });
  });

  describe("server URL config", () => {
    it("falls back to the default when nothing is stored", async () => {
      expect(await stateManager.getServerUrl()).toBe(DEFAULT_SERVER_URL);
    });

    it("persists and returns a normalized override", async () => {
      const saved = await stateManager.setServerUrl("localhost:9000/");
      expect(saved).toBe("http://localhost:9000");
      expect(await stateManager.getServerUrl()).toBe("http://localhost:9000");
    });

    it("returns null and stores nothing for an invalid URL", async () => {
      await stateManager.setServerUrl("http://good.example.com");
      expect(await stateManager.setServerUrl("not a url at all ::: ")).toBeNull();
      // previous value survives a rejected write
      expect(await stateManager.getServerUrl()).toBe("http://good.example.com");
    });

    it("resets to the default on empty input", async () => {
      await stateManager.setServerUrl("http://other.example.com");
      expect(await stateManager.setServerUrl("")).toBe(DEFAULT_SERVER_URL);
      expect(await stateManager.getServerUrl()).toBe(DEFAULT_SERVER_URL);
    });

    it("ignores a stored value that is no longer parseable", async () => {
      await fakeBrowser.storage.local.set({
        devBrowserConfig: { clientId: "abc", serverUrl: "garbage://x" },
      });
      expect(await stateManager.getServerUrl()).toBe(DEFAULT_SERVER_URL);
    });
  });
});
