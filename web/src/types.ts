export type Row = Record<string, any>

export interface ChartSpec {
  chart_type: 'bar' | 'line' | 'pie' | 'hist' | 'none'
  x: string | null
  y: string | null
  series: string[]
  title: string
}

export interface Approval {
  kind: string
  title: string
  content: string
  language: 'sql' | 'python'
}

export type TaskStatus = 'running' | 'awaiting_approval' | 'completed' | 'failed'

export interface TaskView {
  task_id: string
  thread_id: string
  status: TaskStatus
  tool: string
  plan: Record<string, any>
  approval: Approval | null
  artifact_kind: string
  artifact_code: string
  rows: Row[]
  chart_spec: ChartSpec
  insights: string[]
  report: string
  trace: Record<string, any>[]
  logs: string[]
  memory: Record<string, any>
  error: string
}
