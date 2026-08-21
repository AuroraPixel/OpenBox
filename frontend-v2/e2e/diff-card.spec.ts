import { expect, test } from "@playwright/test"
import { waitForIdleAgent } from "./helpers/agent"

// End-to-end proof of the change card: the agent edits a file, the backend
// records a patch part with its snapshot range, the card fetches that step's
// diff and renders collapsed-context rows, and clicking opens review.
test("an edit produces a change card that previews the diff and opens review", async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto("/app")
  await waitForIdleAgent(page)

  const composer = page.getByPlaceholder(/输入消息|Message,/)
  await composer.fill(
    // Snapshots track the project directory, so the file must live inside it.
    "用 write 工具创建 /workspace/default/e2e-diff.txt，内容三行：one、two、three。再用 edit 把 two 改成 TWO。不要解释。",
  )
  await composer.press("Enter")
  await expect(page).toHaveURL(/\/app\/s\//, { timeout: 20_000 })

  const card = page.getByRole("button", { name: /审阅 →|Review →/ }).last()
  await expect(card).toBeVisible({ timeout: 150_000 })
  await expect(card).toContainText(/e2e-diff\.txt/)
  // A quiet row: path plus how much moved. The hunks belong in the panel, not
  // in the conversation — no diff lines, no gap bars.
  await expect(card).toContainText(/[+−]\d+/)
  await expect(card).not.toContainText(/行未修改|unmodified line/)
  expect((await card.boundingBox())?.height ?? 999).toBeLessThan(40)

  await card.click()
  const panel = page.locator("section").filter({ hasText: /本轮改动|This turn's changes/ })
  await expect(panel).toBeVisible({ timeout: 10_000 })
  // The header alone used to render over an empty list, so assert real content:
  // the clicked file must be listed *and* be the expanded card.
  await expect(panel.getByText("e2e-diff.txt").first()).toBeVisible({ timeout: 10_000 })
  await expect(panel.locator('button[aria-expanded="true"]')).toContainText("e2e-diff.txt")
})
