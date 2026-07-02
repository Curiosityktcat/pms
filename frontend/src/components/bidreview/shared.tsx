import { Tag } from 'antd'
import { LOT_COMMON } from '../../services/bidReview'

export const TASK_STATUS_CN: Record<string, { label: string; color: string }> = {
  draft:          { label: '待上传采购文件', color: 'default' },
  ocr_proc_doc:   { label: '识别采购文件中', color: 'processing' },
  extracting:     { label: 'AI 抽取条目中', color: 'processing' },
  criteria_ready: { label: '条目待确认/审查中', color: 'blue' },
  done:           { label: '审查完成', color: 'green' },
  failed:         { label: '处理失败', color: 'red' },
}

export const RESULT_STATUS_CN: Record<string, { label: string; color: string }> = {
  pending: { label: '待审查', color: 'default' },
  running: { label: '审查中', color: 'processing' },
  done:    { label: '已完成', color: 'green' },
  failed:  { label: '失败', color: 'red' },
}

export function verdictTag(v: string) {
  if (v === '满足') return <Tag color="green">满足</Tag>
  if (v === '不满足') return <Tag color="red">不满足</Tag>
  return <Tag color="orange">未找到</Tag>
}

export function lotTag(lot: string) {
  return lot && lot !== LOT_COMMON
    ? <Tag color="blue">包{lot}</Tag>
    : <Tag>通用</Tag>
}

const CAT_COLOR: Record<string, string> = {
  资格: 'geekblue', 实质性: 'volcano', 商务: 'purple', 打分: 'gold',
}

export function catTag(c: string) {
  return <Tag color={CAT_COLOR[c] || 'default'}>{c}</Tag>
}

export function getErr(err: unknown, fallback: string) {
  return (err as { response?: { data?: { error?: string } } })?.response?.data?.error || fallback
}
