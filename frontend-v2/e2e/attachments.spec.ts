import { expect, test } from "@playwright/test"
import { waitForIdleAgent } from "./helpers/agent"
import zlib from "node:zlib"

// A real PNG, generated in-test: gradient 48x48 RGBA.
function testPng(): Buffer {
  const w = 48
  const rows: Buffer[] = []
  for (let y = 0; y < w; y++) {
    const row = Buffer.alloc(1 + w * 4)
    for (let x = 0; x < w; x++) row.set([(x * 5) % 256, (y * 5) % 256, 160, 255], 1 + x * 4)
    rows.push(row)
  }
  const chunk = (type: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(type), data])
    const len = Buffer.alloc(4)
    len.writeUInt32BE(data.length)
    const crc = Buffer.alloc(4)
    crc.writeUInt32BE(zlib.crc32(body) >>> 0)
    return Buffer.concat([len, body, crc])
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(w, 0)
  ihdr.writeUInt32BE(w, 4)
  ihdr.set([8, 6, 0, 0, 0], 8)
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ])
}

// The full transfer path, against the real stack: the browser PUTs the bytes
// straight to OSS (never through the backend), the sent message renders an
// image preview card from a presigned GET, and the desktop pulls the file
// into /workspace/uploads before the agent starts.
test("attachment travels browser → OSS and previews as a card", async ({ page }) => {
  test.setTimeout(120_000)
  const ossPuts: string[] = []
  page.on("request", (r) => {
    if (r.method() === "PUT" && r.url().includes("aliyuncs.com")) ossPuts.push(r.url())
  })

  await page.goto("/app")
  await waitForIdleAgent(page)
  const composer = page.getByPlaceholder(/输入消息|Message,/)
  await expect(composer).toBeVisible({ timeout: 10_000 })

  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({ name: "e2e-attach.png", mimeType: "image/png", buffer: testPng() })

  // Composer strip shows the image thumbnail while/after uploading; wait for
  // the progress % to become a size — the send gate opens only then.
  await expect(page.locator('img[src^="blob:"]')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/^\d+%$/)).toHaveCount(0, { timeout: 20_000 })

  await composer.fill("收到图片请只回复ok")
  await composer.press("Enter")
  await expect(page).toHaveURL(/\/app\/s\//, { timeout: 20_000 })

  // The bytes went to OSS directly, and the chat card previews via OSS too.
  expect(ossPuts.length).toBeGreaterThan(0)
  await expect(page.locator('img[src*="aliyuncs.com"]').first()).toBeVisible({ timeout: 20_000 })
})
