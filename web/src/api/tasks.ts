import axios from 'axios'
import type { TaskView } from '../types'

const http = axios.create({ baseURL: '/api' })

export async function uploadFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post('/files', form)
  return data as { file_id: string; filename: string; source_type: string }
}

export async function createTask(payload: {
  file_id: string
  question: string
  followup?: boolean
  memory?: Record<string, any> | null
}) {
  const { data } = await http.post('/tasks', payload)
  return data as { task_id: string; status: string }
}

export async function getTask(taskId: string) {
  const { data } = await http.get(`/tasks/${taskId}`)
  return data as TaskView
}

export async function resumeTask(taskId: string, approved: boolean) {
  const { data } = await http.post(`/tasks/${taskId}/resume`, { approved })
  return data as { task_id: string; status: string }
}

export async function cancelTask(taskId: string) {
  const { data } = await http.delete(`/tasks/${taskId}`)
  return data as { deleted: boolean; cancelled?: boolean }
}
