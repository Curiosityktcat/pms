import api from './api'

export interface DeptInfo {
  id: number
  code: string
  name: string
  aliases: string[]
  category: string
  active: number
  sort_no: number
  note: string
}

export interface DeptMe {
  role: string
  dept: DeptInfo | null
  can_switch: boolean
  depts?: DeptInfo[]
}

export interface DeptOverview {
  dept: string
  total: number
  ongoing: number
  archived: number
  stages: { stage: string; stage_cn: string; count: number }[]
  years: { year: string; count: number }[]
}

export interface DeptProject {
  id: number
  number: string
  name: string
  amount: number | null
  method: string
  status: string
  manage_dept: string
  demand_dept: string
  bid_time: string
  year: string
  round: number
  current_stage: string
  stage_cn: string
  archived: boolean
}

export interface DeptContract {
  id: number
  project_id: number
  project_number: string
  project_name: string
  contract_number: string
  contract_name: string
  package_no: string
  supplier_name: string
  amount: number | null
  amount_text: string
  sign_date: string
  service_start: string
  service_end: string
  status: string
}

export interface DeptPlan {
  id: number
  year: number
  name: string
  dept: string
  demand_dept: string
  budget: number | null
  method: string
  status: string
  deadline: string
  project: { id: number; number: string; name: string } | null
}

export interface DeptProjectDetail extends DeptProject {
  content: string
  plan: { id: number; name: string; plan_number: string } | null
  contracts: DeptContract[]
}

const q = (params?: Record<string, string | undefined>) => {
  const p = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => { if (v) p.set(k, v) })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const getDeptMe = (dept?: string) =>
  api.get<{ ok: boolean; data: DeptMe }>(`/dept/me${q({ dept })}`)

export const getDeptOverview = (dept?: string) =>
  api.get<{ ok: boolean; data: DeptOverview }>(`/dept/overview${q({ dept })}`)

export const listDeptProjects = (params?: Record<string, string | undefined>) =>
  api.get<{ ok: boolean; data: DeptProject[]; total: number }>(`/dept/projects${q(params)}`)

export const getDeptProject = (id: number, dept?: string) =>
  api.get<{ ok: boolean; data: DeptProjectDetail }>(`/dept/projects/${id}${q({ dept })}`)

export const getDeptProgress = (id: number, dept?: string) =>
  api.get<{ ok: boolean; data: unknown }>(`/dept/projects/${id}/progress${q({ dept })}`)

export const getDeptTree = (id: number, dept?: string) =>
  api.get<{ ok: boolean; data: unknown }>(`/dept/projects/${id}/tree${q({ dept })}`)

export const listDeptContracts = (dept?: string) =>
  api.get<{ ok: boolean; data: DeptContract[]; total: number }>(`/dept/contracts${q({ dept })}`)

export const listDeptPlans = (params?: Record<string, string | undefined>) =>
  api.get<{ ok: boolean; data: DeptPlan[]; total: number }>(`/dept/plans${q(params)}`)

/** 资料下载/预览地址：走后端同一套鉴权，前端只拼 URL。 */
export const deptItemUrl = (pid: number, round: number, kind: string, download = false, dept?: string) =>
  `/api/dept/projects/${pid}/item${q({
    round: String(round), kind, download: download ? '1' : undefined, dept,
  })}`

export const deptAttachmentUrl = (pid: number, aid: number, download = false, dept?: string) =>
  `/api/dept/projects/${pid}/attachment/${aid}${q({
    download: download ? '1' : undefined, dept,
  })}`
