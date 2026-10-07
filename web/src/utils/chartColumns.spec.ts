import { describe, expect, it } from 'vitest'
import {
  applyChartEdit,
  chartTypeOptions,
  collectColumns,
  dimensionCandidates,
  isNumericColumn,
  metricCandidates,
} from './chartColumns'

const rows = [
  { region: '华东', sales_amount: 10, qty: 2 },
  { region: '华南', sales_amount: 20, qty: 3 },
]

describe('collectColumns', () => {
  it('取所有行 key 的并集，去重并保持首次出现顺序', () => {
    expect(
      collectColumns([
        { a: 1, b: 2 },
        { b: 3, c: 4 },
      ]),
    ).toEqual(['a', 'b', 'c'])
  })

  it('空输入返回空数组', () => {
    expect(collectColumns([])).toEqual([])
  })
})

describe('isNumericColumn', () => {
  it('数值列为 true', () => {
    expect(isNumericColumn(rows, 'sales_amount')).toBe(true)
  })

  it('字符串维度列为 false', () => {
    expect(isNumericColumn(rows, 'region')).toBe(false)
  })

  it('全是空字符串或 null 的列不是数值列', () => {
    expect(isNumericColumn([{ v: '' }, { v: '  ' }], 'v')).toBe(false)
    expect(isNumericColumn([{ v: null }, { v: null }], 'v')).toBe(false)
  })

  it('混合列（含部分可解析数值）为 true', () => {
    expect(isNumericColumn([{ v: '1' }, { v: 'abc' }], 'v')).toBe(true)
  })
})

describe('候选列', () => {
  it('dimensionCandidates: 非数值列在前，数值列在后并标注（数值）', () => {
    expect(dimensionCandidates(rows)).toEqual([
      { value: 'region', label: 'region' },
      { value: 'sales_amount', label: 'sales_amount（数值）' },
      { value: 'qty', label: 'qty（数值）' },
    ])
  })

  it('metricCandidates: 只含数值列', () => {
    expect(metricCandidates(rows).map((o) => o.value)).toEqual(['sales_amount', 'qty'])
  })

  it('没有可用数值列时 metricCandidates 为空（下拉置灰的依据）', () => {
    const textOnly = [{ region: '华东' }, { region: '华南' }]
    expect(metricCandidates(textOnly)).toEqual([])
    expect(dimensionCandidates(textOnly).map((o) => o.value)).toEqual(['region'])
  })
})

describe('chartTypeOptions', () => {
  it('默认不含 hist', () => {
    expect(chartTypeOptions('bar').map((o) => o.value)).toEqual(['bar', 'line', 'pie'])
  })

  it('none 不进选项（此时图表不渲染）', () => {
    expect(chartTypeOptions('none').map((o) => o.value)).toEqual(['bar', 'line', 'pie'])
  })

  it('当前值为 hist 时补入 hist，保证下拉能回显', () => {
    expect(chartTypeOptions('hist').map((o) => o.value)).toEqual(['bar', 'line', 'pie', 'hist'])
  })
})

describe('applyChartEdit', () => {
  const base = {
    chart_type: 'bar',
    x: 'region',
    y: 'sales_amount',
    series: ['sales_amount'],
    title: '各区销售额',
  } as const

  it('改 y 时同步 series 为 [y]', () => {
    const next = applyChartEdit({ ...base, series: [...base.series] }, { y: 'qty' })
    expect(next.y).toBe('qty')
    expect(next.series).toEqual(['qty'])
  })

  it('改 x 只影响 x', () => {
    const next = applyChartEdit({ ...base, series: [...base.series] }, { x: 'qty' })
    expect(next.x).toBe('qty')
    expect(next.y).toBe('sales_amount')
  })

  it('改图型只影响 chart_type', () => {
    const next = applyChartEdit({ ...base, series: [...base.series] }, { chart_type: 'pie' })
    expect(next.chart_type).toBe('pie')
    expect(next.x).toBe('region')
  })

  it('title 不被修改，未传字段保持原值', () => {
    const next = applyChartEdit({ ...base, series: [...base.series] }, { x: 'qty' })
    expect(next.title).toBe('各区销售额')
    expect(next.chart_type).toBe('bar')
  })

  it('不修改入参对象', () => {
    const spec = { ...base, series: [...base.series] }
    applyChartEdit(spec, { y: 'qty' })
    expect(spec.y).toBe('sales_amount')
    expect(spec.series).toEqual(['sales_amount'])
  })

  it('改 x / chart_type 时 series 保持原值（多指标不被折叠）', () => {
    const spec = { ...base, series: ['sales_amount', 'qty'] }
    expect(applyChartEdit(spec, { x: 'qty' }).series).toEqual(['sales_amount', 'qty'])
    expect(applyChartEdit(spec, { chart_type: 'line' }).series).toEqual(['sales_amount', 'qty'])
  })

  it('y 置空时保留原 series，避免图表整体消失', () => {
    const next = applyChartEdit({ ...base, series: ['sales_amount', 'qty'] }, { y: null })
    expect(next.y).toBeNull()
    expect(next.series).toEqual(['sales_amount', 'qty'])
  })
})
