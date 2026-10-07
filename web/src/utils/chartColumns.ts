import type { ChartSpec, Row } from '../types'

export type ChartType = ChartSpec['chart_type']

export interface ChartPatch {
  x?: string | null
  y?: string | null
  chart_type?: ChartType
}

export interface SelectOption {
  value: string
  label: string
}

export function collectColumns(rows: Row[]): string[] {
  const seen: string[] = []
  for (const row of rows) {
    for (const key of Object.keys(row ?? {})) {
      if (!seen.includes(key)) seen.push(key)
    }
  }
  return seen
}

export function isNumericColumn(rows: Row[], col: string): boolean {
  return rows.some((row) => {
    const raw = row?.[col]
    if (raw === null || raw === undefined) return false
    if (String(raw).trim() === '') return false
    return Number.isFinite(Number(raw))
  })
}

export function dimensionCandidates(rows: Row[]): SelectOption[] {
  const cols = collectColumns(rows)
  const numeric = cols.filter((col) => isNumericColumn(rows, col))
  const nonNumeric = cols.filter((col) => !numeric.includes(col))
  return [
    ...nonNumeric.map((col) => ({ value: col, label: col })),
    ...numeric.map((col) => ({ value: col, label: `${col}（数值）` })),
  ]
}

export function metricCandidates(rows: Row[]): SelectOption[] {
  return collectColumns(rows)
    .filter((col) => isNumericColumn(rows, col))
    .map((col) => ({ value: col, label: col }))
}

export function chartTypeOptions(current: ChartType): SelectOption[] {
  const options: SelectOption[] = [
    { value: 'bar', label: '柱状图' },
    { value: 'line', label: '折线图' },
    { value: 'pie', label: '饼图' },
  ]
  if (current === 'hist') options.push({ value: 'hist', label: '直方图' })
  return options
}

export function applyChartEdit(spec: ChartSpec, patch: ChartPatch): ChartSpec {
  const next: ChartSpec = { ...spec, series: [...(spec.series ?? [])] }

  if (patch.x !== undefined) next.x = patch.x
  if (patch.y !== undefined) {
    next.y = patch.y
    // y 为空时保留原 series：清空 series 会让 chartSpecToOption 返回 null，
    // 整张图连同卡片头部的控件一起消失，客户将无法再改回来
    if (next.y) next.series = [next.y]
  }
  if (patch.chart_type !== undefined) next.chart_type = patch.chart_type

  return next
}
