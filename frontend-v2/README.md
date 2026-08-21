# bossip — OpenBox Frontend v2

基于 [bossip 设计稿](design-reference/) 重写的 OpenBox 前端。规范见 [docs/ENGINEERING_SPEC.md](docs/ENGINEERING_SPEC.md)。

## 开发

```bash
npm install
npm run dev        # http://localhost:3000（代理 /api /ws → localhost:8080）
```

后端：仓库根目录 `make backend`（FastAPI, :8080）。

## 质量门禁

```bash
npm run check      # i18n parity + lint + tsc + vitest
npx playwright test  # E2E（需后端 + devtest 账号）
```

## 结构

```
src/
├── app/        # 装配：providers / router / layouts / bootstrap
├── routes/     # 路由薄壳
├── features/   # workspace / chat / workbench / auth / settings
├── shared/     # api / ws / ui / i18n / appearance / lib / types
├── locales/    # zh-CN · en-US（key 全量对齐，CI 校验）
└── styles/     # Tailwind 4 @theme token（8 主题 × 深浅色 × 4 字号）
```
