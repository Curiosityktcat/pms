import api from './api'

export interface PlanItem {
  id: number
  year: number
  dept: string
  demand_dept: string
  name: string
  package_no: string
  plan_number: string
  org_form: string
  method: string
  deadline: string
  budget: number
  price_limit: number
  qty: string
  unit: string
  category: string
  category2: string
  demand_type: string
  status: string
  note: string
  project_id: number | null
  project_number: string
  project_name: string
  project_status: string
  linked_by: string
  linked_at: string
  will_procure: boolean
  source_file: string
  extra: Record<string, string>
  attachment_count: number
}

export interface PlanMeta {
  years: number[]
  depts: string[]
  categories: string[]
  categories2: string[]
  methods: string[]
  org_forms: string[]
  statuses: string[]
  demand_types: string[]
  not_procured: string[]
  can_edit: boolean
  total: number
}

export interface PlanStats {
  total: number
  live: number
  closed: number
  linked: number
  unlinked: number
  budget_sum: number
  by_dept: [string, number][]
}

export interface PlanAttachment {
  id: number
  plan_id: number
  filename: string
  size: number
  uploaded_by: string
  uploaded_at: string
  source: string
  ext: string
  exists?: boolean
}

export interface PlanCandidate {
  id: number
  number: string
  name: string
  status: string
  officer: string
  match: number
}

export const getPlanMeta = () =>
  api.get<{ ok: boolean; data: PlanMeta }>('/procurement-plans/meta')

export const listPlans = (params?: Record<string, string>) =>
  api.get<{ ok: boolean; data: PlanItem[]; total: number }>('/procurement-plans', { params })

export const getPlanStats = (year?: string) =>
  api.get<{ ok: boolean; data: PlanStats }>('/procurement-plans/stats', { params: { year } })

export const updatePlan = (id: number, data: Partial<PlanItem>) =>
  api.put<{ ok: boolean; data: PlanItem }>(`/procurement-plans/${id}`, data)

export const linkPlanProject = (id: number, body: { project_id?: number; project_number?: string }) =>
  api.post<{ ok: boolean; data: PlanItem; message: string }>(`/procurement-plans/${id}/link`, body)

export const unlinkPlanProject = (id: number) =>
  api.delete<{ ok: boolean; message: string }>(`/procurement-plans/${id}/link`)

export const getPlanCandidates = (id: number, keyword?: string) =>
  api.get<{ ok: boolean; data: PlanCandidate[] }>(
    `/procurement-plans/${id}/candidates`, { params: { keyword } })

export const listPlanAttachments = (id: number) =>
  api.get<{ ok: boolean; data: PlanAttachment[] }>(`/procurement-plans/${id}/attachments`)

export const uploadPlanAttachments = (id: number, files: File[]) => {
  const fd = new FormData()
  files.forEach(f => fd.append('file', f))
  return api.post<{ ok: boolean; data: PlanAttachment[]; message: string }>(
    `/procurement-plans/${id}/attachments`, fd,
    { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const deletePlanAttachment = (planId: number, aid: number) =>
  api.delete<{ ok: boolean; message: string }>(
    `/procurement-plans/${planId}/attachments/${aid}`)

export const planAttachmentUrl = (planId: number, aid: number, download = false) =>
  `/api/procurement-plans/${planId}/attachments/${aid}/${download ? 'download' : 'preview'}`
