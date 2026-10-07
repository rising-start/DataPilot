import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createTask, resumeTask, getTask } from '../api/tasks'
import type { TaskView } from '../types'

function blankTask(taskId: string): TaskView {
  return {
    task_id: taskId,
    thread_id: '',
    status: 'running',
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

export const useTaskStore = defineStore('task', () => {
  const task = ref<TaskView | null>(null)
  const connected = ref(false)
  let es: EventSource | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null

  // 统一清理实时通道：关闭 SSE 连接并停止轮询定时器
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

  // SSE 不可用时的降级：周期性拉取任务最新状态，直至终态或用户离开
  function startPolling() {
    if (!task.value) return
    const id = task.value.task_id
    if (pollTimer !== null) return
    pollTimer = setInterval(async () => {
      if (!task.value || task.value.task_id !== id) return
      try {
        const view = await getTask(id)
        if (!task.value || task.value.task_id !== id) return
        task.value = { ...task.value, ...view }
        if (view.status === 'completed' || view.status === 'failed') {
          cleanup()
        }
      } catch {
        // 任务已失效或服务不可达：停止轮询，避免无效空转
        cleanup()
      }
    }, 2000)
  }

  function stopStreaming() {
    cleanup()
  }

  // 组件卸载时调用：彻底断开实时通道（SSE + 轮询），避免连接泄漏
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
        // 进程重启等导致任务丢失
        stopStreaming()
        task.value = null
        ElMessage.error('会话已失效，请重新提交分析。')
        return
      }
      if (msg.type === 'update') {
        task.value = { ...task.value, ...msg.view }
        if (msg.view.status === 'completed' || msg.view.status === 'failed') {
          stopStreaming()
        }
      }
    }

    es.onerror = () => {
      // EventSource 自动重连在单进程会话下多半仍失败，降级为轮询拉取最新状态
      cleanup()
      if (task.value && task.value.status === 'running') {
        startPolling()
        ElMessage.warning('实时连接中断，已切换为轮询模式。')
      }
    }
  }

  async function submit(fileId: string, question: string, followup = false) {
    const memory = followup ? task.value?.memory ?? null : null
    const created = await createTask({ file_id: fileId, question, followup, memory })

    // 重置为空白任务，避免把上一轮的 trace / approval 带到新一轮
    task.value = blankTask(created.task_id)
    if (followup && memory) task.value.memory = memory

    startStreaming()
  }

  async function decide(approved: boolean) {
    if (!task.value) return
    await resumeTask(task.value.task_id, approved)
    // 流仍在等待中，会收到 running -> completed/failed 的后续更新，无需重建连接
    task.value = { ...task.value, status: 'running' }
  }

  return { task, connected, submit, decide, stopStreaming, stopPolling }
})
