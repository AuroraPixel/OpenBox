import js from "@eslint/js"
import tseslint from "typescript-eslint"
import reactHooks from "eslint-plugin-react-hooks"
import reactRefresh from "eslint-plugin-react-refresh"
import boundaries from "eslint-plugin-boundaries"
import i18next from "eslint-plugin-i18next"
import unusedImports from "eslint-plugin-unused-imports"
import jsxA11y from "eslint-plugin-jsx-a11y"
import globals from "globals"

export default tseslint.config(
  { ignores: ["dist", "coverage", "design-reference", "node_modules"] },

  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      "unused-imports": unusedImports,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-explicit-any": "error",
      "unused-imports/no-unused-imports": "error",
      "jsx-a11y/alt-text": "error",
      "jsx-a11y/aria-props": "error",

      // ENGINEERING_SPEC §6 — file/function size hard limits
      "max-lines": ["error", { max: 800, skipBlankLines: false, skipComments: false }],
      "max-lines-per-function": [
        "error",
        { max: 320, skipBlankLines: true, skipComments: true, IIFEs: false },
      ],
      complexity: ["error", 25],
      "max-params": ["error", 4],
      "max-depth": ["error", 5],

      // ENGINEERING_SPEC §9.1 — colors must come from tokens, never inline values
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/\\b(?:bg|text|border|fill|stroke|ring|shadow)-\\[#/]",
          message: "颜色必须走 token（ENGINEERING_SPEC §9.1），禁止 -[#hex] 任意值。",
        },
        {
          selector: "Literal[value=/hsl\\(var\\(--/]",
          message: "颜色必须走 token（ENGINEERING_SPEC §9.1），禁止 hsl(var(--x)) 任意值。",
        },
      ],
    },
  },

  // ENGINEERING_SPEC §4 — layer boundaries: app → routes → features → shared
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { boundaries },
    settings: {
      "boundaries/elements": [
        { type: "app", pattern: "src/app/**" },
        { type: "routes", pattern: "src/routes/**" },
        { type: "features", pattern: "src/features/*", capture: ["feature"] },
        { type: "shared", pattern: "src/shared/**" },
        { type: "locales", pattern: "src/locales/**" },
        { type: "styles", pattern: "src/styles/**" },
      ],
      "boundaries/include": ["src/**/*.{ts,tsx}"],
      "import/resolver": {
        typescript: { project: "./tsconfig.app.json" },
      },
    },
    rules: {
      "boundaries/dependencies": [
        "error",
        {
          default: "disallow",
          policies: [
            {
              from: { element: { type: "app" } },
              allow: { to: { element: { types: { anyOf: ["app", "routes", "features", "shared", "styles"] } } } },
            },
            {
              from: { element: { type: "routes" } },
              allow: { to: { element: { types: { anyOf: ["routes", "features", "shared"] } } } },
            },
            // A feature may import itself and shared — never another feature.
            {
              from: { element: { type: "features" } },
              allow: [
                { to: { element: { type: "features", captured: { feature: "{{from.feature}}" } } } },
                { to: { element: { type: "shared" } } },
              ],
            },
            { from: { element: { type: "shared" } }, allow: { to: { element: { type: "shared" } } } },
          ],
        },
      ],
    },
  },

  // ENGINEERING_SPEC §10.4 — no hardcoded user-facing strings in UI code
  {
    files: ["src/**/*.tsx"],
    ignores: ["src/**/*.test.tsx"],
    plugins: { i18next },
    rules: {
      "i18next/no-literal-string": [
        "error",
        {
          mode: "jsx-only",
          "jsx-attributes": {
            include: ["placeholder", "title", "aria-label", "alt", "label"],
          },
          words: {
            // Entries are matched as regexes — letters-only names here; pure
            // symbol glyphs are excluded via the callee/JSX symbol regex below.
            exclude: ["bossip", "^b$", "var\\(--.*", "^[^A-Za-z\u4e00-\u9fff]*$"],
          },
        },
      ],
    },
  },

  // Non-UI layers: size limits only, no JSX rules needed
  {
    files: ["**/*.test.{ts,tsx}", "e2e/**"],
    rules: {
      "max-lines-per-function": "off",
      "i18next/no-literal-string": "off",
    },
  },
)
