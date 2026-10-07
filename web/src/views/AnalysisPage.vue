<template>
  <div class="page">
    <div class="top">
      <FileUpload @uploaded="onUploaded" />
      <QuestionInput
        :file-id="fileId"
        :has-previous="!!store.task"
        :busy="busy"
        @submit="onSubmit"
      />
    </div>

    <el-alert
      v-if="store.task?.status === 'running'"
      type="info"
      :closable="false"
      :title="stageLabel"
    />

    <el-alert
      v-if="store.task?.status === 'failed'"
      type="error"
      :closable="false"
      :title="store.task.error || '分析失败'"
    />

    <ApprovalCard
      v-if="store.task?.status === 'awaiting_approval' && store.task.approval"
      :approval="store.task.approval"
      :busy="busy"
      @decide="onDecide"
    />

    <template v-if="store.task?.status === 'completed'">
      <ChartView :spec="store.task.chart_spec" :rows="store.task.rows" />
      <ResultTable :rows="store.task.rows" />
      <InsightList :insights="store.task.insights" :report="store.task.report" />
    </template>

    <TraceTimeline v-if="store.task?.trace?.length" :trace="store.task.trace" />
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ApprovalCard from '../components/ApprovalCard.vue'
import ChartView from '../components/ChartView.vue'
import FileUpload from '../components/FileUpload.vue'
import InsightList from '../components/InsightList.vue'
import QuestionInput from '../components/QuestionInput.vue'
import ResultTable from '../components/ResultTable.vue'
import TraceTimeline from '../components/TraceTimeline.vue'
import { useTaskStore } from '../stores/task'

const store = useTaskStore()
const fileId = ref<string | null>(null)

const busy = computed(() => store.task?.status === 'running')

const STAGE_LABELS: Record<string, string> = {
  load: '正在加载数据…',
  plan: '正在制定分析方案…',
  generate: '正在生成分析代码…',
  approval: '等待审批…',
  execute: '正在执行分析…',
  repair: '正在修复代码…',
  chart: '正在生成图表…',
  report: '正在生成报告…',
}

const stageLabel = computed(() => {
  const s = store.task?.stage
  return (s && STAGE_LABELS[s]) || '正在分析，请稍候…'
})

function onUploaded(id: string) {
  fileId.value = id
}

onUnmounted(() => store.stopPolling())

async function onSubmit(question: string, followup: boolean) {
  if (!fileId.value) return
  try {
    await store.submit(fileId.value, question, followup)
  } catch (e: any) {
    ElMessage.error(`提交失败：${e?.message ?? e}`)
  }
}

async function onDecide(approved: boolean) {
  try {
    await store.decide(approved)
  } catch (e: any) {
    ElMessage.error(`操作失败：${e?.message ?? e}`)
  }
}
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1100px;
  margin: 0 auto;
}

.top {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 16px;
}

@media (max-width: 900px) {
  .top {
    grid-template-columns: 1fr;
  }
}
</style>
