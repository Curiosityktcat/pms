import api from './api'

export interface AuthLetterRecord {
  id: number
  project_id: number
  project_name: string
  project_number: string
  round_number: number
  bid_time: string
  supervisor_name: string
  representative_names: string
  generated_by: string
  generated_at: string
}

export interface AuthLetterRecordInput {
  project_id: number
  project_name: string
  project_number: string
  round_number: number
  bid_time: string
  supervisor_name: string
  representative_names: string
}

export const listAuthLetterRecords = () =>
  api.get<{ ok: boolean; data: AuthLetterRecord[] }>('/auth-letter-records')

export const createAuthLetterRecord = (data: AuthLetterRecordInput) =>
  api.post<{ ok: boolean; message: string; data: AuthLetterRecord }>('/auth-letter-records', data)

export const deleteAuthLetterRecord = (id: number) =>
  api.delete<{ ok: boolean; message: string }>(`/auth-letter-records/${id}`)
