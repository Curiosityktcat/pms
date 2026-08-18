import api from './api'
import type { Pending } from './project'

export interface MonitorFilters {
  year?: string
  manage_dept?: string
  demand_dept?: string
  officer?: string
  method?: string
  stage?: string
  overdue?: string
  archived?: string      // '1' = 把已归档的历史项目也列出来
  keyword?: string
}

export interface MonitorProject {
  id: number
  name: string
  number: string
  manage_dept: string
  demand_dept: string
  officer: string
  method: string
  amount: number | null
  current_stage: string
  stage_label: string
  current_round: number
  updated_at: string
  last_action_at: string
  overdue: boolean
  pending?: Pending
}

export interface MonitorMeta {
  years: string[]
  manage_depts: string[]
  demand_depts: string[]
  officers: string[]
  methods: string[]
  stages: { value: string; label: string }[]
  overdue_days: number
  show_officer_stats: boolean
  show_plans: boolean
}

export interface MonitorStats {
  ongoing: number
  new_this_month: number
  overdue: number
  overdue_days: number
  by_stage: { stage: string; label: string; count: number }[]
  by_officer: { name: string; count: number }[]
}

export interface MonitorNode {
  key: string
  label: string
  done: boolean
  at: string
  by: string
}

export interface MonitorTimeline {
  project: {
    id: number
    name: string
    number: string
    method: string
    current_round: number
    current_stage: string
    pending?: Pending
  }
  rounds: { round_number: number; status: string; nodes: MonitorNode[] }[]
}

export interface MonitorPlan {
  id: number
  year: number
  name: string
  dept: string
  demand_dept: string
  budget: number
  method: string
  status: string
  plan_status: string
  deadline: string
  deadline_raw: string
  overdue: boolean
  deadline_near: boolean
  project: null | {
    id: number
    number: string
    name: string
    current_stage: string
    stage_label: string
    pending?: Pending
  }
}

export const getMonitorMeta = () =>
  api.get<{ ok: boolean; data: MonitorMeta }>('/project-monitor/meta')

export const listMonitorProjects = (params: MonitorFilters & { page: number; page_size: number }) =>
  api.get<{ ok: boolean; data: MonitorProject[]; total: number; page: number; page_size: number }>(
    '/project-monitor/projects', { params })

export const getMonitorStats = (params: MonitorFilters) =>
  api.get<{ ok: boolean; data: MonitorStats }>('/project-monitor/stats', { params })

export const getMonitorTimeline = (id: number) =>
  api.get<{ ok: boolean; data: MonitorTimeline }>(`/project-monitor/projects/${id}/timeline`)

export const listMonitorPlans = (params: { year?: string; keyword?: string; page: number; page_size: number }) =>
  api.get<{ ok: boolean; data: MonitorPlan[]; total: number; page: number; page_size: number }>(
    '/project-monitor/plans', { params })

export const monitorExportUrl = (filters: MonitorFilters) => {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value) query.set(key, value)
  })
  const suffix = query.toString()
  return `/api/project-monitor/export${suffix ? `?${suffix}` : ''}`
}

// ── 项目资料：归档文件夹里的东西 + 在这里补传的材料 ──────────────
export interface MonitorFileItem {
  id?: number                 // 只有「补充材料」有 id（能删）
  name: string
  size: number
  url: string
  preview_url?: string
  uploaded_by?: string
  uploaded_at?: string
  can_delete?: boolean
}
export interface MonitorFileFolder {
  folder: string
  items: MonitorFileItem[]
}

export const getProjectFiles = (pid: number) =>
  api.get<{ ok: boolean; data: MonitorFileFolder[]; total: number; can_upload: boolean }>(
    `/project-monitor/projects/${pid}/files`)

export const uploadProjectFiles = (pid: number, files: File[]) => {
  const fd = new FormData()
  files.forEach(f => fd.append('file', f))
  return api.post<{ ok: boolean; message: string }>(
    `/project-monitor/projects/${pid}/files`, fd)
}

export const deleteProjectFile = (pid: number, fid: number) =>
  api.delete<{ ok: boolean; message: string }>(
    `/project-monitor/projects/${pid}/files/${fid}`)
