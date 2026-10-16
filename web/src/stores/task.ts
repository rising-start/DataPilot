import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createTask, resumeTask, getTask, cancelTask } from '../api/tasks'
import type { TaskView, TaskStatus } from '../types'

export interface HistoryItem {
  task_id: string
  question: string
  file_name: string
  status: TaskStatus
  created_at: number
  view: TaskView
}

const HISTORY_KEY = 'datapilot_history'
const HISTORY_MAX = 30

function blankTask(taskId: string): TaskView {
  return {
    task_id: taskId,
    thread_id: '',
    status: 'running',
    stage: '',
    tool: '',
    plan: {},
    approval: null,
    artifact_kind: '',
    artifact_code: '',
    rows: [],
    chart_spec: { chart_type: 'none', x: null, y: null, series: [], title: '' },
    insights: [],
    report: '',
    trace: [],
    logs: [],
    memory: {},
    error: '',
  }
}

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? (arr as HistoryItem[]) : []
  } catch {
    return []
  }
}

function saveHistory(items: HistoryItem[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, HISTORY_MAX)))
  } catch {
    /* 存储不可用时静默降级，不影响主流程 */
  }
}

export const useTaskStore = defineStore('task', () => {
  const task = ref<TaskView | null>(null)
  const connected = ref(false)
  const history = ref<HistoryItem[]>(loadHistory())
  let es: EventSource | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null

  function pushHistory(item: HistoryItem) {
    history.value = [item, ...history.value.filter((h) => h.task_id !== item.task_id)].slice(0, HISTORY_MAX)
    saveHistory(history.value)
  }

  function updateHistory(taskId: string, patch: Partial<HistoryItem>) {
    const idx = history.value.findIndex((h) => h.task_id === taskId)
    if (idx >= 0) {
      history.value[idx] = { ...history.value[idx], ...patch }
      saveHistory(history.value)
    }
  }

  function deleteHistory(taskId: string) {
    history.value = history.value.filter((h) => h.task_id !== taskId)
    saveHistory(history.value)
  }

  
  
  function loadHistoryView(view: TaskView) {
    task.value = view
  }

  
  function cleanup() {
    connected.value = false
    if (es) {
      es.close()
      es = null
    }
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  
  function startPolling() {
    if (!task.value) return
    const id = task.value.task_id
    if (pollTimer !== null) return
    pollTimer = setInterval(async () => {
      if (!task.value || task.value.task_id !== id) return
      try {
        const view = await getTask(id)
        const cur = task.value
        if (!cur || cur.task_id !== id) return
        task.value = { ...cur, ...view }
        if (view.status === 'completed' || view.status === 'failed' || view.status === 'cancelled') {
          cleanup()
          updateHistory(id, { status: view.status, view: { ...cur, ...view } })
        }
      } catch {
        cleanup()
      }
    }, 2000)
  }

  function stopStreaming() {
    cleanup()
  }

  
  function stopPolling() {
    cleanup()
  }

  function startStreaming() {
    if (!task.value) return
    cleanup()

    es = new EventSource(`/api/tasks/${task.value.task_id}/events`)
    connected.value = true

    es.onmessage = (e: MessageEvent) => {
      let msg: any
      try {
        msg = JSON.parse(e.data)
      } catch {
        return
      }
      if (msg.type === 'gone') {
        stopStreaming()
        const goneId = task.value?.task_id
        if (goneId) deleteHistory(goneId)
        task.value = null
        ElMessage.error('会话已失效，请重新提交分析。')
        return
      }
      if (msg.type === 'update') {
        const cur = task.value
        if (!cur) return
        if (cur.task_id !== msg.view.task_id) {
          
          updateHistory(msg.view.task_id, { status: msg.view.status, view: msg.view })
          return
        }
        const merged = { ...cur, ...msg.view }
        task.value = merged
        if (
          msg.view.status === 'completed' ||
          msg.view.status === 'failed' ||
          msg.view.status === 'cancelled'
        ) {
          stopStreaming()
          updateHistory(msg.view.task_id, { status: msg.view.status, view: merged })
        }
      }
    }

    es.onerror = () => {
      cleanup()
      
      
      if (
        task.value &&
        (task.value.status === 'running' || task.value.status === 'awaiting_approval')
      ) {
        startPolling()
        ElMessage.warning('实时连接中断，已切换为轮询模式。')
      }
    }
  }

  async function submit(fileId: string, question: string, followup = false, fileName = '') {
    const memory = followup ? task.value?.memory ?? null : null
    const created = await createTask({ file_id: fileId, question, followup, memory })

    task.value = blankTask(created.task_id)
    if (followup && memory) task.value.memory = memory

    pushHistory({
      task_id: created.task_id,
      question,
      file_name: fileName,
      status: 'running',
      created_at: Date.now(),
      view: { ...task.value },
    })

    startStreaming()
  }

  async function decide(approved: boolean, modifiedContent?: string | null) {
    const t = task.value
    if (!t) return
    await resumeTask(t.task_id, approved, modifiedContent)
    task.value = { ...t, status: 'running' }
    updateHistory(t.task_id, { status: 'running' })
  }

  async function cancel() {
    if (!task.value) return
    const id = task.value.task_id
    task.value = { ...task.value, status: 'cancelled', error: '任务已被用户取消' }
    updateHistory(id, { status: 'cancelled' })
    try {
      await cancelTask(id)
    } catch {
      
    }
  }

  return {
    task,
    connected,
    history,
    submit,
    decide,
    cancel,
    loadHistoryView,
    deleteHistory,
    stopStreaming,
    stopPolling,
  }
})
