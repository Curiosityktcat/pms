import api from './api'

export interface Project {
  id: number
  number: string
  name: string
  round: number
  display_name: string
  amount: number | null
  line: string
  method: string
  demand_dept: string
  manage_dept: string
  agency_code: string
  agency_name?: string
  officer: string
  content: string
  bid_time: string
  status: string
  is_draft: boolean
  can_open: string
  bid_note: string
  supervisor: string
  representative: string
  created_at: string
  updated_at: string
  category: string
  year: string
  is_deleted: boolean
  deleted_at: string
  demand_confirmed: boolean
  demand_confirmed_by: string
  demand_confirmed_at: string
  doc_confirmed: boolean
  doc_confirmed_by: string
  doc_confirmed_at: string
}

export interface Agency {
  id: number
  code: string
  name: string
  active: number
}

export interface ProjectMeta {
  agencies: Agency[]
  methods: string[]
  statuses: string[]
}

export const getProjects = (deleted = false) =>
  api.get<{ ok: boolean; data: Project[]; total: number }>(
    deleted ? '/projects?deleted=1' : '/projects'
  )

export const restoreProject = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/projects/${id}/restore`, {})

export const getProjectMeta = () =>
  api.get<ProjectMeta & { ok: boolean }>('/projects/meta')

export const getProject = (id: number) =>
  api.get<{ ok: boolean; data: Project; agencies: Agency[]; methods: string[]; statuses: string[] }>(`/projects/${id}`)

export const createProject = (data: Record<string, unknown>) =>
  api.post<{ ok: boolean; message: string; data: Project }>('/projects', data)

export const updateProject = (id: number, data: Record<string, unknown>) =>
  api.put<{ ok: boolean; message: string; data: Project }>(`/projects/${id}`, data)

export const deleteProject = (id: number) =>
  api.delete<{ ok: boolean; message: string }>(`/projects/${id}`)
