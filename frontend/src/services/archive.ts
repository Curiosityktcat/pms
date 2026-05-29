import api from './api'

export interface ArchiveItem {
  id: number
  number: string
  name: string
  officer: string
  agency_code: string
  status: string
  archived: boolean
  auth_letter_count: number
  contract_count: number
  result_count: number
}

export const listArchive = () =>
  api.get<{ ok: boolean; data: ArchiveItem[] }>('/archive')

export const archiveProject = (id: number) =>
  api.post(`/archive/${id}`)

export const revokeArchive = (id: number) =>
  api.post(`/archive/${id}/revoke`)
