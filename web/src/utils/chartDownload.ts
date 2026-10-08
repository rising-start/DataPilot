// 文件名中的非法字符（跨 Windows / Unix）：\ / : * ? " < > | 及控制字符
const ILLEGAL = /[\\/:*?"<>|\x00-\x1f]/g

export function buildChartFileName(title: string, now: number = Date.now()): string {
  const cleaned = (title ?? '')
    .trim()
    .replace(ILLEGAL, '_')
    .replace(/\.+$/g, '') // 去掉末尾的点（Windows 不允许）
    .replace(/\s+$/g, '') // 去掉末尾空白

  if (!cleaned) {
    const ts = new Date(now).toISOString().replace(/[:.]/g, '-')
    return `图表-${ts}.png`
  }
  return `${cleaned}.png`
}
