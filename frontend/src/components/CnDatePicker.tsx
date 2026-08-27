import { DatePicker } from 'antd'
import type { Dayjs } from 'dayjs'
import { parseCnDate, fmtCnDay } from '../utils/cnDate'

/**
 * 日历式选日期，但存/取仍是「2026年5月30日」这种中文串——
 * 库里这几列本来就是字符串，成稿套打也认这个格式，改控件不能改数据。
 * 放进 Form.Item 直接用，表单里拿到的还是字符串。
 */
export default function CnDatePicker({
  value, onChange, placeholder, disabledDate,
}: {
  value?: string
  onChange?: (v: string) => void
  placeholder?: string
  disabledDate?: (d: Dayjs) => boolean
}) {
  return (
    <DatePicker
      style={{ width: '100%' }}
      format="YYYY年M月D日"
      placeholder={placeholder || '选择日期'}
      value={parseCnDate(value)}
      disabledDate={disabledDate}
      onChange={d => onChange?.(fmtCnDay(d))}
    />
  )
}
