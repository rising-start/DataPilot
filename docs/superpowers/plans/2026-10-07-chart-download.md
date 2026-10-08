# 图表下载（Chart Download）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在图表卡片头部新增一个「下载图片」按钮，点击后把当前 ECharts 图表导出为 PNG，不点则不下载。

**Architecture:** 纯前端方案。把「生成安全的文件名」抽成可单测的纯函数 `buildChartFileName`，在 `ChartView.vue` 中新增按钮与 `downloadChart()` 处理：调用已有的 `chart.getDataURL({ type: 'png' })` 拿到 data URL，用临时 `<a download>` 触发浏览器下载。不涉及后端、不改 `ChartControls`。

**Tech Stack:** Vue 3 (`<script setup>`) + Element Plus (`el-button` / `Download` 图标，包已随 element-plus 安装) + ECharts 5 (`getDataURL`) + Vitest（单测）。

## Global Constraints

- 仅改动前端；**不**新增后端接口、**不**引入自动下载开关、**不**改动 `ChartControls.vue` 职责。
- 导出格式固定为 **PNG**；`getDataURL` 须带 `pixelRatio: 2` 与 `backgroundColor: '#fff'`。
- 文件名取 `spec.title` 清洗后作前缀，标题为空/清洗后为空时回退为 `图表-<时间戳>`；扩展名固定 `.png`。
- 无图表（`option` 为空 / `chart` 为 null）时按钮 `disabled`。
- 使用既有的 Vitest 配置（`web/src/utils/*.spec.ts` 风格），不要引入新的测试框架或 jsdom。

---

## File Structure

- **Create:** `web/src/utils/chartDownload.ts` — 纯函数 `buildChartFileName(title, now?)`，负责把标题清洗为安全文件名。
- **Create:** `web/src/utils/chartDownload.spec.ts` — 该函数的 Vitest 单测。
- **Modify:** `web/src/components/ChartView.vue` — 头部加「下载图片」按钮 + `downloadChart()` 处理函数。

---

### Task 1: 文件名清洗纯函数（TDD）

**Files:**
- Create: `web/src/utils/chartDownload.ts`
- Create: `web/src/utils/chartDownload.spec.ts`

**Interfaces:**
- Produces: `buildChartFileName(title: string, now?: number): string` —— Task 2 的 `downloadChart()` 直接调用。

- [ ] **Step 1: 写失败测试**

新建 `web/src/utils/chartDownload.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { buildChartFileName } from './chartDownload'

describe('buildChartFileName', () => {
  it('普通标题追加 .png 并清洗非法字符', () => {
    expect(buildChartFileName('销售分析 / 2026')).toBe('销售分析 _ 2026.png')
  })

  it('去除首尾空格与末尾点', () => {
    expect(buildChartFileName('  周报 . ')).toBe('周报.png')
  })

  it('空标题回退为 图表-<时间戳>.png', () => {
    const name = buildChartFileName('', 1_700_000_000_000)
    expect(name.startsWith('图表-')).toBe(true)
    expect(name.endsWith('.png')).toBe(true)
  })

  it('仅含非法字符时回退为时间戳文件名', () => {
    const name = buildChartFileName('///', 1_700_000_000_000)
    expect(name.startsWith('图表-')).toBe(true)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

```
cd web && npm test -- chartDownload
```

预期：报错 `Cannot find module './chartDownload'`（模块尚未创建）。

- [ ] **Step 3: 实现最小可用函数**

新建 `web/src/utils/chartDownload.ts`：

```ts
// 文件名中的非法字符（跨 Windows / Unix）：\ / : * ? " < > | 及控制字符
const ILLEGAL = /[\\/:*?"<>|\x00-\x1f]/g

export function buildChartFileName(title: string, now: number = Date.now()): string {
  const cleaned = (title ?? '')
    .trim()
    .replace(ILLEGAL, '_')
    .replace(/\.+$/g, '') // 去掉末尾的点（Windows 不允许）
    .replace(/\s+$/g, '') // 去掉末尾空白

  if (!cleaned) {
    const ts = new Date(now).toISOString().replace(/[:.]/g, '-')
    return `图表-${ts}.png`
  }
  return `${cleaned}.png`
}
```

- [ ] **Step 4: 运行测试确认通过**

```
cd web && npm test -- chartDownload
```

预期：4 个用例全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add web/src/utils/chartDownload.ts web/src/utils/chartDownload.spec.ts
git commit -m "feat(web): add buildChartFileName helper for chart download"
```

---

### Task 2: 在 ChartView 接入下载按钮

**Files:**
- Modify: `web/src/components/ChartView.vue`

**Interfaces:**
- Consumes: `buildChartFileName(title: string, now?: number): string`（来自 Task 1）
- Consumes: 已有的模块级 `let chart: echarts.ECharts | null` 与 `option` computed

- [ ] **Step 1: 给 ChartView 增加下载按钮与处理函数**

在 `ChartView.vue` 中做以下三处修改。

(1) `<script setup>` 顶部新增导入：

```ts
import { Download } from '@element-plus/icons-vue'
```

并在 `render()` 函数之后新增：

```ts
function downloadChart() {
  if (!chart) return
  const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' })
  const a = document.createElement('a')
  a.href = url
  a.download = buildChartFileName(viewSpec.value.title)
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
```

(2) 模板中，在 `</template>` 的头部 `div.head` 内、`ChartControls` 之后追加按钮：

```vue
<el-button size="small" :icon="Download" :disabled="!option" @click="downloadChart">
  下载图片
</el-button>
```

(3) 确认顶部 `import` 区块已包含 `buildChartFileName`：

```ts
import { buildChartFileName } from '../utils/chartDownload'
```

- [ ] **Step 2: 类型检查**

```
cd web && npm run typecheck
```

预期：无类型错误（`vue-tsc --noEmit` 通过）。

- [ ] **Step 3: 手动验证（无自动化组件测试，沿用项目现状）**

```
cd web && npm run dev
```

1. 运行一次分析生成图表 → 卡片头部出现「下载图片」按钮。
2. 点击 → 浏览器下载一张 PNG，内容与屏幕图表一致（含 ChartControls 的手动调整）。
3. 将图表调整为 `none` 或数据为空时 → 按钮处于禁用（`disabled`）状态。

- [ ] **Step 4: 提交**

```bash
git add web/src/components/ChartView.vue
git commit -m "feat(web): add download button to export chart as PNG"
```

---

## Self-Review 记录

- **Spec 覆盖**：下载按钮（Task 2）、PNG 格式 + pixelRatio/背景（Task 2 `getDataURL`）、文件名清洗+回退（Task 1）、无图禁用（Task 2 `:disabled="!option"`）、不改 ChartControls/后端（Global Constraints）均覆盖。
- **占位符扫描**：无 TBD/TODO；所有代码步骤均给出完整代码。
- **类型一致性**：`buildChartFileName(title, now?)` 在 Task 1 定义、Task 2 以 `viewSpec.value.title` 调用，签名一致；`chart` / `option` 为既有变量，未改名。
- **依赖**：`@element-plus/icons-vue` 已随 element-plus 安装在 `web/node_modules`，`Download` 图标可直接导入；若 `npm run build` 报模块缺失，再将其加入 `web/package.json` 依赖并 `npm install`。
