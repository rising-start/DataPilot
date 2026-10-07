import type { ChartSpec, Row } from '../types'

export function chartSpecToOption(spec: ChartSpec, rows: Row[]): Record<string, any> | null {
  if (!spec || spec.chart_type === 'none' || !rows.length) return null

  const seriesCols = (spec.series || []).filter(Boolean)
  if (!seriesCols.length) return null

  const title = { text: spec.title || '' }

  if (spec.chart_type === 'pie') {
    const col = seriesCols[0]
    return {
      title,
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: '60%',
          data: rows.map((r) => ({
            name: String(r[spec.x ?? ''] ?? ''),
            value: Number(r[col]) || 0,
          })),
        },
      ],
    }
  }

  if (spec.chart_type === 'hist') {
    const values = rows
      .map((r) => Number(r[seriesCols[0]]))
      .filter((v) => Number.isFinite(v))
    if (!values.length) return null

    const min = Math.min(...values)
    const max = Math.max(...values)
    const bins = Math.max(1, Math.ceil(Math.log2(values.length) + 1))
    const width = (max - min) / bins || 1
    const counts = new Array(bins).fill(0)
    values.forEach((v) => {
      const idx = Math.min(bins - 1, Math.floor((v - min) / width))
      counts[idx] += 1
    })

    return {
      title,
      tooltip: {},
      xAxis: {
        type: 'category',
        data: counts.map((_, i) => (min + i * width).toFixed(2)),
      },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: counts }],
    }
  }

  return {
    title,
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: rows.map((r) => String(r[spec.x ?? ''] ?? '')),
    },
    yAxis: { type: 'value' },
    series: seriesCols.map((col) => ({
      name: col,
      type: spec.chart_type === 'line' ? 'line' : 'bar',
      data: rows.map((r) => Number(r[col]) || 0),
    })),
  }
}
