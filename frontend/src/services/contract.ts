import api from './api'

export interface Contract {
  id: number
  project_id: number
  contract_number: string
  contract_name: string
  package_no: string
  status: '合同草案' | '审核完成' | '合同上传'
  supplier_name: string
  supplier_address: string
  supplier_contact: string
  supplier_legal_rep: string
  amount_is_text: number   // 0=数字, 1=文字
  amount_text: string
  amount: number | null
  sign_date: string
  service_start: string
  service_end: string
  file_name: string
  file_saved_name: string
  notes: string
  created_by: string
  created_at: string
  updated_at: string
  // enriched
  project_number: string
  project_name: string
  project_amount: number | null
  project_category: string
}

export const listContracts = (projectId?: number) =>
  api.get<{ ok: boolean; data: Contract[] }>('/contracts', {
    params: projectId ? { project_id: projectId } : {}
  })

export const createContract = (data: Partial<Contract>) =>
  api.post<{ ok: boolean; data: Contract }>('/contracts', data)

export const updateContract = (id: number, data: Partial<Contract>) =>
  api.put<{ ok: boolean; data: Contract }>(`/contracts/${id}`, data)

export const deleteContract = (id: number) =>
  api.delete<{ ok: boolean }>(`/contracts/${id}`)

export const submitContract = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/contracts/${id}/submit`)

export const revokeContract = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/contracts/${id}/revoke`)

export const contractFileUrl = (id: number) => `/api/contracts/${id}/file`
export const contractFilePreviewUrl = (id: number) => `/api/contracts/${id}/file/preview`

export const uploadContractFile = (id: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<{ ok: boolean; file_name: string }>(`/contracts/${id}/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// ── 合同附件 ──────────────────────────────────────────────────────
export interface ContractAttachment {
  id: number
  contract_id: number
  original_name: string
  saved_name: string
  file_size: number
  mime_type: string
  stage: '草案' | '上传'
  uploaded_by: string
  uploaded_at: string
}

export const listAttachments = (cid: number) =>
  api.get<{ ok: boolean; data: ContractAttachment[] }>(`/contracts/${cid}/attachments`)

export const uploadAttachment = (cid: number, file: File, stage: '草案' | '上传') => {
  const form = new FormData()
  form.append('file', file)
  form.append('stage', stage)
  return api.post<{ ok: boolean; data: ContractAttachment }>(`/contracts/${cid}/attachments`, form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const deleteAttachment = (cid: number, aid: number) =>
  api.delete<{ ok: boolean }>(`/contracts/${cid}/attachments/${aid}`)

export const attachmentDownloadUrl = (cid: number, aid: number) =>
  `/api/contracts/${cid}/attachments/${aid}/download`

export const attachmentPreviewUrl = (cid: number, aid: number) =>
  `/api/contracts/${cid}/attachments/${aid}/preview`

export function isPreviewable(mimeType: string): boolean {
  return mimeType.startsWith('image/') || mimeType === 'application/pdf'
}

export function isImage(mimeType: string): boolean {
  return mimeType.startsWith('image/')
}

// ── rd-web 合同审签单直连 ─────────────────────────────────────────
export interface RdwebStatus {
  running: boolean
  ok: boolean | null
  serial_no: string
  msg: string
}

export const submitContractToRdweb = (cid: number, overrides?: Record<string, string>) =>
  api.post<{ ok: boolean; msg: string }>(`/contracts/${cid}/submit-to-rdweb`,
    overrides ? { data: overrides } : {})

export const getRdwebContractStatus = (cid: number) =>
  api.get<{ ok: boolean; data: RdwebStatus }>(`/contracts/${cid}/rdweb-status`)
