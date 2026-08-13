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
}

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
