import { expect, test } from "@playwright/test"
import { waitForIdleAgent } from "./helpers/agent"

// The stop button must cancel the in-flight LLM stream (opencode's AbortSignal
// semantics), not just set a flag the loop reads at the next chunk. Regression:
// during silent generation the old flag-check never ran and stop did nothing.

test("stop halts content growth immediately", async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto("/app")
  await waitForIdleAgent(page)
  const composer = page.getByPlaceholder(/输入消息|Message,/)
  await composer.fill("帮我写一个完整的俄罗斯方块,html+css+js 都要非常详细,先输出很长的文字方案再写代码")
  await composer.press("Enter")
  await expect(page).toHaveURL(/\/app\/s\//, { timeout: 20_000 })

  // 固定在发出 2 秒后按停:此刻几乎必然仍在生成(常在模型的静默期 ——
  // 正是老实现完全不响应停止的场景);等内容流出再点反而会赶上快答案
  // 已经跑完、按钮消失的时序。
  const stopBtn = page.getByRole("button", { name: /停止|Stop/ }).first()
  await expect(stopBtn).toBeVisible({ timeout: 10_000 })
  await page.waitForTimeout(2000)
  await stopBtn.click()
  await page.waitForTimeout(1500)
  const lenAtStop = (await page.locator("main").innerText()).length
  await page.waitForTimeout(4000)
  const lenAfter = (await page.locator("main").innerText()).length
  console.log("GROWTH AFTER STOP:", lenAfter - lenAtStop, "chars; busy:", await page.getByRole("button", { name: /停止|Stop/ }).count())
  expect(lenAfter - lenAtStop).toBeLessThan(30)
  await expect(page.getByRole("button", { name: /停止|Stop/ })).toHaveCount(0)
})
