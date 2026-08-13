import api from './api'

export interface WebAnn {
  id: number
  site_id: number
  url: string
  title: string
  ann_type: string
  publish_date: string      // 挂网时间
  bid_time: string          // 开标时间
  bid_place: string
  doc_get_start: string
  doc_get_end: string
  project_number: string
  project_name: string
  round_text: string
  agency: string
  method: string
  budget_text: string
  officer: string
  officer_basis: string
  purchaser_phone: string
  dept_contact: string
  agency_contact: string
  winner: string
  win_amount: string
  project_id: number | null
  match_how: string
  needs_check: number
  body?: string
}

export const listWebAnns = (params?: Record<string, string>) =>
  api.get<{ ok: boolean; data: WebAnn[]; total: number }>('/web-announcements', { params })

export const getWebAnnsByProject = (pid: number) =>
  api.get<{ ok: boolean; data: WebAnn[] }>(`/web-announcements/by-project/${pid}`)

export const getWebAnn = (id: number) =>
  api.get<{ ok: boolean; data: WebAnn }>(`/web-announcements/${id}`)

export const getWebAnnCounts = () =>
  api.get<{ ok: boolean; data: Record<string, number> }>('/web-announcements/counts')
