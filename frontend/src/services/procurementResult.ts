import api from './api'

export interface ResultPackage {
  result: '成交' | '废标'
  winner: string
  amount: number
  amount_cn: string
  note: string
}

export interface ProcurementResult {
  id: number
  project_id: number
  round_number: number
  bid_time: string
  agency_name: string
  procurement_method: string
  packages: ResultPackage[]
  notes: string
  confirm_date: string
  status: '草稿' | '已确认'
  created_by: string
  created_at: string
  updated_at: string
}

export const listResults = (projectId?: number) =>
  api.get<{ ok: boolean; data: ProcurementResult[] }>('/procurement-results', {
    params: projectId ? { project_id: projectId } : {}
  })

export const createResult = (data: Partial<ProcurementResult> & { packages: ResultPackage[] }) =>
  api.post<{ ok: boolean; data: ProcurementResult }>('/procurement-results', data)

export const updateResult = (id: number, data: Partial<ProcurementResult>) =>
  api.put<{ ok: boolean; data: ProcurementResult }>(`/procurement-results/${id}`, data)

export const deleteResult = (id: number) =>
  api.delete<{ ok: boolean }>(`/procurement-results/${id}`)

export const confirmResult = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-results/${id}/confirm`)

export const revokeResult = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-results/${id}/revoke`)

export const resultWordUrl = (id: number) => `/api/procurement-results/${id}/word`
