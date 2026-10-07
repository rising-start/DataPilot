# 图表 X/Y 轴可由客户校正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在图表卡片头部开放 X 轴、Y 轴、图型三个下拉，客户可校正 AI 推断的 `chart_spec` 并即时重画，无需重新执行分析。

**Architecture:** 后端零改动。前端新增纯函数模块 `utils/chartColumns.ts`（候选列推导与 spec 编辑）与展示组件 `ChartControls.vue`；`ChartView.vue` 内部维护一份 `viewSpec`（编辑态），渲染改用它，`props.spec` 作为 AI 默认值，改动不回传后端。

**Tech Stack:** Vue 3 + TypeScript + Vite + Element Plus + ECharts + Vitest

## Global Constraints

- 范围仅限 `web/src`；**不得修改** `server/`、`agent/`、`viz/`、`service.py`、`core/`，也不得修改 `chart_spec` v1 契约与 `types.ts` 中的 `ChartSpec` / `TaskView` 定义。
- 可编辑字段只有三个：`x`、`y`、`chart_type`。`title` 永不修改；`series` 恒为单元素（跟随 `y`）。
- 候选列**只来自当前结果表 `rows` 已有的列**，不做任何后端请求、不重新执行代码或 SQL。
- 沿用现有代码风格：组件用 `<script setup lang="ts">`，单测用 `import { describe, expect, it } from 'vitest'`，纯函数与组件分离（参考 `web/src/utils/echarts.ts` + `echarts.spec.ts`）。
- 测试命令：`cd web && npm run test`（vitest run）、`npm run typecheck`（vue-tsc --noEmit）、`npm run build`；后端回归 `python -m pytest tests -q` 预期 81 passed。
- **Git：仓库当前没有任何 commit，且索引里是重构前的旧文件（`app.py`、`tools/`、`utils/`、`agent/nodes.py`、`.idea/`），当前源码大多是 untracked。提交时必须用显式路径 `git add <具体文件>`，禁止 `git add -A` 或 `git add .`（会把 `web/node_modules` 一万多个文件加进来）。**

---

### Task 1: 候选列与 spec 编辑的纯函数

**Files:**
- Create: `web/src/utils/chartColumns.ts`
- Test: `web/src/utils/chartColumns.spec.ts`

**Interfaces:**
- Consumes: `web/src/types.ts` 的 `ChartSpec`（`chart_type: 'bar' | 'line' | 'pie' | 'hist' | 'none'`；`x: string | null`；`y: string | null`；`series: string[]`；`title: string`）与 `Row`（`Record<string, any>`）
- Produces（Task 2、Task 3 依赖）：
  - `collectColumns(rows: Row[]): string[]`
  - `isNumericColumn(rows: Row[], col: string): boolean`
  - `dimensionCandidates(rows: Row[]): SelectOption[]`
  - `metricCandidates(rows: Row[]): SelectOption[]`
  - `chartTypeOptions(current: ChartSpec['chart_type']): SelectOption[]`
  - `applyChartEdit(spec: ChartSpec, patch: ChartPatch): ChartSpec`
  - 类型 `ChartPatch`、`SelectOption`、`ChartType`

- [ ] **Step 1: 写失败测试**

Create `web/src/utils/chartColumns.spec.ts`:

