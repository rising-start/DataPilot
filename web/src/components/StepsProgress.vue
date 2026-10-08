<template>
  <div class="steps">
    <div
      v-for="(s, i) in steps"
      :key="s.key"
      class="step"
      :class="s.state"
    >
      <div class="dot">
        <el-icon v-if="s.state === 'done'"><Check /></el-icon>
        <el-icon v-else-if="s.state === 'error'"><Close /></el-icon>
        <span v-else>{{ i + 1 }}</span>
      </div>
      <div class="label">{{ s.label }}</div>
      <div v-if="i < steps.length - 1" class="line" :class="{ filled: s.state === 'done' }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Check, Close } from '@element-plus/icons-vue'
import { computed } from 'vue'
import type { TaskStatus } from '../types'

const props = defineProps<{ status: TaskStatus; stage: string }>()

const ORDER = [
  { key: 'load', label: '加载数据' },
  { key: 'plan', label: '制定方案' },
  { key: 'generate', label: '生成代码' },
  { key: 'execute', label: '执行分析' },
  { key: 'chart', label: '生成图表' },
  { key: 'report', label: '生成报告' },
]

function indexOfStage(stage: string): number {
  switch (stage) {
    case 'load':
      return 0
    case 'plan':
      return 1
    case 'generate':
      return 2
    case 'approval':
      return 2
    case 'execute':
    case 'repair':
      return 3
    case 'chart':
      return 4
    case 'report':
      return 5
    default:
      return -1
  }
}

const steps = computed(() => {
  if (props.status === 'completed') {
    return ORDER.map((s) => ({ ...s, state: 'done' as const }))
  }
  const idx = indexOfStage(props.stage)
  const failed = props.status === 'failed'
  return ORDER.map((s, i) => ({
    ...s,
    state:
      failed && i === idx
        ? ('error' as const)
        : i < idx
          ? ('done' as const)
          : i === idx
            ? ('active' as const)
            : ('pending' as const),
  }))
})
</script>

<style scoped>
.steps {
  display: flex;
  align-items: flex-start;
  padding: 16px 4px 4px;
}

.step {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  text-align: center;
}

.dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 600;
  background: var(--color-surface);
  border: 2px solid var(--color-border);
  color: var(--color-text-3);
  z-index: 1;
  transition: all 0.25s ease;
}

.label {
  font-size: 11px;
  color: var(--color-text-3);
  transition: color 0.25s ease;
}

.line {
  position: absolute;
  top: 13px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: var(--color-border);
  z-index: 0;
}

.line.filled {
  background: var(--color-primary);
}

.step.active .dot {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.12);
}

.step.active .label {
  color: var(--color-primary);
  font-weight: 600;
}

.step.done .dot {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

.step.done .label {
  color: var(--color-text-2);
}

.step.error .dot {
  background: var(--color-danger);
  border-color: var(--color-danger);
  color: #fff;
}

.step.error .label {
  color: var(--color-danger);
}
</style>
