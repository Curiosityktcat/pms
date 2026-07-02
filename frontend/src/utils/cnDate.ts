import dayjs from 'dayjs'

// ── 中文日期串 ↔ dayjs ──────────────────────────────────────────────
// DatePicker 用 dayjs；存库统一中文串（"2026年6月1日" / "2026年6月20日15:00"），
// 以兼容 Word 生成与各处「开标时间」抓取正则（要求 年月日时之间无空格）。
export function parseCnDate(s?: string): dayjs.Dayjs | null {
  if (!s) return null
  const m = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:(\d{1,2})\s*[：:]\s*(\d{2}))?/)
  if (!m) return null
  const d = dayjs(new Date(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 0, m[5] ? +m[5] : 0))
  return d.isValid() ? d : null
}

export function fmtCnDay(d?: dayjs.Dayjs | null): string {
  return d ? d.format('YYYY年M月D日') : ''
}

export function fmtCnDateTime(d?: dayjs.Dayjs | null): string {
  return d ? d.format('YYYY年M月D日HH:mm') : ''
}