```ts
import { describe, expect, it } from 'vitest'
import {
  applyChartEdit,
  chartTypeOptions,
  collectColumns,
  dimensionCandidates,
  isNumericColumn,
  metricCandidates,
} from './chartColumns'

const rows = [
  { region: '华东', sales_amount: 10, qty: 2 },
  { region: '华南', sales_amount: 20, qty: 3 },
]

describe('collectColumns', () => {
  it('取所有行 key 的并集，去重并保持首次出现顺序', () => {
    expect(
      collectColumns([
        { a: 1, b: 2 },
        { b: 3, c: 4 },
      ]),
    ).toEqual(['a', 'b', 'c'])
  })

  it('空输入返回空数组', () => {
    expect(collectColumns([])).toEqual([])
  })
})

describe('isNumericColumn', () => {
  it('数值列为 true', () => {
    expect(isNumericColumn(rows, 'sales_amount')).toBe(true)
  })

  it('字符串维度列为 false', () => {
    expect(isNumericColumn(rows, 'region')).toBe(false)
  })

  it('全是空字符串或 null 的列不是数值列', () => {
    expect(isNumericColumn([{ v: '' }, { v: '  ' }], 'v')).toBe(false)
    expect(isNumericColumn([{ v: null }, { v: null }], 'v')).toBe(false)
  })

  it('混合列（含部分可解析数值）为 true', () => {
    expect(isNumericColumn([{ v: '1' }, { v: 'abc' }], 'v')).toBe(true)
  })
})

describe('候选列', () => {
  it('dimensionCandidates: 非数值列在前，数值列在后并标注（数值）', () => {
    expect(dimensionCandidates(rows)).toEqual([
      { value: 'region', label: 'region' },
      { value: 'sales_amount', label: 'sales_amount（数值）' },
      { value: 'qty', label: 'qty（数值）' },
    ])
  })

  it('metricCandidates: 只含数值列', () => {
    expect(metricCandidates(rows).map((o) => o.value)).toEqual(['sales_amount', 'qty'])
  })
})

describe('chartTypeOptions', () => {
  it('默认不含 hist', () => {
    expect(chartTypeOptions('bar').map((o) => o.value)).toEqual(['bar', 'line', 'pie'])
  })

  it('当前值为 hist 时补入 hist，保证下拉能回显', () => {
    expect(chartTypeOptions('hist').map((o) => o.value)).toEqual(['bar', 'line', 'pie', 'hist'])
  })
})

describe('applyChartEdit', () => {
  const base = { chart_type: 'bar', x: 'region', y: 'sales_amount', series: ['sales_amount'], title: '各区销售额' } as const

  it('改 y 时同步 series 为 [y]', () => {
    const next = applyChartEdit({ ...base, series: [...base.series] }, { y: 'qty' })
    expect(next.y).toBe('qty')
    expect(next.series).toEqual(['qty'])
  })

  it('改 x 只影响 x', () => {
    const next = applyChartEdit({ ...base, series: [...base.series] }, { x: 'qty' })
    expect(next.x).toBe('qty')
    expect(next.y).toBe('sales_amount')
  })

  it('改图型只影响 chart_type', () => {
    const next = applyChartEdit({ ...base, series: [...base.series] }, { chart_type: 'pie' })
    expect(next.chart_type).toBe('pie')
    expect(next.x).toBe('region')
  })

  it('title 不被修改，未传字段保持原值', () => {
    const next = applyChartEdit({ ...base, series: [...base.series] }, { x: 'qty' })
    expect(next.title).toBe('各区销售额')
    expect(next.chart_type).toBe('bar')
  })

  it('不修改入参对象', () => {
    const spec = { ...base, series: [...base.series] }
    applyChartEdit(spec, { y: 'qty' })
    expect(spec.y).toBe('sales_amount')
    expect(spec.series).toEqual(['sales_amount'])
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web && npm run test`
Expected: FAIL —— `Cannot find module './chartColumns'`（模块尚未创建）

- [ ] **Step 3: 写最小实现**

Create `web/src/utils/chartColumns.ts`:

