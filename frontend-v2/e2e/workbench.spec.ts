import { expect, test } from "@playwright/test"

// Files panel, inside a session: the tree roots at the session's PROJECT
// directory (/workspace/<slug>), never the whole /workspace sandbox, and the
// header shows that directory's name — not the container id.
test("files panel scopes to the session's project directory", async ({ page }) => {
  await page.goto("/app")
  await expect(page).toHaveURL(/\/app/, { timeout: 10_000 })

  // Enter whichever session is first — the scoping must hold for any of them.
  await page.locator('a[href*="/app/s/"]').first().click()
  await expect(page).toHaveURL(/\/app\/s\//)

  await page.getByRole("button", { name: /打开工作面板|Open workspace panel/ }).click()

  const panel = page.locator("section")
  // The menu page hints must be human — never the sandbox's machine id
  // (Wuying desktop id / container hash).
  await expect(panel.getByText(/终端|Terminal/).first()).toBeVisible()
  await expect(panel).not.toContainText(/ecd-[a-z0-9]{8,}/)

  await page.getByRole("button", { name: /文件|Files/ }).last().click()
  // The first breadcrumb is the project directory, so "workspace" (the whole
  // agent activity space) must never appear as a crumb.
  const crumbs = panel.locator("div.flex-wrap button")
  await expect(crumbs.first()).toBeVisible({ timeout: 10_000 })
  await expect(crumbs.first()).not.toHaveText("workspace")
  // Header shows the directory name, not the container's random id.
  await expect(panel.getByText(/›/)).not.toContainText(/^[a-z]{3}-[a-z0-9]{10,}/)

  // Open a known text file. Deliberately not "the first file": the project
  // directory also holds binaries the agent produced, and the viewer renders
  // text — the test would then assert on whatever landed alphabetically first
  // that day.
  await panel.getByRole("button", { name: /hello\.txt/ }).click()
  const viewer = page.getByTestId("file-viewer-content")
  await expect(viewer).toBeVisible({ timeout: 10_000 })
  await expect(viewer).not.toBeEmpty()
})

// Opening the panel used to blank the whole workspace: the panel sits outside
// the layout's Suspense boundary, so `useTranslation("workbench")` fetching its
// namespace suspended all the way up to the router boundary — the app flashed a
// fallback and every effect re-ran (WS reconnect, full refetch). Guard both the
// blank frame and the refetch storm.
test("opening the panel neither blanks the workspace nor refetches the session", async ({ page }) => {
  await page.goto("/app")
  await expect(page).toHaveURL(/\/app/, { timeout: 10_000 })
  await page.waitForTimeout(2500) // let first paint settle

  const requests: string[] = []
  page.on("request", (r) => requests.push(r.url()))

  // Sample every frame while the panel opens.
  await page.evaluate(() => {
    const w = window as unknown as { __h: number[] }
    w.__h = []
    const tick = () => {
      const main = document.querySelector("main")
      w.__h.push(main ? Math.round(main.getBoundingClientRect().height) : 0)
      if (w.__h.length < 60) requestAnimationFrame(tick)
    }
    tick()
  })

  await page.getByRole("button", { name: /打开工作面板|Open workspace panel/ }).click()
  await page.waitForTimeout(1500)

  const heights = await page.evaluate(() => (window as unknown as { __h: number[] }).__h)
  expect(heights.length).toBeGreaterThan(10)
  expect(heights.filter((h) => h === 0)).toHaveLength(0)

  // A locale fetch here means the panel suspended; a session refetch means the
  // tree remounted.
  expect(requests.filter((u) => u.includes("/locales/"))).toHaveLength(0)
  expect(requests.filter((u) => u.includes("/auth/ticket"))).toHaveLength(0)
  expect(requests.filter((u) => u.endsWith("/api/agent/session"))).toHaveLength(0)
})

// 云桌面 tab: the menu row opens a desktop view that talks to
// /api/desktop/ticket. Stubbed here (the real stream needs cloud
// credentials); asserts the state machine and that no machine id leaks.
test("cloud desktop tab connects via the ticket API and never shows ids", async ({ page }) => {
  let ticketCalls = 0
  await page.route("**/api/desktop/ticket*", (route) => {
    ticketCalls += 1
    void route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ available: false, reason: "provider" }),
    })
  })

  await page.goto("/app")
  await expect(page).toHaveURL(/\/app/, { timeout: 10_000 })
  await page.getByRole("button", { name: /打开工作面板|Open workspace panel/ }).click()

  const panel = page.locator("section")
  await panel.getByRole("button", { name: /云桌面|Cloud desktop/ }).click()

  // Ticket was requested, the failure state rendered, and nothing that looks
  // like a desktop/container id ever hit the DOM.
  await expect(panel.getByText(/云桌面暂不可用|Cloud desktop is unavailable/)).toBeVisible({ timeout: 10_000 })
  await expect(panel.getByRole("button", { name: /重新连接|Reconnect/ })).toBeVisible()
  expect(ticketCalls).toBeGreaterThan(0)
  await expect(panel).not.toContainText(/ecd-[a-z0-9]{8,}/)
})
