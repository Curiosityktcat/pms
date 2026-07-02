import api from './api'

export interface AgencyInfo {
  id: number
  code: string
  name: string
  active: number
  in_rotation: number
  rotation_seq: number
  legal_rep: string
  phone: string
  address: string
  is_central: number
}

export const listAgencies = () =>
  api.get<{ ok: boolean; data: AgencyInfo[] }>('/agencies')

export const createAgency = (data: Partial<AgencyInfo>) =>
  api.post<{ ok: boolean; data: AgencyInfo; error?: string }>('/agencies', data)

export const updateAgency = (id: number, data: Partial<AgencyInfo>) =>
  api.put<{ ok: boolean; data: AgencyInfo; error?: string }>(`/agencies/${id}`, data)

export const deactivateAgency = (id: number) =>
  api.delete<{ ok: boolean; error?: string }>(`/agencies/${id}`)