```ts
import type { ChartSpec, Row } from '../types'

export type ChartType = ChartSpec['chart_type']

export interface ChartPatch {
  x?: string | null
  y?: string | null
  chart_type?: ChartType
}

export interface SelectOption {
  value: string
  label: string
}

export function collectColumns(rows: Row[]): string[] {
  const seen: string[] = []
  for (const row of rows) {
    for (const key of Object.keys(row ?? {})) {
      if (!seen.includes(key)) seen.push(key)
    }
  }
  return seen
}

export function isNumericColumn(rows: Row[], col: string): boolean {
  return rows.some((row) => {
    const raw = row?.[col]
    if (raw === null || raw === undefined) return false
    if (String(raw).trim() === '') return false
    return Number.isFinite(Number(raw))
  })
}

export function dimensionCandidates(rows: Row[]): SelectOption[] {
  const cols = collectColumns(rows)
  const numeric = cols.filter((col) => isNumericColumn(rows, col))
  const nonNumeric = cols.filter((col) => !numeric.includes(col))
  return [
    ...nonNumeric.map((col) => ({ value: col, label: col })),
    ...numeric.map((col) => ({ value: col, label: `${col}（数值）` })),
  ]
}

export function metricCandidates(rows: Row[]): SelectOption[] {
  return collectColumns(rows)
    .filter((col) => isNumericColumn(rows, col))
    .map((col) => ({ value: col, label: col }))
}

export function chartTypeOptions(current: ChartType): SelectOption[] {
  const options: SelectOption[] = [
    { value: 'bar', label: '柱状图' },
    { value: 'line', label: '折线图' },
    { value: 'pie', label: '饼图' },
  ]
  if (current === 'hist') options.push({ value: 'hist', label: '直方图' })
  return options
}

export function applyChartEdit(spec: ChartSpec, patch: ChartPatch): ChartSpec {
  const next: ChartSpec = { ...spec, series: [...(spec.series ?? [])] }

  if ('x' in patch) next.x = patch.x ?? null
  if ('y' in patch) {
    next.y = patch.y ?? null
    next.series = patch.y ? [patch.y] : []
  }
  if (patch.chart_type !== undefined) next.chart_type = patch.chart_type

  return next
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd web && npm run test`
Expected: PASS —— 原有 4 条 + 新增 12 条（`collectColumns` 2、`isNumericColumn` 4、候选列 2、`chartTypeOptions` 2、`applyChartEdit` 5，其中部分合并计数）

- [ ] **Step 5: 类型检查**

Run: `cd web && npm run typecheck`
Expected: 无错误输出

- [ ] **Step 6: 提交**

```bash
git add web/src/utils/chartColumns.ts web/src/utils/chartColumns.spec.ts
git commit -m "feat(web): add chart column candidates and spec edit helpers"
```

（若仓库还没有任何 commit，按 Global Constraints 用显式路径提交这两个文件即可，不要 `git add -A`。）

---

### Task 2: 改轴控件组件

**Files:**
- Create: `web/src/components/ChartControls.vue`

**Interfaces:**
- Consumes: Task 1 的 `dimensionCandidates` / `metricCandidates` / `chartTypeOptions` / `ChartPatch` / `SelectOption` / `ChartType`；`types.ts` 的 `ChartSpec`、`Row`
- Produces: 组件 `ChartControls`，props `{ spec: ChartSpec; rows: Row[] }`，emits `change(patch: ChartPatch)`、`reset()` —— Task 3 的 `ChartView` 消费

- [ ] **Step 1: 写组件**

Create `web/src/components/ChartControls.vue`:

```vue
<template>
  <div class="controls">
    <span class="label">X 轴</span>
    <el-select
      size="small"
      :model-value="spec.x ?? ''"
      :disabled="!xOptions.length"
      :placeholder="xOptions.length ? '选择维度列' : '无可选项'"
      style="width: 150px"
      @change="onX"
    >
      <el-option v-for="o in xOptions" :key="o.value" :label="o.label" :value="o.value" />
    </el-select>

    <span class="label">Y 轴</span>
    <el-select
      size="small"
      :model-value="spec.y ?? ''"
      :disabled="!yOptions.length"
      :placeholder="yOptions.length ? '选择指标列' : '无可选项'"
      style="width: 150px"
      @change="onY"
    >
      <el-option v-for="o in yOptions" :key="o.value" :label="o.label" :value="o.value" />
    </el-select>

    <span class="label">图型</span>
    <el-select
      size="small"
      :model-value="spec.chart_type"
      style="width: 110px"
      @change="onType"
    >
      <el-option v-for="o in typeOptions" :key="o.value" :label="o.label" :value="o.value" />
    </el-select>

    <el-button size="small" link :disabled="!canReset" @click="emit('reset')">恢复默认</el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { chartTypeOptions, dimensionCandidates, metricCandidates } from '../utils/chartColumns'
import type { ChartPatch, ChartType } from '../utils/chartColumns'
import type { ChartSpec, Row } from '../types'

const props = defineProps<{ spec: ChartSpec; rows: Row[]; canReset: boolean }>()
const emit = defineEmits<{
  (e: 'change', patch: ChartPatch): void
  (e: 'reset'): void
}>()

const xOptions = computed(() => dimensionCandidates(props.rows))
const yOptions = computed(() => metricCandidates(props.rows))
const typeOptions = computed(() => chartTypeOptions(props.spec.chart_type))

function onX(value: string) {
  emit('change', { x: value })
}

function onY(value: string) {
  emit('change', { y: value })
}

function onType(value: ChartType) {
  emit('change', { chart_type: value })
}
</script>

<style scoped>
.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
```

