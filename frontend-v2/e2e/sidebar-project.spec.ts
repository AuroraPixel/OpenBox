import { expect, test } from "@playwright/test"

// New chat must respect the sidebar's current project: creating a chat while a
// project is selected files the session into that project, and the tree's
// selection/expansion state survives both the navigation and a reload.
test("new chat keeps the selected project and the tree state", async ({ page }) => {
  // Grab a real project id from the list the sidebar loads.
  const projectsResp = page.waitForResponse((r) => r.url().includes("/api/agent/project") && r.request().method() === "GET")
  await page.goto("/app")
  const projects = (await (await projectsResp).json()) as { id: string; name: string }[]
  expect(projects.length).toBeGreaterThan(0)
  const target = projects[0]

  // Click the project's chevron: collapses it and makes it the current
  // project (accent dot on its name).
  const chevron = page.locator(`button[aria-label="${target.name}"]`).first()
  await chevron.click()
  const dot = page.locator("aside span.bg-accent")
  await expect(dot).toBeVisible()
  await expect(chevron).toHaveAttribute("aria-expanded", "false")

  // …new chat from the top button carries that project in the URL…
  await page.getByRole("button", { name: /新对话|New chat/ }).click()
  await expect(page).toHaveURL(new RegExp(`/app\\?project=${target.id}`))

  // …and the tree state did NOT reset: still selected, still collapsed.
  await expect(dot).toBeVisible()
  await expect(chevron).toHaveAttribute("aria-expanded", "false")

  // Sending the first message must create the session INSIDE that project.
  const createReq = page.waitForRequest(
    (r) => r.url().endsWith("/api/agent/session") && r.method() === "POST",
  )
  const composer = page.getByPlaceholder(/输入消息|Message,/)
  await composer.fill("只回复ok这一个词")
  await composer.press("Enter")
  const body = (await createReq).postDataJSON() as { project_id?: string }
  expect(body.project_id).toBe(target.id)
  await expect(page).toHaveURL(/\/app\/s\//, { timeout: 20_000 })

  // Selection and expansion survive a full reload (persisted).
  await page.reload()
  await expect(page.locator("aside span.bg-accent")).toBeVisible({ timeout: 10_000 })
  const chevronAfter = page.locator(`button[aria-label="${target.name}"]`).first()
  await expect(chevronAfter).toHaveAttribute("aria-expanded", "false")

  // Restore expansion for other tests.
  await chevronAfter.click()
})
