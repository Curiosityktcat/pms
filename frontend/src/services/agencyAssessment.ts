import api from './api'

export interface AssessItem {
  key: string
  name: string
  standard: string
  auto: boolean
  auto_score: number | null   // 系统算出的建议分（null=算不出）
  auto_basis: string          // 建议分的依据，写清楚为什么是这个分
  score: number
  note: string
  // 三项时效（编制/拟合同/归档）才有：起止日期可手填，填了就按手填的算分
  date_start?: string
  date_end?: string
  date_source?: 'manual' | 'auto' | 'none'
  start_label?: string
  end_label?: string
  auto_hint?: string
}

// {"archive_speed": {"start": "2026-06-01", "end": "2026-06-03"}, ...}
export type AssessDates = Record<string, { start?: string; end?: string }>

export interface VetoItem { key: string; name: string }

export interface Assessment {
  id: number | null
  project_id: number
  project_number: string
  project_name: string
  agency_code: string
  agency_name: string
  items: AssessItem[]
  veto: string[]
  veto_note: string
  dates?: AssessDates
  veto_hit?: number
  subj_timeliness: string
  subj_ability: string
  subj_attitude: string
  comment: string
  total_score: number
  status: '草稿' | '已提交'
  assessor?: string
  assessed_at?: string
}

export interface AssessMeta {
  items: { key: string; name: string; standard: string; auto: boolean }[]
  veto_items: VetoItem[]
  subj_options: string[]
  ladder_items?: Record<string, { start_label: string; end_label: string; auto_hint: string }>
  thresholds: { pass_line: number; bonus_line: number; suspend_line: number; valid_months: number }
  can_assess: boolean
}

export interface AgencySummary {
  agency_code: string
  agency_name: string
  count: number
  avg: number | null
  net: number          // 近 N 月加扣分净额
  veto: number
  below_count?: number
  flags: string[]
  advice: string
  months?: number
  period?: string      // 这份汇总统计的是哪一段时间，直接显示给人看
}

export interface PendingProject {
  id: number; number: string; name: string; method: string
  officer: string; agency_code: string; agency_name: string; status: string
}

export const getAssessMeta = () =>
  api.get<{ ok: boolean; data: AssessMeta }>('/agency-assessments/meta')

export const listAssessments = (params?: Record<string, string>) =>
  api.get<{ ok: boolean; data: Assessment[] }>('/agency-assessments', { params })

export const listPendingProjects = () =>
  api.get<{ ok: boolean; data: PendingProject[] }>('/agency-assessments/pending-projects')

export const getAssessment = (pid: number) =>
  api.get<{ ok: boolean; data: Assessment }>(`/agency-assessments/project/${pid}`)

export const saveAssessment = (pid: number, data: Partial<Assessment>, submit = false) =>
  api.post<{ ok: boolean; data: Assessment; message: string }>(
    `/agency-assessments/project/${pid}${submit ? '?submit=1' : ''}`, data)

export const revokeAssessment = (aid: number) =>
  api.post<{ ok: boolean; message: string }>(`/agency-assessments/${aid}/revoke`)

// start/end 是「2026-01」这样的月份，含起含止；都不传就是考核办法默认的近 3 个月
export const getAgencySummary = (start?: string, end?: string) =>
  api.get<{ ok: boolean; data: AgencySummary[]; period?: string }>(
    '/agency-assessments/summary', { params: { start, end } })

// 只重算不落库：填日历时用它拿到新的建议分，算分规则不在前端复制一份
export const previewAssessment = (pid: number, items: AssessItem[], dates: AssessDates) =>
  api.post<{ ok: boolean; data: { items: AssessItem[]; total_score: number } }>(
    `/agency-assessments/project/${pid}/preview`, { items, dates })

// 导出 Excel / 打印：后端出成稿，走浏览器直连（要带 cookie，所以不用 axios）
export const assessExportUrl = (pid: number) =>
  `${api.defaults.baseURL}/agency-assessments/project/${pid}/export.xlsx`
export const assessPrintUrl = (pid: number) =>
  `${api.defaults.baseURL}/agency-assessments/project/${pid}/print`
