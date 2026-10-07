<template>
  <div class="controls">
    <span class="label">X 轴</span>
    <el-select
      size="small"
      :model-value="spec.x ?? ''"
      :disabled="xDisabled"
      :placeholder="xPlaceholder"
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

// 直方图由前端对数值列分箱，不消费 X 轴（见 utils/echarts.ts 的 hist 分支），
// 此时开放 X 下拉会让客户以为改动无效
const xDisabled = computed(() => !xOptions.value.length || props.spec.chart_type === 'hist')
const xPlaceholder = computed(() => {
  if (props.spec.chart_type === 'hist') return '直方图不使用 X 轴'
  return xOptions.value.length ? '选择维度列' : '无可选项'
})

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
