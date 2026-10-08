<template>
  <div class="history">
    <div class="history-head">
      <span class="title">分析记录</span>
      <span class="count">{{ items.length }}</span>
    </div>
    <div v-if="!items.length" class="empty">暂无记录，提交分析后会出现在这里</div>
    <ul v-else class="list">
      <li
        v-for="h in items"
        :key="h.task_id"
        class="item"
        :class="{ active: h.task_id === currentId }"
        @click="$emit('select', h.view)"
      >
        <div class="q" :title="h.question">{{ h.question }}</div>
        <div class="meta">
          <el-tag size="small" :type="statusType(h.status)" effect="light">
            {{ statusLabel(h.status) }}
          </el-tag>
          <span class="time">{{ formatTime(h.created_at) }}</span>
          <el-icon class="del" title="删除记录" @click.stop="$emit('delete', h.task_id)">
            <Delete />
          </el-icon>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { Delete } from '@element-plus/icons-vue'
import type { TaskStatus, TaskView } from '../types'

export interface HistoryItem {
  task_id: string
  question: string
  file_name: string
  status: TaskStatus
  created_at: number
  view: TaskView
}

const props = defineProps<{ items: HistoryItem[]; currentId?: string }>()
defineEmits<{ (e: 'select', view: TaskView): void; (e: 'delete', taskId: string): void }>()

function statusType(s: TaskStatus): 'success' | 'info' | 'warning' | 'danger' | 'primary' {
  switch (s) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'cancelled':
      return 'warning'
    case 'awaiting_approval':
      return 'primary'
    default:
      return 'info'
  }
}

function statusLabel(s: TaskStatus): string {
  switch (s) {
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'cancelled':
      return '已取消'
    case 'awaiting_approval':
      return '待审批'
    default:
      return '分析中'
  }
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<style scoped>
.history {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: 14px;
}

.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.history-head .title {
  font-weight: 600;
  font-size: 14px;
}

.history-head .count {
  font-size: 12px;
  color: var(--color-text-3);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0 8px;
  min-width: 22px;
  text-align: center;
}

.empty {
  font-size: 12px;
  color: var(--color-text-3);
  line-height: 1.6;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow: auto;
}

.item {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.item:hover {
  border-color: var(--color-primary-light-7, #b9b6f4);
  background: var(--color-surface-2);
}

.item.active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.q {
  font-size: 13px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 8px;
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.time {
  font-size: 11px;
  color: var(--color-text-3);
}

.del {
  margin-left: auto;
  color: var(--color-text-3);
  cursor: pointer;
  transition: color 0.18s ease;
}

.del:hover {
  color: var(--color-danger);
}
</style>
