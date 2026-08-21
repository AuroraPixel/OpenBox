import { expect, test } from "@playwright/test"

// Visitor viewpoint: no stored session.
test.use({ storageState: { cookies: [], origins: [] } })

test("landing renders and navigates to login", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await page.getByText(/^登录$|^Sign in$/).first().click()
  await expect(page).toHaveURL(/\/login/)
})
