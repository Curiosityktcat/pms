import type { Pending } from './project'
import api from './api'
import { smartUpload, type UploadProgress } from './upload'

export interface Contract {
  pending?: Pending          // 当前处理人
  id: number
  project_id: number
  contract_number: string
  contract_name: string
  package_no: string
  status: '合同草案' | '待审核' | '审核完成' | '合同上传'
  contract_type?: string      // 合同类型名，经办人审核时确认
  reviewed_by?: string
  reviewed_at?: string
  // rd-web 合同审签推送结果：有流水号即表示推送成功
  rdweb_serial_no?: string
  rdweb_submitted_at?: string
  // 驳回：退回合同草案时挂上原因，编制方直接看到要改什么
  reject_reason?: string
  reject_count?: number
  rejected_by?: string
  rejected_at?: string
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

/** 审核弹窗要显示的内容：猜出来的合同类型 + 拼好的合同名称，供经办人过目 */
export interface ReviewPreview {
  contract_type: string
  contract_type_guessed: boolean
  composed_name: string
  project_name: string
  package_no: string
  common_types: string[]
}
export const getReviewPreview = (id: number) =>
  api.get<{ ok: boolean; data: ReviewPreview }>(`/contracts/${id}/review-preview`)

/** 经办人审核通过：这一步才置「审核完成」，也只有这一步会推 rd-web 审签单 */
export const reviewContract = (id: number, contractType: string) =>
  api.post<{ ok: boolean; message: string; rdweb_push?: unknown }>(
    `/contracts/${id}/review`, { contract_type: contractType })

export const revokeContract = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/contracts/${id}/revoke`)

/** 驳回：退回合同草案，必须写明原因（记入审批过程记录，归档留存） */
export const rejectContract = (id: number, reason: string) =>
  api.post<{ ok: boolean; message: string }>(`/contracts/${id}/reject`, { reason })

export const contractFileUrl = (id: number) => `/api/contracts/${id}/file`
export const contractFilePreviewUrl = (id: number) => `/api/contracts/${id}/file/preview`

export const uploadContractFile = (id: number, file: File) =>
  smartUpload<{ ok: boolean; file_name: string }>(`/contracts/${id}/upload`, file)

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

export const uploadAttachment = (
  cid: number, file: File, stage: '草案' | '上传', onProgress?: (p: UploadProgress) => void,
) => smartUpload<{ ok: boolean; data: ContractAttachment }>(
  `/contracts/${cid}/attachments`, file, { stage }, onProgress)

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
