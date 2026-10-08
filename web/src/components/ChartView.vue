<template>
  <el-card v-if="option" shadow="never">
    <template #header>
      <div class="head">
        <el-icon class="card-icon"><PieChart /></el-icon>
        <span>可视化</span>
        <ChartControls
          :spec="viewSpec"
          :rows="rows"
          :can-reset="isDirty"
          @change="onPatch"
          @reset="onReset"
        />
        <el-button size="small" :icon="Download" :disabled="!option" @click="downloadChart">
          下载图片
        </el-button>
        </div>
    </template>
    <div ref="chartEl" class="chart"></div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from '../utils/echartsCore'
import { chartSpecToOption } from '../utils/echarts'
import { applyChartEdit } from '../utils/chartColumns'
import type { ChartPatch } from '../utils/chartColumns'
import ChartControls from './ChartControls.vue'
import { Download, PieChart } from '@element-plus/icons-vue'
import { buildChartFileName } from '../utils/chartDownload'
import type { ChartSpec, Row } from '../types'

const props = defineProps<{ spec: ChartSpec; rows: Row[] }>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function cloneSpec(spec: ChartSpec): ChartSpec {
  return { ...spec, series: [...(spec.series ?? [])] }
}

function sameSeries(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, i) => value === b[i])
}

// AI 产出的 spec 作为默认值；viewSpec 是客户编辑后的渲染依据，不回传后端
const viewSpec = ref<ChartSpec>(cloneSpec(props.spec))
const option = computed(() => chartSpecToOption(viewSpec.value, props.rows))
// series 也要参与比较：改 Y 会把 series 折叠为单元素，
// 若只看 x/y/chart_type，改回原值时会被判为「未修改」而让多出来的系列无法恢复
const isDirty = computed(
  () =>
    viewSpec.value.x !== props.spec.x ||
    viewSpec.value.y !== props.spec.y ||
    viewSpec.value.chart_type !== props.spec.chart_type ||
    !sameSeries(viewSpec.value.series ?? [], props.spec.series ?? []),
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

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.chart {
  width: 100%;
  height: 400px;
  animation: fadeUp 0.4s ease both;
}
</style>