- [ ] **Step 2: 类型检查**

Run: `cd web && npm run typecheck`
Expected: 无错误输出（`el-select` 的 `@change` 回调参数由 Element Plus 类型推导；若 vue-tsc 报参数类型不匹配，把 `onX` / `onY` 的形参类型显式标为 `string | number | boolean | object` 并在函数体内 `String(value)` 转换）

- [ ] **Step 3: 提交**

```bash
git add web/src/components/ChartControls.vue
git commit -m "feat(web): add chart controls component for x/y/type selection"
```

---

### Task 3: ChartView 集成编辑态

**Files:**
- Modify: `web/src/components/ChartView.vue`

**Interfaces:**
- Consumes: Task 1 的 `applyChartEdit` / `ChartPatch`；Task 2 的 `ChartControls`（props `spec`/`rows`/`canReset`，emits `change`/`reset`）；既有的 `chartSpecToOption`
- Produces: 对外 props 契约**不变**（仍是 `{ spec: ChartSpec; rows: Row[] }`），`AnalysisPage.vue` 无需改动

- [ ] **Step 1: 改造模板与脚本**

把 `web/src/components/ChartView.vue` 的 `<template>` 与 `<script setup>` 替换为下面内容（`render` / `dispose` / `onResize` / 生命周期 / `.chart` 样式保持原样不动）：

```vue
<template>
  <el-card v-if="option" shadow="never">
    <template #header>
      <div class="head">
        <span>图表</span>
        <ChartControls
          :spec="viewSpec"
          :rows="rows"
          :can-reset="isDirty"
          @change="onPatch"
          @reset="onReset"
        />
      </div>
    </template>
    <div ref="chartEl" class="chart"></div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { chartSpecToOption } from '../utils/echarts'
import { applyChartEdit } from '../utils/chartColumns'
import type { ChartPatch } from '../utils/chartColumns'
import ChartControls from './ChartControls.vue'
import type { ChartSpec, Row } from '../types'

const props = defineProps<{ spec: ChartSpec; rows: Row[] }>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function cloneSpec(spec: ChartSpec): ChartSpec {
  return { ...spec, series: [...(spec.series ?? [])] }
}

// AI 产出的 spec 作为默认值；viewSpec 是客户编辑后的渲染依据，不回传后端
const viewSpec = ref<ChartSpec>(cloneSpec(props.spec))
const option = computed(() => chartSpecToOption(viewSpec.value, props.rows))
const isDirty = computed(
  () =>
    viewSpec.value.x !== props.spec.x ||
    viewSpec.value.y !== props.spec.y ||
    viewSpec.value.chart_type !== props.spec.chart_type,
)

watch(
  () => props.spec,
  (spec) => {
    viewSpec.value = cloneSpec(spec)
  },
  { deep: true },
)

function onPatch(patch: ChartPatch) {
  viewSpec.value = applyChartEdit(viewSpec.value, patch)
}

function onReset() {
  viewSpec.value = cloneSpec(props.spec)
}

function dispose() {
  if (chart) {
    chart.dispose()
    chart = null
  }
}

function render() {
  if (!option.value) {
    dispose()
    return
  }
  if (!chartEl.value) return
  chart = chart ?? echarts.init(chartEl.value)
  chart.setOption(option.value, true)
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

watch(option, render)

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  dispose()
})
</script>
```

