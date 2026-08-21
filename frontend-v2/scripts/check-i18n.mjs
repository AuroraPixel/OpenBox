// i18n gates (ENGINEERING_SPEC §10.8): key parity across languages and
// interpolation-variable consistency.
import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

const root = new URL("../src/locales", import.meta.url).pathname
const langs = readdirSync(root)
const [base, ...rest] = langs
let failed = false

const flat = (obj, prefix = "") =>
  Object.entries(obj).flatMap(([k, v]) => {
    const key = prefix ? `${prefix}.${k}` : k
    if (v !== null && typeof v === "object" && !Array.isArray(v)) return flat(v, key)
    return [[key, v]]
  })

const varsOf = (v) => {
  if (Array.isArray(v)) v = v.map((x) => JSON.stringify(x)).join(" ")
  if (typeof v !== "string") return ""
  return [...v.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort().join(",")
}

for (const ns of readdirSync(join(root, base))) {
  const baseMap = new Map(flat(JSON.parse(readFileSync(join(root, base, ns), "utf8"))))
  for (const lang of rest) {
    let other
    try {
      other = new Map(flat(JSON.parse(readFileSync(join(root, lang, ns), "utf8"))))
    } catch {
      console.error(`✗ ${lang}/${ns} missing or invalid`)
      failed = true
      continue
    }
    for (const [k, v] of baseMap) {
      if (!other.has(k)) {
        console.error(`✗ ${lang}/${ns}: missing key ${k}`)
        failed = true
      } else if (varsOf(v) !== varsOf(other.get(k))) {
        console.error(`✗ ${lang}/${ns}: interpolation mismatch at ${k}`)
        failed = true
      }
    }
    for (const k of other.keys()) {
      if (!baseMap.has(k)) {
        console.error(`✗ ${base}/${ns}: missing key ${k} (present in ${lang})`)
        failed = true
      }
    }
  }
}
if (failed) process.exit(1)
console.log("i18n parity OK")
