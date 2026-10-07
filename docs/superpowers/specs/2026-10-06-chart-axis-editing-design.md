# DataPilot 图表 X/Y 轴可由客户校正的设计

日期：2026-10-06
状态：待审阅
范围：仅前端 `web/src`。后端（`server/`、`agent/`、`viz/`、`service.py`）零改动。

---

## 1. 背景与目标

`build_chart` 节点由 `viz/chart.py` 依据分析计划自动推断 `chart_spec`（x = 维度列、y/series = 指标列、chart_type 由 plan 决定），客户只能被动接受。当推断不符合预期（例如把 `month` 判成了 X 轴、客户想看按 `region` 的对比）时，当前没有任何干预入口，只能重新提问，代价是再走一遍 LLM + 审批 + 执行。

目标：**在图表上开放 X 轴、Y 轴、图型三项的手动选择**，客户确认 AI 的推断是否正确，不正确就地改掉并立刻看到新图。

关键约束（决定设计形态）：

1. `chart_spec` 是 v1 契约，前端 `chartSpecToOption(spec, rows)` 是渲染的唯一入口，图表完全由「spec + rows」决定 —— 因此改 spec 即可重画，无需后端参与。
2. 结果表 `rows` 已完整下发到前端（`TaskView.rows`），改轴所需的候选列在前端就齐全。
3. 任务完成后前端停止轮询，`props.spec` 稳定，适合在组件内维护编辑态。

## 2. 决策记录

| 决策 | 结论 | 理由 |
|---|---|---|
| 改轴改在哪一层 | **纯前端**，编辑后的 spec 不回传后端 | 零后端改动、零 LLM 消耗、秒级响应；后端状态机与审批流程不受影响 |
| 可选列范围 | **仅限当前结果表已有的列** | 客户已确认；想看结果里没有的维度时重新提问即可 |
| 可编辑字段 | X 轴、Y 轴、图型 | 客户已确认；标题与多指标 series 不在本次范围 |
| 交互形态 | 图表卡片头部**常驻**一行下拉 + 「恢复默认」 | 客户已确认；所见即所得，选完即时重画 |
| Y 轴与 series 的关系 | 改 Y 时同步 `series = [y]`（单系列） | `echarts.ts` 用 `series` 取数、`y` 只作为主指标标记；不同步会导致下拉与图不一致 |
| 图型候选 | 柱状 / 折线 / 饼图；若 AI 给的是 `hist` 则动态补入选项 | `hist` 由前端分箱、不消费 X 轴，默认不暴露；但需保证当前值能在下拉里正确回显 |

## 3. 非目标（YAGNI）

- 不改后端：不动 `chart_spec` v1 契约、不动 `TaskView` / `ChartSpec` 类型、不新增 HTTP 接口、不重新执行代码与 SQL。
- 不支持结果表以外的列（想要新维度 → 重新提问）。
- 不改图表标题；不支持 Y 轴多选多指标（`series` 恒为单元素）。
- 不把客户的改轴结果写入 `memory` 或回传后端（下一轮分析仍以 AI 推断为默认）。
- 不做撤销/重做，只提供「恢复默认」。

## 4. 改动清单

```
web/src/
  utils/chartColumns.ts        新增：候选列与 spec 编辑的纯函数（可单测）
  utils/chartColumns.spec.ts   新增：Vitest 单测
  components/ChartControls.vue 新增：X/Y/图型下拉 + 恢复默认按钮
  components/ChartView.vue     改造：header 挂载控件；内部持有 viewSpec 并改用其渲染
  views/AnalysisPage.vue       不改（ChartView 的 props 契约不变）
  types.ts                     不改
```

## 5. 详细设计

### 5.1 `utils/chartColumns.ts`（纯函数，无 DOM / 无组件依赖）

```ts
export type ChartPatch = {
  x?: string | null
  y?: string | null
  chart_type?: ChartSpec['chart_type']
}

export function collectColumns(rows: Row[]): string[]
export function isNumericColumn(rows: Row[], col: string): boolean
export function dimensionCandidates(rows: Row[]): string[]
export function metricCandidates(rows: Row[]): string[]
export function chartTypeOptions(current: ChartSpec['chart_type']): { value: ChartSpec['chart_type']; label: string }[]
export function applyChartEdit(spec: ChartSpec, patch: ChartPatch): ChartSpec
```

- `collectColumns`：取所有行 key 的并集（与 `ResultTable` 现有「列取所有行的并集」语义一致），保持首次出现顺序。
- `isNumericColumn`：存在至少一个值满足 `v != null && String(v).trim() !== '' && Number.isFinite(Number(v))`。空字符串必须排除（`Number('')` 为 0，会误判为数值列）。
- `dimensionCandidates`：**非数值列在前、数值列在后**（数值列也保留，避免结果全是数值列时无解；UI 上对数值列加「（数值）」后缀提示）。
- `metricCandidates`：仅数值列。
- `chartTypeOptions`：固定 `bar` / `line` / `pie`；当 `current === 'hist'` 时追加 `hist`，保证下拉能正确回显 AI 的当前值。`none` 不进选项（图表此时不渲染）。
- `applyChartEdit`（返回新对象，不改入参）：
  - `patch.x` → 覆盖 `x`
  - `patch.y` → 覆盖 `y`，并同步 `series = [patch.y]`
  - `patch.chart_type` → 覆盖 `chart_type`
  - 未出现在 patch 中的字段保持原值；`title` 永不修改

