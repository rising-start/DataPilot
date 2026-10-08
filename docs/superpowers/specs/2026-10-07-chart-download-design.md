# 图表下载功能设计（2026-10-07）

## 背景
当前 `ChartView.vue` 用 ECharts 在浏览器渲染图表，但没有任何方式把图表保存为图片。
用户希望「可以选择是否下载」——即在图表头部提供一个「下载图片」按钮，点击即把当前
图表导出为 PNG，不点则不下载。

## 目标
- 在图表卡片头部新增「下载图片」按钮。
- 点击后导出**当前屏幕上显示的图表**（含用户在 ChartControls 上的手动调整）为 PNG。
- 不自动下载，不接后端，不加全局开关。

## 非目标（YAGNI）
- 不引入后端图片生成 / 文件接口。
- 不做 html-to-image / dom 截图。
- 不做「自动下载」开关。
- 不改动 `ChartControls.vue` 的职责。

## 方案
纯前端实现，利用 ECharts 实例已有的 `getDataURL` 方法。

### 改动文件
`web/src/components/ChartView.vue`

### 组件结构
卡片头部目前为：
```
[ 图表 ]  <ChartControls ... />
```
改为：
```
[ 图表 ]  <ChartControls ... />   [ 下载图片 按钮 ]
```

### 关键逻辑
1. 在 `<script setup>` 中新增 `downloadChart()`：
   - 若 `chart` 为 null（未渲染）直接 return。
   - 调用 `chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' })`
     得到 PNG 的 data URL（`pixelRatio: 2` 保证清晰度，`backgroundColor` 避免透明背景）。
   - 创建临时 `<a :href="dataURL" download="文件名" />`，触发 `click()`。
   - 文件名：取 `spec.title` 去掉非法字符后作为前缀；为空则回退 `图表-<时间戳>`。
2. 按钮使用 `el-button`，带下载图标，`@click="downloadChart"`。
3. 按钮 `:disabled="!option"`（无图表时不渲染/不可点）。

### 数据流
```
用户点击「下载图片」
  → downloadChart()
  → chart.getDataURL(png) → dataURL
  → 创建 <a download> 触发下载
```
`chart` 是 `ChartView.vue` 模块级变量，无需向子组件传递。

## 验证
1. `npm run dev` 启动前端。
2. 运行一次分析，生成图表后点「下载图片」。
3. 确认浏览器下载了一张 PNG，且内容与屏幕图表一致（含手动调整后的样式）。
4. 将图表调整为 `none`（无图）或确认空数据时，按钮处于禁用状态。
5. `npm run test`（或前端单测）确认无回归。

## 风险 / 注意
- `getDataURL` 对 canvas 渲染器有效（当前默认即 canvas），无需额外配置。
- 直接使用 data URL 作为 `<a href>` 在大多数浏览器可用，无需 Blob 转换。
