import { expect, test } from "@playwright/test"

async function login(page: import("@playwright/test").Page) {
  // Session restores from the storageState refresh cookie.
  await page.goto("/app")
  await expect(page).toHaveURL(/\/app/, { timeout: 10_000 })
}

test("theme pick flips tokens, survives reload, and restores", async ({ page }) => {
  await login(page)
  await page.goto("/app/settings/appearance")

  await page.getByRole("button", { name: "azure" }).click()
  await expect(page.locator("html")).toHaveAttribute("data-theme", "azure")

  // Server-side prefs hydrate the theme back after a full reload.
  await page.reload()
  await expect(page.locator("html")).toHaveAttribute("data-theme", "azure", { timeout: 10_000 })

  await page.getByRole("button", { name: "默认", exact: true }).click()
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", "azure")
})
