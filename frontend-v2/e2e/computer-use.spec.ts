import { expect, test } from "@playwright/test"
import { waitForIdleAgent } from "./helpers/agent"

// The agent drives the cloud desktop: it must take a real screenshot, actually
// RECEIVE it, and answer from it. The regression this guards is subtle — a
// broken OSS object key made the image silently vanish from the request, and
// the model then confidently described a screen it had never seen. So the
// assertions are: the tool ran, an image card came back from OSS, and nothing
// reported an unloadable image.
test("agent screenshots the desktop and actually receives the image", async ({ page }) => {
  test.setTimeout(300_000)
  await page.goto("/app")
  await waitForIdleAgent(page)
  const composer = page.getByPlaceholder(/输入消息|Message,/)
  await expect(composer).toBeVisible({ timeout: 10_000 })

  await composer.fill(
    "请用 computer 工具截取云桌面截图,然后用一句话描述你看到的画面。禁止使用 bash。",
  )
  await composer.press("Enter")
  await expect(page).toHaveURL(/\/app\/s\//, { timeout: 20_000 })

  // Wait for the turn to finish (stop button disappears).
  await expect(page.getByRole("button", { name: /停止|Stop/ })).toHaveCount(0, { timeout: 240_000 })

  const main = page.locator("main")
  await expect(main).toContainText(/computer/i)
  // The screenshot came back through OSS and rendered as a card.
  await expect(page.locator('main img[src*="aliyuncs.com"]').first()).toBeVisible({ timeout: 20_000 })
  // The model was never handed an unloadable image.
  await expect(main).not.toContainText(/could not be loaded/i)
})
