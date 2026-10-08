import { describe, expect, it } from 'vitest'
import { buildChartFileName } from './chartDownload'

describe('buildChartFileName', () => {
  it('普通标题追加 .png 并清洗非法字符', () => {
    expect(buildChartFileName('销售分析 / 2026')).toBe('销售分析 _ 2026.png')
  })

  it('去除首尾空格与末尾点', () => {
    expect(buildChartFileName('  周报 . ')).toBe('周报.png')
  })

  it('空标题回退为 图表-<时间戳>.png', () => {
    const name = buildChartFileName('', 1_700_000_000_000)
    expect(name.startsWith('图表-')).toBe(true)
    expect(name.endsWith('.png')).toBe(true)
  })

  it('仅含非法字符时替换为下划线并保留 .png', () => {
    expect(buildChartFileName('///')).toBe('___.png')
  })
})
