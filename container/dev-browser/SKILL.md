---
name: dev-browser
description: Browser automation with persistent page state via user's Chrome extension. Use when users ask to navigate websites, fill forms, take screenshots, extract web data, test web apps, or automate browser workflows. Trigger phrases include "go to [url]", "click on", "fill out the form", "take a screenshot", "scrape", "automate", "test the website", "log into", or any browser interaction request.
---

# Dev Browser Skill

Browser automation that controls the user's real Chrome browser through the OpenBox Dev Browser Chrome Extension. Write small, focused scripts to accomplish tasks incrementally.

## Choosing Your Approach

- **Local/source-available sites**: Read the source code first to write selectors directly
- **Unknown page layouts**: Use `getAISnapshot()` to discover elements and `selectSnapshotRef()` to interact with them
- **Visual feedback**: Take screenshots to see what the user sees

## Two browsers, and why it matters

This skill drives one of two browsers. They are not interchangeable:

| Mode | Which browser | Has the user's logins |
|---|---|---|
| `local` | Chrome on this cloud desktop | **No** |
| `extension` | The user's OWN Chrome, via the Dev Browser extension | **Yes** |

`auto` (the default) prefers the user's own browser and **falls back to the cloud
desktop's Chrome whenever the extension is not connected**, so automation keeps working
when the user closes their browser.

Local mode talks to Chrome's native CDP endpoint directly — no extension, no bridging,
fewer hops. Prefer it for anything that does not need the user's identity.

**Check which one you got before doing anything identity-dependent:**

```bash
curl -s http://localhost:9222/ | head -c 300
```

`mode` is the effective mode, `configuredMode` is what was requested. If a task needs a
site the user is logged into and `mode` is `local`, stop and ask the user — either they
connect their own browser, or they accept logging in on the cloud one.

## Setup — there isn't any

**The browser and the relay are already running.** Loading this skill started both and
waited for them; the `<browser_mode>` block at the end of the skill output tells you
which browser you got. Go straight to writing a script.

Do **not** run `npm run start-relay` first. It is not harmless: it kills the running
relay and starts another, costing a wasted step and several seconds, and the relay it
replaces was the one already wired to the browser you were told about.

Only start it by hand if the `<browser_mode>` block reported a failure — and then say
what it reported, rather than retrying blindly:

```bash
cd /opt/openbox/skills/dev-browser && npm run start-relay &
```

**If you need the user's own browser and the extension is not connected**, tell them to:
1. Open the Browser tab in the OpenBox frontend
2. Click "Enable Dev Browser" and follow the setup instructions
3. Configure and activate the Chrome extension

## Writing Scripts

> **Run all scripts from `/opt/openbox/skills/dev-browser/` directory.** The `@/` import alias requires this directory's config.

Execute scripts inline using heredocs:

```bash
cd /opt/openbox/skills/dev-browser && npx tsx <<'EOF'
import { connect, waitForPageLoad } from "@/client.js";

const client = await connect();
// Create page with custom viewport size (optional)
const page = await client.page("example", { viewport: { width: 1920, height: 1080 } });

await page.goto("https://example.com");
await waitForPageLoad(page);

console.log({ title: await page.title(), url: page.url() });
await client.disconnect();
EOF
```

> ⚠️ **The script is TypeScript. The callbacks you pass to the browser are not.**
>
> `npx tsx` compiles the file, so annotations are fine at the top level — and that is
> exactly what makes this trap easy to fall into. The function bodies handed to
> `page.evaluate()`, `page.$$eval()` and `page.addInitScript()` are serialised and run
> *inside the browser*, which never sees the compiler. One `:any` in there and the whole
> run dies on `SyntaxError: Unexpected token ':'` — you pay a full round trip to learn it.
>
> ```ts
> await page.evaluate(() => Array.from(document.images).map((i) => i.src));       // ✅
> await page.evaluate(() => Array.from(document.images).map((i: any) => i.src));  // ❌
> ```
>
> Inside those callbacks write plain JS: no type annotations, no `as`, no generics,
> no interfaces.

**Write to `tmp/` files only when** the script needs reuse, is complex, or user explicitly requests it.

### Key Principles

1. **Small scripts**: Each script does ONE thing (navigate, click, fill, check)
2. **Evaluate state**: Log/return state at the end to decide next steps
3. **Descriptive page names**: Use `"checkout"`, `"login"`, not `"main"`
4. **Disconnect to exit**: `await client.disconnect()` - pages persist on server
5. **Plain JS in evaluate**: `page.evaluate()` runs in browser - no TypeScript syntax

### Always `connect()` — never launch your own browser

```ts
const client = await connect();          // ✅ the visible browser on the desktop
const page = await client.page("work");
```

```ts
import { chromium } from "playwright";
const browser = await chromium.launch(); // ❌ silently headless, and invisible
```

`chromium.launch()` defaults to **headless**, so a browser started that way:

- cannot be seen by the user, who often wants to watch what you are doing
- cannot be reached by the `computer` tool, so a native dialog stops the run
  with no way out (see the handoff section below)
- has none of the profile, policy, or extension setup this browser has
- is a *second* browser, so its pages are invisible to `client.page()`

The browser `connect()` gives you is already running, visible, and configured.
Use it. Only launch a separate headless browser when the user explicitly asks
for headless — and say so in your answer when you do, because it means they
cannot watch and you cannot recover from a native dialog.

## Workflow Loop

Follow this pattern for complex tasks:

1. **Write a script** to perform one action
2. **Run it** and observe the output
3. **Evaluate** - did it work? What's the current state?
4. **Decide** - is the task complete or do we need another script?
5. **Repeat** until task is done