- [ ] **Step 2: 补 `.head` 样式**

在 `ChartView.vue` 的 `<style scoped>` 中追加（保留原有 `.chart` 规则）：

```css
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
```

- [ ] **Step 3: 类型检查**

Run: `cd web && npm run typecheck`
Expected: 无错误输出

- [ ] **Step 4: 全量前端测试**

Run: `cd web && npm run test`
Expected: PASS（Task 1 的 12 条 + 原有 4 条）

- [ ] **Step 5: 提交**

```bash
git add web/src/components/ChartView.vue
git commit -m "feat(web): let users override chart x/y/type in ChartView"
```

---

### Task 4: 构建、回归与文档

**Files:**
- Modify: `README.md`（第 7 节前端说明的组件表、`chart_spec` v1 说明）

**Interfaces:**
- Consumes: Task 1–3 的全部产出

- [ ] **Step 1: 前端构建**

Run: `cd web && npm run build`
Expected: 构建成功，`web/dist` 产出更新

- [ ] **Step 2: 后端回归**

Run: `python -m pytest tests -q`
Expected: `81 passed`（本次零后端改动，确认无回归）

- [ ] **Step 3: 更新 README 组件表**

在 `README.md` 第 7 节「前端说明」的组件表格中，在 `ChartView.vue` 一行之后追加：

```markdown
| `ChartControls.vue` | 图表卡片头部的 X 轴 / Y 轴 / 图型下拉 +「恢复默认」，改完即时重画（纯前端，不回传后端） |
```

- [ ] **Step 4: 更新 README 的 chart_spec 说明**

在 `README.md` 的 `chart_spec` v1 表格之后追加一句：

```markdown
`chart_spec` 由 `viz/chart.py` 自动推断；客户可在图表卡片头部手动改 X 轴、Y 轴与图型，
改动只在前端生效（即时重画），不回传后端、不重新执行代码。可选的列仅限当前结果表已有的列。
```

- [ ] **Step 5: 手工冒烟**

启动后端（ `uvicorn server.main:app --reload --port 8000` ）与前端（`cd web && npm run dev`），用 `data/sales.csv` 逐项确认：

1. 提问 → 审批 → 完成后，图表卡片头部出现三个下拉 + 「恢复默认」
2. 改 X 轴 → 图表立刻重画，类目轴换成新列
3. 改 Y 轴 → 图表立刻重画，数值换成新列
4. 改图型（柱状 → 折线 → 饼图）→ 图表立刻重画
5. 点「恢复默认」→ 回到 AI 推断的结果
6. 未改动时「恢复默认」为置灰状态
7. 再提交一个新问题 → 控件回到 AI 默认值，不残留上一轮的修改
8. 提问一个 AI 判为「不画图」的问题（`chart_type: none`）→ 图表卡片与控件都不出现

- [ ] **Step 6: 提交**

```bash
git add README.md
git commit -m "docs: document manual chart axis controls"
```

---

## 自查记录

- 规格覆盖：设计文档第 2 节决策记录（纯前端 / 仅限已有列 / X+Y+图型 / 常驻下拉 / series 跟随 y / hist 动态补入）分别对应 Task 1（`chartTypeOptions`、`applyChartEdit`）、Task 2（三个下拉）、Task 3（`viewSpec` + 恢复默认）；第 6 节边界处理（非数值兜底、饼图单系列、无候选列 disabled、轮询刷新重置）分别由 `echarts.ts` 既有兜底、`applyChartEdit` 的 `series = [y]`、`ChartControls` 的 `disabled`、`ChartView` 的 `watch` 覆盖；第 7 节测试与第 8 节验收对应 Task 1 单测与 Task 4。
- 无 TBD / TODO /「类似 Task N」等占位表述，每个代码步骤都给出了完整代码。
- 命名与类型一致性：`ChartPatch` / `SelectOption` / `ChartType` 在 Task 1 定义，Task 2、Task 3 以同名导入；`canReset` 在 Task 2 声明为 prop、Task 3 以 `:can-reset="isDirty"` 传入，两处一致。
