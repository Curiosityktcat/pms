import api from './api'

export interface BidCoverParams {
  agency_name?: string
  compile_date?: string
  round_number?: number
}

export const generateBidCover = (projectId: number, data: BidCoverParams) =>
  api.post(`/projects/${projectId}/bid-cover`, data, { responseType: 'blob' })

export const generateContentConfirm = (projectId: number, data: { agency_name?: string }) =>
  api.post(`/projects/${projectId}/content-confirm-word`, data, { responseType: 'blob' })

export type ConfirmKind = 'demand' | 'doc'

export const setDocConfirm = (projectId: number, kind: ConfirmKind, confirmed: boolean) =>
  api.post(`/projects/${projectId}/doc-confirm`, { kind, confirmed })

export interface DocAttachment {
  id: number
  project_id: number
  kind: string
  original_name: string
  file_size: number
  sha256: string
  uploaded_by: string
  uploaded_at: string
}

export const listDocAttachments = (projectId: number, kind: ConfirmKind) =>
  api.get<{ ok: boolean; data: DocAttachment[] }>(
    `/projects/${projectId}/doc-attachments?kind=${kind}`,
  )

export const uploadDocAttachmentUrl = (projectId: number, kind: ConfirmKind) =>
  `/api/projects/${projectId}/doc-attachments?kind=${kind}`

export const downloadDocAttachment = (projectId: number, attId: number) =>
  api.get(`/projects/${projectId}/doc-attachments/${attId}`, { responseType: 'blob' })

export const deleteDocAttachment = (projectId: number, attId: number) =>
  api.delete(`/projects/${projectId}/doc-attachments/${attId}`)
