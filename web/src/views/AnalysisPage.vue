<template>
  <div class="layout">
    <aside class="sidebar">
      <FileUpload @uploaded="onUploaded" />
      <QuestionInput
        :file-id="fileId"
        :has-previous="!!store.task"
        :busy="busy"
        @submit="onSubmit"
      />
      <StepsProgress
        v-if="store.task"
        :status="store.task.status"
        :stage="store.task.stage"
      />
      <HistoryList
        :items="store.history"
        :current-id="store.task?.task_id"
        @select="onSelectHistory"
        @delete="onDeleteHistory"
      />
    </aside>

    <section class="workspace">
      <div v-if="banner" class="banner" :class="banner.type">
        <el-icon class="banner-icon"><component :is="banner.icon" /></el-icon>
        <span class="banner-text">{{ banner.text }}</span>
        <el-button
          v-if="store.task?.status === 'running'"
          size="small"
          type="danger"
          plain
          @click="onCancel"
        >
          取消
        </el-button>
      </div>

      <ApprovalCard
        v-if="store.task?.status === 'awaiting_approval' && store.task.approval"
        :approval="store.task.approval"
        :busy="busy"
        @decide="onDecide"
      />

      <div v-if="store.task?.status === 'completed'" class="result fade-up">
        <ChartView :spec="store.task.chart_spec" :rows="store.task.rows" />
        <el-tabs class="tabs" type="border-card">
          <el-tab-pane>
            <template #label><el-icon><Grid /></el-icon> 数据明细</template>
            <ResultTable :rows="store.task.rows" />
          </el-tab-pane>
          <el-tab-pane>
            <template #label><el-icon><MagicStick /></el-icon> 关键发现</template>
            <InsightList :insights="store.task.insights" :report="store.task.report" />
          </el-tab-pane>
          <el-tab-pane>
            <template #label><el-icon><Connection /></el-icon> 执行链路</template>
            <TraceTimeline :trace="store.task.trace" />
          </el-tab-pane>
        </el-tabs>
      </div>

      <div v-if="!store.task" class="placeholder">
        <el-empty description="上传数据文件并输入问题，开始你的分析">
          <template #image>
            <el-icon class="empty-icon"><DataAnalysis /></el-icon>
          </template>
        </el-empty>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Loading,
  Warning,
  CircleClose,
  Grid,
  MagicStick,
  Connection,
  DataAnalysis,
} from '@element-plus/icons-vue'
import ApprovalCard from '../components/ApprovalCard.vue'
import ChartView from '../components/ChartView.vue'
import FileUpload from '../components/FileUpload.vue'
import HistoryList from '../components/HistoryList.vue'
import InsightList from '../components/InsightList.vue'
import QuestionInput from '../components/QuestionInput.vue'
import ResultTable from '../components/ResultTable.vue'
import StepsProgress from '../components/StepsProgress.vue'
import TraceTimeline from '../components/TraceTimeline.vue'
import { useTaskStore } from '../stores/task'
import type { TaskView } from '../types'

const store = useTaskStore()
const fileId = ref<string | null>(null)
const fileName = ref('')

const busy = computed(() => store.task?.status === 'running' || store.task?.status === 'awaiting_approval')

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

const banner = computed(() => {
  const t = store.task
  if (!t) return null
  if (t.status === 'running') {
    return { type: 'info', icon: Loading, text: (t.stage && STAGE_LABELS[t.stage]) || '正在分析，请稍候…' }
  }
  if (t.status === 'cancelled') {
    return { type: 'warning', icon: Warning, text: t.error || '任务已取消' }
  }
  if (t.status === 'failed') {
    return { type: 'error', icon: CircleClose, text: t.error || '分析失败' }
  }
  return null
})

function onUploaded(payload: { id: string; name: string }) {
  fileId.value = payload.id
  fileName.value = payload.name
}

onUnmounted(() => store.stopPolling())

async function onSubmit(question: string, followup: boolean) {
  if (!fileId.value) return
  try {
    await store.submit(fileId.value, question, followup, fileName.value)
  } catch (e: any) {
    ElMessage.error(`提交失败：${e?.message ?? e}`)
  }
}

function onSelectHistory(view: TaskView) {
  store.loadHistoryView(view)
}

function onDeleteHistory(taskId: string) {
  store.deleteHistory(taskId)
}

async function onDecide(approved: boolean) {
  try {
    await store.decide(approved)
  } catch (e: any) {
    ElMessage.error(`操作失败：${e?.message ?? e}`)
  }
}

async function onCancel() {
  try {
    await store.cancel()
    ElMessage.info('已发送取消请求，任务将在当前步骤后停止。')
  } catch (e: any) {
    ElMessage.error(`取消失败：${e?.message ?? e}`)
  }
}
</script>

<style scoped>
.layout {
  display: flex;
  gap: 20px;
  max-width: 1280px;
  margin: 0 auto;
  align-items: flex-start;
}

.sidebar {
  width: 340px;
  flex: 0 0 340px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: sticky;
  top: 88px;
}

.workspace {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  font-size: 14px;
  border: 1px solid transparent;
}

.banner-icon {
  font-size: 18px;
}

.banner-text {
  flex: 1;
}

.banner.info {
  background: var(--color-primary-soft);
  border-color: #d9d6fb;
  color: var(--color-primary-active);
}

.banner.warning {
  background: #fef4e6;
  border-color: #fbe2bd;
  color: var(--color-warning);
}

.banner.error {
  background: #fdecec;
  border-color: #f7c9c9;
  color: var(--color-danger);
}

.placeholder {
  display: grid;
  place-items: center;
  min-height: 420px;
  background: var(--color-surface);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
}

.empty-icon {
  font-size: 64px;
  color: var(--color-primary-light-7, #b9b6f4);
}

.tabs {
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  border: none;
}

.tabs :deep(.el-tabs__header) {
  border-radius: var(--radius-md) var(--radius-md) 0 0;
}

@media (max-width: 980px) {
  .layout {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    flex: none;
    position: static;
  }
}
</style>
