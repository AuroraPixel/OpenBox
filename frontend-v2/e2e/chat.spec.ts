import { expect, test } from "@playwright/test"

async function login(page: import("@playwright/test").Page) {
  // Session restores from the storageState refresh cookie.
  await page.goto("/app")
  await expect(page).toHaveURL(/\/app/, { timeout: 10_000 })
}

test("send a message and receive a streamed agent turn", async ({ page }) => {
  test.setTimeout(120_000)
  await login(page)

  const composer = page.getByPlaceholder(/输入消息|Message,/)
  await composer.fill("只回复两个字：收到")
  await composer.press("Enter")

  // Session route + user bubble appear immediately (optimistic).
  await expect(page).toHaveURL(/\/app\/s\//, { timeout: 15_000 })
  await expect(page.getByText("只回复两个字：收到").first()).toBeVisible()

  // The agent's reply streams in over WS.
  await expect(page.getByText(/收到/).nth(1)).toBeVisible({ timeout: 90_000 })
})

test("language toggle switches the whole UI", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { level: 1 })).toContainText("把你的专业")
  await page.getByText("EN", { exact: true }).first().click()
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Turn what you know", {
    timeout: 10_000,
  })
  await page.getByText("中", { exact: true }).first().click()
  await expect(page.getByRole("heading", { level: 1 })).toContainText("把你的专业")
})
