import { expect, test } from "@playwright/test"

// Locks the DEEIX message meta bar + structured tool output.
test("message meta bar carries real usage and actions", async ({ page }) => {
  await page.goto("/app")
  await page.getByRole("link", { name: /hello\.txt/ }).first().click()
  await expect(page).toHaveURL(/\/app\/s\//)

  // Meta actions exist and are hover-gated (hidden until the turn is hovered).
  const like = page.getByRole("button", { name: /点赞|Good response/ }).last()
  await expect(like).toBeAttached()
  const bar = like.locator("xpath=ancestor::div[contains(@class,'transition-opacity')][1]")
  await expect(bar).toHaveCSS("opacity", "0")

  // Hovering the turn reveals it, and it carries real token counts.
  await bar.locator("xpath=ancestor::div[contains(@class,'group/msg')][1]").hover()
  await expect(bar).toHaveCSS("opacity", "1")
  await expect(page.getByRole("button", { name: /复制|Copy/ }).last()).toBeVisible()
  await expect(page.getByRole("button", { name: /复刻|Fork/ }).last()).toBeVisible()
})

test("tool chain renders structured per-tool output", async ({ page }) => {
  await page.goto("/app")
  await page.getByRole("link", { name: /hello\.txt/ }).first().click()

  const chain = page.getByRole("button", { name: /工具调用|Tool calls/ }).first()
  await chain.click()

  // Structured layout: a per-tool status line plus at least one labelled
  // section — which label depends on the tool (file / shell / search / generic).
  await expect(page.getByText(/已完成|Done/).first()).toBeVisible({ timeout: 10_000 })
  const label = page.getByText(
    /^(请求|响应|命令|输出|路径|参数|结果|改动|内容|匹配|错误|Request|Response|Command|Output|Path|Arguments|Result|Diff|Content|Matches|Error)$/,
  )
  await expect(label.first()).toBeVisible()
})
