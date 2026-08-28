/**
 * 时间显示统一工具 — 全站按北京时间（UTC+8）展示。
 *
 * 后端接口输出的时间已经是「不带时区偏移的北京时间」，例如
 * `2026-08-29T02:38:36.031102`（由 LocalTimezoneMiddleware 统一换算）。
 * 本工具主要在两种场景下兜底：
 *   1. 无偏移字符串：后端已按北京时间输出，直接按原样格式化，
 *      避免 dayjs / new Date 再按浏览器时区二次解释（跨时区访问时会错 8 小时）。
 *   2. 带偏移字符串（历史数据或第三方来源）：先换算到 UTC+8 再格式化。
 */

const BEIJING_OFFSET_MINUTES = 8 * 60

const ISO_RE =
  /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?\s*(Z|z|[+-]\d{2}:?\d{2})?$/

/**
 * 把任意时间字符串换算成「北京时间」的无偏移形式
 * `YYYY-MM-DDTHH:mm:ss.SSS`；无法解析时返回 null。
 */
export function toBeijingTime(value?: string | null): string | null {
  if (!value) return null
  const raw = String(value).trim()
  if (!raw) return null

  const m = raw.match(ISO_RE)
  if (!m) return null

  const [, datePart, timePart, fracRaw, offsetRaw] = m
  const frac = (fracRaw || '000').slice(0, 3).padEnd(3, '0')

  // 无偏移：后端已按北京时间输出，直接用
  if (!offsetRaw) {
    return `${datePart}T${timePart}.${frac}`
  }

  // 有偏移：换算到 UTC+8
  let offsetMinutes = 0
  if (offsetRaw !== 'Z' && offsetRaw !== 'z') {
    const sign = offsetRaw[0] === '-' ? -1 : 1
    const digits = offsetRaw.slice(1).replace(':', '')
    const hh = parseInt(digits.slice(0, 2), 10)
    const mm = parseInt(digits.slice(2, 4), 10)
    offsetMinutes = sign * (hh * 60 + mm)
  }

  // 用 UTC 毫秒数做加减，避免浏览器本地时区干扰
  const baseMs = Date.UTC(
    Number(datePart.slice(0, 4)),
    Number(datePart.slice(5, 7)) - 1,
    Number(datePart.slice(8, 10)),
    Number(timePart.slice(0, 2)),
    Number(timePart.slice(3, 5)),
    Number(timePart.slice(6, 8)),
    Number(frac)
  )
  const beijingMs = baseMs - offsetMinutes * 60_000 + BEIJING_OFFSET_MINUTES * 60_000
  const d = new Date(beijingMs)

  const pad = (n: number, len = 2) => String(n).padStart(len, '0')
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}` +
    `.${pad(d.getUTCMilliseconds(), 3)}`
  )
}

/** 格式化时间为北京时间字符串，默认 `YYYY-MM-DD HH:mm:ss`。 */
export function formatTime(
  value?: string | null,
  length: 'date' | 'minute' | 'second' | 'short' = 'second'
): string {
  const beijing = toBeijingTime(value)
  if (!beijing) return '-'
  const [datePart, timePart = '00:00:00'] = beijing.split('T')
  if (length === 'date') return datePart
  if (length === 'minute') return `${datePart} ${timePart.slice(0, 5)}`
  if (length === 'short') return `${datePart.slice(5)} ${timePart.slice(0, 5)}`
  return `${datePart} ${timePart.slice(0, 8)}`
}

/** 直接截取显示（等价 formatTime 的 second 精度）。 */
export function fmtTime(value?: string | null): string {
  return formatTime(value, 'second')
}