### No TypeScript in Browser Context

Code passed to `page.evaluate()` runs in the browser, which doesn't understand TypeScript:

```typescript
// Correct: plain JavaScript
const text = await page.evaluate(() => {
  return document.body.innerText;
});

// Wrong: TypeScript syntax will fail at runtime
const text = await page.evaluate(() => {
  const el: HTMLElement = document.body; // Type annotation breaks in browser!
  return el.innerText;
});
```

## Scraping Data

For scraping large datasets, intercept and replay network requests rather than scrolling the DOM. See [references/scraping.md](references/scraping.md) for the complete guide covering request capture, schema discovery, and paginated API replay.

## Client API

```typescript
const client = await connect();

// Get or create named page (viewport only applies to new pages)
const page = await client.page("name");
const pageWithSize = await client.page("name", { viewport: { width: 1920, height: 1080 } });

const pages = await client.list(); // List all page names
await client.close("name"); // Close a page
await client.disconnect(); // Disconnect (pages persist)

// ARIA Snapshot methods
const snapshot = await client.getAISnapshot("name"); // Get accessibility tree
const element = await client.selectSnapshotRef("name", "e5"); // Get element by ref
```

The `page` object is a standard Playwright Page.

## Waiting

```typescript
import { waitForPageLoad } from "@/client.js";

await waitForPageLoad(page); // After navigation
await page.waitForSelector(".results"); // For specific elements
await page.waitForURL("**/success"); // For specific URL
```

## Inspecting Page State

### Screenshots

```typescript
await page.screenshot({ path: "tmp/screenshot.png" });
await page.screenshot({ path: "tmp/full.png", fullPage: true });
```

### ARIA Snapshot (Element Discovery)

Use `getAISnapshot()` to discover page elements. Returns YAML-formatted accessibility tree:

```yaml
- banner:
  - link "Hacker News" [ref=e1]
  - navigation:
    - link "new" [ref=e2]
- main:
  - list:
    - listitem:
      - link "Article Title" [ref=e8]
      - link "328 comments" [ref=e9]
- contentinfo:
  - textbox [ref=e10]
    - /placeholder: "Search"
```

**Interpreting refs:**

- `[ref=eN]` - Element reference for interaction (visible, clickable elements only)
- `[checked]`, `[disabled]`, `[expanded]` - Element states
- `[level=N]` - Heading level
- `/url:`, `/placeholder:` - Element properties

**Interacting with refs:**

```typescript
const snapshot = await client.getAISnapshot("hackernews");
console.log(snapshot); // Find the ref you need

const element = await client.selectSnapshotRef("hackernews", "e2");
await element.click();
```

## When there is no browser at all

The user can close the browser whenever they like — it is their desktop. If a script
reports it cannot connect, or a screenshot shows no browser window, **do not look for a
browser icon**. Call:

```
computer  action: "open_browser"
```

That starts the managed browser and re-attaches to one already running. Loading this
skill does the same thing, so either route works.

Clicking a Chrome icon is not an equivalent fallback, even if you can see one. Chrome
started that way has **no remote-debugging port**, so `connect()` cannot reach it — the
hunt either fails outright or leaves you with a browser that looks right on screen and
is undrivable, which fails later and further from the cause.

## When the browser stops responding: hand off to `computer`

Some things that block a page are drawn by the **browser**, not the page — a
native dialog, an OS file picker, a print sheet, a crash bubble. No script can
reach them: `page.evaluate()` and `page.goto()` just hang until they time out,
and retrying the script does nothing. The most common one is a site trying to
open its own app ("Open xdg-open?"). Policy blocks the schemes we know about,
but an unknown one will still stop you.

The `computer` tool drives the real mouse and keyboard on the desktop, so it
**can** click what CDP cannot. Use it as an escape hatch, then come back:

1. **Recognise the symptom.** Two script runs in a row time out, or a call that
   should be instant (`page.title()`, a small `evaluate`) hangs. Do not keep
   retrying the script — the dialog is not going anywhere.
2. **Look at the screen.** `computer` with `action: "screenshot"`. The dialog
   will be plainly visible on top of the browser window.
3. **Dismiss it.** Click its safe button — `Cancel`, `Close`, `Not now` —
   with `left_click` at the coordinates you saw. `key` with `Escape` often
   works too, and is worth trying first since it needs no aiming.
4. **Confirm it is gone** with another screenshot before continuing.
5. **Go back to scripts.** Page state survived; `client.page("name")` returns
   the same page and you carry on where you stopped.

Stay in dev-browser for everything the page itself can do. `computer` is for
the moment the browser blocks you, not a substitute for scripting — clicking
page elements by coordinate is slower and far less reliable than using refs
from `getAISnapshot()`.

**This only works in `local` mode.** There the browser runs on this desktop, so
the screenshot shows it. In `extension` mode the browser is on the *user's own*
machine and nothing here can see or touch it — if it stalls behind a native
dialog, tell the user what to dismiss instead of trying to do it yourself.

If a scheme blocks you repeatedly, say so in your answer: it is worth adding to
the blocklist permanently rather than dismissing by hand every run.

## Error Recovery

Page state persists after failures. Debug with:

```bash
cd /opt/openbox/skills/dev-browser && npx tsx <<'EOF'
import { connect } from "@/client.js";

const client = await connect();
const page = await client.page("hackernews");

await page.screenshot({ path: "tmp/debug.png" });
console.log({
  url: page.url(),
  title: await page.title(),
  bodyText: await page.textContent("body").then((t) => t?.slice(0, 200)),
});

await client.disconnect();
EOF
```
