import type {
  GetStateMessage,
  SetStateMessage,
  CheckAuthMessage,
  StateResponse,
  AuthStatusResponse,
} from "../../utils/types";

const toggle = document.getElementById("active-toggle") as HTMLInputElement;
const statusText = document.getElementById("status-text") as HTMLSpanElement;
const connectionStatus = document.getElementById("connection-status") as HTMLParagraphElement;
const authStatusEl = document.getElementById("auth-status") as HTMLParagraphElement;
const clientIdInfo = document.getElementById("client-id-info") as HTMLParagraphElement;

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

  if (state.username) {
    authStatusEl.textContent = `Logged in: ${state.username}`;
    authStatusEl.className = "auth-status logged-in";
  } else if (state.authError) {
    authStatusEl.textContent = AUTH_ERROR_MESSAGES[state.authError] || state.authError;
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

// Check auth on popup open
chrome.runtime.sendMessage<CheckAuthMessage, AuthStatusResponse>({ type: "checkAuth" }, (response) => {
  if (response) {
    if (response.isLoggedIn) {
      authStatusEl.textContent = response.username ? `Logged in: ${response.username}` : "Logged in";
      authStatusEl.className = "auth-status logged-in";
    } else {
      authStatusEl.textContent = "Not logged in";
      authStatusEl.className = "auth-status error";
    }
  }
});

// Load initial state
refreshState();

// Poll for state updates
const pollInterval = setInterval(refreshState, 1000);

window.addEventListener("unload", () => {
  clearInterval(pollInterval);
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
