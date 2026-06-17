/**
 * dev-browser Chrome Extension Background Script
 *
 * This extension connects to the dev-browser relay server and allows
 * Playwright automation of the user's existing browser tabs.
 */

import { createLogger } from "../utils/logger";
import { TabManager } from "../services/TabManager";
import { ConnectionManager } from "../services/ConnectionManager";
import { CDPRouter } from "../services/CDPRouter";
import { StateManager } from "../services/StateManager";
import type { PopupMessage, StateResponse, AuthStatusResponse } from "../utils/types";

export default defineBackground(() => {
  let connectionManager: ConnectionManager;

  const logger = createLogger((msg) => connectionManager?.send(msg));
  const stateManager = new StateManager();

  const tabManager = new TabManager({
    logger,
    sendMessage: (msg) => connectionManager.send(msg),
  });

  const cdpRouter = new CDPRouter({
    logger,
    tabManager,
  });

  connectionManager = new ConnectionManager({
    logger,
    onMessage: (msg) => cdpRouter.handleCommand(msg),
    onDisconnect: () => tabManager.detachAll(),
  });

  // Keep-alive
  const KEEPALIVE_ALARM = "keepAlive";
  const KEEPALIVE_INTERVAL_MINUTES = 0.25;

  let keepAlivePingTimer: ReturnType<typeof setInterval> | null = null;

  function startKeepAlivePing(): void {
    if (keepAlivePingTimer) return;
    keepAlivePingTimer = setInterval(() => {
      chrome.runtime.getPlatformInfo().catch(() => {});
    }, 20000);
  }

  function stopKeepAlivePing(): void {
    if (keepAlivePingTimer) {
      clearInterval(keepAlivePingTimer);
      keepAlivePingTimer = null;
    }
  }

  function updateBadge(isActive: boolean): void {
    chrome.action.setBadgeText({ text: isActive ? "ON" : "" });
    chrome.action.setBadgeBackgroundColor({ color: "#4CAF50" });
  }

  async function handleStateChange(isActive: boolean): Promise<void> {
    await stateManager.setState({ isActive });
    if (isActive) {
      await stateManager.ensureClientId();
      chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: KEEPALIVE_INTERVAL_MINUTES });
      startKeepAlivePing();
      connectionManager.startMaintaining();
    } else {
      chrome.alarms.clear(KEEPALIVE_ALARM);
      stopKeepAlivePing();
      connectionManager.disconnect();
    }
    updateBadge(isActive);
  }

  function onDebuggerEvent(
    source: chrome.debugger.DebuggerSession,
    method: string,
    params: unknown
  ): void {
    cdpRouter.handleDebuggerEvent(source, method, params, (msg) => connectionManager.send(msg));
  }

  function onDebuggerDetach(
    source: chrome.debugger.Debuggee,
    reason: `${chrome.debugger.DetachReason}`
  ): void {
    const tabId = source.tabId;
    if (!tabId) return;

    logger.debug(`Debugger detached for tab ${tabId}: ${reason}`);
    tabManager.handleDebuggerDetach(tabId);
  }

  chrome.runtime.onMessage.addListener(
    (
      message: PopupMessage,
      _sender: chrome.runtime.MessageSender,
      sendResponse: (response: StateResponse | AuthStatusResponse) => void
    ) => {
      if (message.type === "getState") {
        (async () => {
          const state = await stateManager.getState();
          const config = await stateManager.getConfig();
          const isConnected = await connectionManager.checkConnection();
          sendResponse({
            isActive: state.isActive,
            isConnected,
            isReplaced: connectionManager.isReplaced(),
            authError: connectionManager.getAuthError(),
            username: connectionManager.getUsername(),
            clientId: config.clientId || undefined,
          });
        })();
        return true;
      }

      if (message.type === "setState") {
        (async () => {
          await handleStateChange(message.isActive);
          const state = await stateManager.getState();
          const config = await stateManager.getConfig();
          const isConnected = await connectionManager.checkConnection();
          sendResponse({
            isActive: state.isActive,
            isConnected,
            isReplaced: connectionManager.isReplaced(),
            authError: connectionManager.getAuthError(),
            username: connectionManager.getUsername(),
            clientId: config.clientId || undefined,
          });
        })();
        return true;
      }

      if (message.type === "checkAuth") {
        (async () => {
          const isLoggedIn = await connectionManager.checkCookie();
          sendResponse({
            isLoggedIn,
            username: connectionManager.getUsername(),
          });
        })();
        return true;
      }

      return false;
    }
  );

  chrome.tabs.onRemoved.addListener((tabId) => {
    if (tabManager.has(tabId)) {
      logger.debug("Tab closed:", tabId);
      tabManager.detach(tabId, false);
    }
  });

  chrome.debugger.onEvent.addListener(onDebuggerEvent);
  chrome.debugger.onDetach.addListener(onDebuggerDetach);

  chrome.debugger.getTargets().then((targets) => {
    const attached = targets.filter((t) => t.tabId && t.attached);
    if (attached.length > 0) {
      logger.log(`Detaching ${attached.length} stale debugger connections`);
      for (const target of attached) {
        chrome.debugger.detach({ tabId: target.tabId }).catch(() => {});
      }
    }
  });

  logger.log("Extension initialized");

  stateManager.getState().then((state) => {
    updateBadge(state.isActive);
    if (state.isActive) {
      chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: KEEPALIVE_INTERVAL_MINUTES });
      startKeepAlivePing();
      connectionManager.startMaintaining();
    }
  });

  chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (alarm.name === KEEPALIVE_ALARM) {
      const state = await stateManager.getState();

      if (state.isActive && !connectionManager.isReplaced()) {
        const isConnected = connectionManager.isConnected();

        if (!isConnected) {
          logger.debug("Keep-alive: Connection lost, restarting...");
          connectionManager.startMaintaining();
        }
      }
    }
  });
});
