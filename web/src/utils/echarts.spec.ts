import { describe, expect, it } from 'vitest'
import { chartSpecToOption } from './echarts'

const rows = [
  { channel: '线上', sales_amount: 10 },
  { channel: '线下', sales_amount: 20 },
]

describe('chartSpecToOption', () => {
  it('bar: x 为类目轴，series 取 spec.series', () => {
    const option = chartSpecToOption(
      { chart_type: 'bar', x: 'channel', y: 'sales_amount', series: ['sales_amount'], title: 't' },
      rows,
    )
    expect(option!.series[0].type).toBe('bar')
    expect(option!.xAxis.data).toEqual(['线上', '线下'])
    expect(option!.series[0].data).toEqual([10, 20])
  })

  it('pie: data 为 {name,value}', () => {
    const option = chartSpecToOption(
      { chart_type: 'pie', x: 'channel', y: 'sales_amount', series: ['sales_amount'], title: 't' },
      rows,
    )
    expect(option!.series[0].data[0]).toEqual({ name: '线上', value: 10 })
  })

  it('hist: 对数值列分箱', () => {
    const option = chartSpecToOption(
      { chart_type: 'hist', x: null, y: 'sales_amount', series: ['sales_amount'], title: 't' },
      [{ sales_amount: 1 }, { sales_amount: 2 }, { sales_amount: 3 }],
    )
    expect(option!.series[0].type).toBe('bar')
    expect(option!.series[0].data.length).toBeGreaterThan(0)
  })

  it('none / 空数据返回 null', () => {
    expect(
      chartSpecToOption({ chart_type: 'none', x: 'a', y: 'b', series: [], title: '' }, rows),
    ).toBeNull()
    expect(
      chartSpecToOption(
        { chart_type: 'bar', x: 'channel', y: 'sales_amount', series: ['sales_amount'], title: '' },
        [],
      ),
    ).toBeNull()
  })
})
