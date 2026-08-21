import { expect, test as setup } from "@playwright/test"

// One real form login for the whole suite (backend rate-limits login to
// 5/min/IP). The refresh cookie in storageState restores sessions elsewhere.
setup("password login reaches the workspace", async ({ page }) => {
  await page.goto("/login")
  await page.getByPlaceholder(/邮箱或用户名|Email or username/).fill("devtest")
  await page.getByPlaceholder(/至少 8 位|At least 8 characters/).fill("devtest1234")
  await page.getByRole("button", { name: /^登录$|^Sign in$/ }).click()
  await expect(page).toHaveURL(/\/app/, { timeout: 10_000 })
  await page.context().storageState({ path: "test-results/.auth-state.json" })
})
