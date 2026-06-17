import { defineConfig } from "wxt";

export default defineConfig({
  manifest: {
    version: "1.3.0",
    name: "OpenAgent Browser",
    description: "Connect your browser to OpenAgent for automated browser control",
    permissions: ["debugger", "tabGroups", "storage", "alarms", "cookies"],
    host_permissions: ["<all_urls>"],
    icons: {
      16: "icons/icon-16.png",
      32: "icons/icon-32.png",
      48: "icons/icon-48.png",
      128: "icons/icon-128.png",
    },
  },
});
