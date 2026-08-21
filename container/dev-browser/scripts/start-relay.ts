/**
 * Start the dev-browser relay server.
 *
 * Supports three modes:
 *   - "extension": bridge CDP to the user's Chrome via the extension
 *   - "local": point clients straight at a local Chrome's native CDP endpoint
 *   - "auto" (default): prefer the extension when connected, fall back to local
 *
 * Configuration via env vars and/or CLI flags (flags win over env):
 *   DEV_BROWSER_MODE        / --mode          extension | local | auto
 *   DEV_BROWSER_PORT        / --port          relay HTTP/WS port (default 9222)
 *   DEV_BROWSER_CHROME_PORT / --chrome-port   local Chrome CDP port (default 9333)
 *   DEV_BROWSER_CHROME_HOST / --chrome-host   local Chrome host (default 127.0.0.1)
 *   HOST                    / --host          relay bind host (default 127.0.0.1)
 */

import { serveRelay } from "@/relay.js";

type Mode = "extension" | "local" | "auto";

/** Minimal `--key value` / `--key=value` / `--flag` parser. */
function parseArgs(argv: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (!arg || !arg.startsWith("--")) continue;
    const body = arg.slice(2);
    const eq = body.indexOf("=");
    if (eq >= 0) {
      out[body.slice(0, eq)] = body.slice(eq + 1);
      continue;
    }
    const next = argv[i + 1];
    if (next && !next.startsWith("--")) {
      out[body] = next;
      i++;
    } else {
      out[body] = "true";
    }
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));

const mode = (args.mode ?? process.env.DEV_BROWSER_MODE ?? "auto") as Mode;
const port = parseInt(args.port ?? process.env.DEV_BROWSER_PORT ?? process.env.PORT ?? "9222", 10);
const host = args.host ?? process.env.HOST ?? "127.0.0.1";
const chromePort = parseInt(
  args["chrome-port"] ?? process.env.DEV_BROWSER_CHROME_PORT ?? "9333",
  10
);
const chromeHost = args["chrome-host"] ?? process.env.DEV_BROWSER_CHROME_HOST ?? "127.0.0.1";

async function main() {
  if (mode !== "extension" && mode !== "local" && mode !== "auto") {
    throw new Error(`Invalid mode "${mode}" (expected extension | local | auto)`);
  }

  console.log(
    `[start-relay] resolving mode=${mode} relay=${host}:${port} chrome=${chromeHost}:${chromePort}`
  );

  const server = await serveRelay({ mode, port, host, chromePort, chromeHost });

  console.log(`[start-relay] advertised wsEndpoint: ${server.wsEndpoint}`);

  // Handle shutdown
  const shutdown = async () => {
    console.log("\nShutting down relay server...");
    await server.stop();
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error("Failed to start relay server:", err);
  process.exit(1);
});
