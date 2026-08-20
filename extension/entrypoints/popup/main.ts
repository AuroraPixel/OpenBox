import type {
  GetStateMessage,
  SetStateMessage,
  CheckAuthMessage,
  SetServerUrlMessage,
  StateResponse,
  AuthStatusResponse,
  SetServerUrlResponse,
} from "../../utils/types";

const toggle = document.getElementById("active-toggle") as HTMLInputElement;
const statusText = document.getElementById("status-text") as HTMLSpanElement;
const connectionStatus = document.getElementById("connection-status") as HTMLParagraphElement;
const authStatusEl = document.getElementById("auth-status") as HTMLParagraphElement;
const clientIdInfo = document.getElementById("client-id-info") as HTMLParagraphElement;
const serverUrlInput = document.getElementById("server-url") as HTMLInputElement;
const saveServerUrlBtn = document.getElementById("save-server-url") as HTMLButtonElement;
const resetServerUrlBtn = document.getElementById("reset-server-url") as HTMLButtonElement;
const serverUrlStatus = document.getElementById("server-url-status") as HTMLParagraphElement;

/** Suppresses the 1s poll clobbering the field while it's being edited. */
let serverUrlDirty = false;

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  not_logged_in: "Not logged in",
  token_expired: "Login expired, please re-login",
  auth_failed: "Auth failed",
  server_unreachable: "Server unreachable",
  no_container: "No running container",
};

function updateUI(state: StateResponse): void {
  toggle.checked = state.isActive;
  statusText.textContent = state.isActive ? "Active" : "Inactive";

  if (state.clientId) {
    clientIdInfo.textContent = `Client: ${state.clientId.slice(0, 8)}...`;
  }

  // Don't overwrite what the user is typing.
  if (!serverUrlDirty && state.serverUrl && document.activeElement !== serverUrlInput) {
    serverUrlInput.value = state.isDefaultServerUrl ? "" : state.serverUrl;
    serverUrlInput.placeholder = state.isDefaultServerUrl
      ? state.serverUrl
      : "http://localhost:3000";
  }

  // A background script from a previous build won't report serverUrl at all.
  // Surfacing that explicitly beats the misleading "Not logged in" you would
  // otherwise get from it checking a stale origin.
  if (state.serverUrl === undefined) {
    authStatusEl.textContent = "Reload the extension (stale background script)";
    authStatusEl.className = "auth-status error";
  } else if (state.username) {
    authStatusEl.textContent = `Logged in: ${state.username}`;
    authStatusEl.className = "auth-status logged-in";
  } else if (state.authError) {
    const base = AUTH_ERROR_MESSAGES[state.authError] || state.authError;
    // Naming the origin turns "why am I not logged in?" into an answer.
    const needsOrigin = state.authError === "not_logged_in" || state.authError === "server_unreachable";
    authStatusEl.textContent = needsOrigin && state.serverUrl ? `${base} @ ${state.serverUrl}` : base;
    authStatusEl.className = "auth-status error";
  }

  if (state.isReplaced) {
    connectionStatus.textContent = "Replaced by another device";
    connectionStatus.className = "connection-status error";
  } else if (state.isActive) {
    if (state.isConnected) {
      connectionStatus.textContent = "Connected to relay";
      connectionStatus.className = "connection-status connected";
    } else if (state.authError) {
      connectionStatus.textContent = AUTH_ERROR_MESSAGES[state.authError] || "Error";
      connectionStatus.className = "connection-status error";
    } else {
      connectionStatus.textContent = "Connecting...";
      connectionStatus.className = "connection-status connecting";
    }
  } else {
    connectionStatus.textContent = "";
    connectionStatus.className = "connection-status";
  }
}

function refreshState(): void {
  chrome.runtime.sendMessage<GetStateMessage, StateResponse>({ type: "getState" }, (response) => {
    if (response) {
      updateUI(response);
    }
  });
}

// Live cookie probe on popup open. Only the positive result is written here —
// failures are left to updateUI, which also knows the origin being checked and
// whether the background script is stale.
chrome.runtime.sendMessage<CheckAuthMessage, AuthStatusResponse>({ type: "checkAuth" }, (response) => {
  if (response?.isLoggedIn) {
    authStatusEl.textContent = response.username ? `Logged in: ${response.username}` : "Logged in";
    authStatusEl.className = "auth-status logged-in";
  }
});

// Load initial state
refreshState();

// Poll for state updates
const pollInterval = setInterval(refreshState, 1000);

window.addEventListener("unload", () => {
  clearInterval(pollInterval);
});

// ── Advanced: server URL ──

function showServerUrlStatus(text: string, kind: "ok" | "error" | ""): void {
  serverUrlStatus.textContent = text;
  serverUrlStatus.className = kind ? `field-status ${kind}` : "field-status";
}

function submitServerUrl(value: string): void {
  saveServerUrlBtn.disabled = true;
  resetServerUrlBtn.disabled = true;
  showServerUrlStatus("Saving...", "");

  chrome.runtime.sendMessage<SetServerUrlMessage, SetServerUrlResponse>(
    { type: "setServerUrl", serverUrl: value },
    (response) => {
      saveServerUrlBtn.disabled = false;
      resetServerUrlBtn.disabled = false;
      if (!response) {
        showServerUrlStatus("Extension not responding", "error");
        return;
      }
      if (!response.ok) {
        serverUrlInput.classList.add("invalid");
        showServerUrlStatus(response.error || "Save failed", "error");
        return;
      }
      serverUrlDirty = false;
      serverUrlInput.classList.remove("invalid");
      showServerUrlStatus(`Saved — ${response.serverUrl}`, "ok");
      refreshState();
    }
  );
}

serverUrlInput.addEventListener("input", () => {
  serverUrlDirty = true;
  serverUrlInput.classList.remove("invalid");
  showServerUrlStatus("", "");
});

serverUrlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitServerUrl(serverUrlInput.value);
});

saveServerUrlBtn.addEventListener("click", () => submitServerUrl(serverUrlInput.value));

resetServerUrlBtn.addEventListener("click", () => {
  serverUrlInput.value = "";
  submitServerUrl("");
});

// Handle toggle
toggle.addEventListener("change", () => {
  const isActive = toggle.checked;

  chrome.runtime.sendMessage<SetStateMessage, StateResponse>(
    { type: "setState", isActive },
    (response) => {
      if (response) {
        updateUI(response);
      }
    }
  );
});