### 5.2 `components/ChartControls.vue`

- props：`{ spec: ChartSpec; rows: Row[]; canReset: boolean }`（`canReset` 由 `ChartView` 的 `isDirty` 传入，未改动时「恢复默认」置灰）
- emits：`change(patch: ChartPatch)`、`reset()`
- 结构：一行 `el-select`（size="small"）× 3 —— X 轴 / Y 轴 / 图型，加一个「恢复默认」`el-button`（`link` 型）
- 候选为空时 `el-select` 置 `disabled` 且 placeholder 显示「无可选项」
- `chart_type === 'hist'` 时 X 轴下拉额外置 `disabled`，placeholder 显示「直方图不使用 X 轴」——`hist` 由前端分箱、不消费 `x`，开放该下拉会让客户以为改动无效
- 只负责收集选择与回显，不持有编辑态（编辑态在 `ChartView`）

### 5.3 `components/ChartView.vue`

- props 契约不变：仍是 `{ spec: ChartSpec; rows: Row[] }`
- 新增内部状态：

```ts
const viewSpec = ref<ChartSpec>(cloneSpec(props.spec))
const option = computed(() => chartSpecToOption(viewSpec.value, props.rows))
const isDirty = computed(() => 与 props.spec 的 x / y / chart_type / series 存在差异)

watch(() => props.spec, (s) => { viewSpec.value = cloneSpec(s) }, { deep: true })

function cloneSpec(s: ChartSpec) { return { ...s, series: [...(s.series ?? [])] } }
function onPatch(patch: ChartPatch) { viewSpec.value = applyChartEdit(viewSpec.value, patch) }
function onReset() { viewSpec.value = cloneSpec(props.spec) }
```

- 渲染：卡片仍以 `v-if="option"` 为显示条件，控件放在卡片 `#header` 内（左侧「图表」标题、右侧 `ChartControls`，窄屏换行）。因此 `rows` 为空或 `chart_type === 'none'` 时，图表与控件一起不出现 —— 现有行为不变。
- 「恢复默认」在 `!isDirty` 时置灰。

### 5.4 状态重置时机

`stores/task.ts` 提交新一轮时会把 `task` 重置为 `blankTask`（`chart_spec` 为 `none`），`AnalysisPage` 的 `v-if="status === 'completed'"` 使 `ChartView` 重建，`viewSpec` 自然回到 AI 默认值 —— 无需额外重置逻辑。

## 6. 边界处理

| 场景 | 处理 |
|---|---|
| 换 Y 后部分行非数值 | `echarts.ts` 中已有 `Number(r[col]) \|\| 0` 兜底，渲染不崩 |
| X 轴选中数值列 | 类目轴按字符串渲染，可用；下拉中该类列标注「（数值）」 |
| `chart_type === 'hist'` | 该分支由前端分箱、不消费 `x`，故 X 轴下拉置灰并提示「直方图不使用 X 轴」 |
| 多指标 `series` 被改 Y 折叠 | `isDirty` 把 `series` 纳入比较，改回原 Y 仍判定为「已修改」，「恢复默认」可用，系列不会永久丢失 |
| `y` 被置空 | 保留原 `series` 而非清空，避免 `chartSpecToOption` 返回 null 导致整张图连同控件一起消失 |
| 饼图 | 只绘制 `series[0]`；Y 仍为单选，行为与现有 `chartSpecToOption` 一致 |
| 结果无可用的数值列 / 只有 1 列 | 对应下拉 disabled + 「无可选项」 |
| 后端轮询刷新（审批期间） | 任务完成后停止轮询；`watch(props.spec)` 兜底重置编辑态 |

## 7. 测试

**前端（新增 `utils/chartColumns.spec.ts`，沿用 `echarts.spec.ts` 风格）**

- `collectColumns` 取多行列并集、去重、保序
- `isNumericColumn`：普通数值列 true；全空字符串 / 全 null 列 false；混合列（含部分非数值）true
- `dimensionCandidates`：非数值列排在数值列之前
- `metricCandidates`：只含数值列
- `chartTypeOptions`：`hist` 出现时补入选项；默认只含 bar/line/pie
- `applyChartEdit`：改 y 时 series 同步为 `[y]`；不改入参（原对象不变）；未传字段保持原值；title 不被修改

**后端**：`python -m pytest tests -q` 仍为 81 条通过（本次零后端改动，用于确认无回归）。

**手工冒烟**：上传 `data/sales.csv` → 提问 → 批准 → 分别改 X 轴、Y 轴、图型各一次，图表即时重画 → 点「恢复默认」回到 AI 结果 → 再提交一个新问题，控件回到 AI 默认值。

## 8. 验收

1. `cd web && npm run test`、`npm run typecheck`、`npm run build` 全绿
2. `python -m pytest tests -q` 81 条通过
3. 第 7 节手工冒烟全部符合

## 9. 风险

- **低**：改动全部落在新增文件与 `ChartView` 内部，`AnalysisPage` 与后端不受影响；`ChartView` 的对外 props 契约不变，回滚成本仅为删除两个新文件 + 还原 `ChartView`。
- **注意**：客户改轴结果不持久化，刷新页面或提交新一轮后回到 AI 默认 —— 这是有意设计，需在 UI 上不做相反暗示。
