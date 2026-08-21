import { expect, test } from "@playwright/test"

// Locks the DEEIX-Chat message shape: user bubbles right, assistant turns
// full-width with no avatar, and collapsed trace rows carrying a title over
// a muted summary.
test("chat renders the DEEIX message shape", async ({ page }) => {
  await page.goto("/app")
  await page.getByRole("link", { name: /hello\.txt/ }).first().click()
  await expect(page).toHaveURL(/\/app\/s\//)

  // Trace rows: 处理完成 + 准备 N tokens 上下文 / 工具调用 + N 次工具调用
  const processRow = page.getByRole("button", { name: /处理完成|Processed/ }).first()
  await expect(processRow).toBeVisible({ timeout: 10_000 })
  await expect(processRow).toContainText(/tokens/)
  await expect(processRow).toHaveAttribute("aria-expanded", "false")

  const toolRow = page.getByRole("button", { name: /工具调用|Tool calls/ }).first()
  await expect(toolRow).toContainText(/次工具调用|tool call/)

  // Expanding a trace reveals its body.
  await toolRow.click()
  await expect(toolRow).toHaveAttribute("aria-expanded", "true")

  // The assistant column carries no avatar tile.
  await expect(page.locator("[data-assistant-avatar]")).toHaveCount(0)
})
