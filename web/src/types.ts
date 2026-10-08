// 类型契约：本文件的 TaskView / Approval 接口必须与后端 server/schemas.py 的
// Pydantic 模型字段逐一对应。后端为「单一真源」，由 tests/test_taskview_contract.py
// 校验；修改任一侧字段后须同步另一侧并让该测试通过（防 schema 漂移）。
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

export type TaskStatus = 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled'

export interface TaskView {
  task_id: string
  thread_id: string
  status: TaskStatus
  stage: string
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
