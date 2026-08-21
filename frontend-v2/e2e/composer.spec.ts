import { expect, test } from "@playwright/test"

// Locks the DEEIX composer: no black focus ring, one morphing action button,
// and the @-mention menu resolving real sandbox files.
test("composer focus stays on the shell, not a black textarea outline", async ({ page }) => {
  await page.goto("/app")
  const ta = page.getByPlaceholder(/输入消息|Message,/)
  await ta.click()
  await expect(ta).toHaveCSS("outline-style", "none")
})

test("@ mention lists sandbox files and inserts the path", async ({ page }) => {
  await page.goto("/app")
  const ta = page.getByPlaceholder(/输入消息|Message,/)
  await ta.click()
  await ta.fill("看一下 @hello")

  const option = page.getByRole("option").first()
  await expect(option).toBeVisible({ timeout: 10_000 })
  await expect(option).toContainText("/workspace/")

  await option.click()
  await expect(ta).toHaveValue(/@\/workspace\/.*hello\.txt/)
  await expect(page.getByRole("listbox")).toHaveCount(0)
})

test("send button is disabled until there is something to send", async ({ page }) => {
  await page.goto("/app")
  const send = page.getByRole("button", { name: /^发送$|^Send$/ })
  await expect(send).toBeDisabled()
  await page.getByPlaceholder(/输入消息|Message,/).fill("hi")
  await expect(send).toBeEnabled()
})
