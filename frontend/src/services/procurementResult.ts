import api from './api'

export interface ResultPackage {
  package_no?: number
  result: '成交' | '废标'
  winner: string
  amount: number
  amount_cn: string
  note: string
  unit_price_attached?: boolean   // 招单价项目：成交单价详见附件（不填固定金额）
}

export interface PriceAttachment {
  id: number
  original_name: string
  file_size: number
  uploaded_by: string
  uploaded_at: string
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
  status: '草稿' | '待确认' | '已确认'
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

export const submitResult = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-results/${id}/submit`)

export const confirmResult = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-results/${id}/confirm`)

export const revokeResult = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-results/${id}/revoke`)

export const resultWordUrl = (id: number) => `/api/procurement-results/${id}/word`

// ── 单价附件（招单价项目「单价详见附件」）─────────────────────────────
export const listPriceAttachments = (rid: number) =>
  api.get<{ ok: boolean; data: PriceAttachment[] }>(`/procurement-results/${rid}/price-attachments`)

export const uploadPriceAttachmentUrl = (rid: number) =>
  `/api/procurement-results/${rid}/price-attachments`

export const downloadPriceAttachment = (rid: number, aid: number) =>
  api.get(`/procurement-results/${rid}/price-attachments/${aid}`, { responseType: 'blob' })

export const pricePreviewUrl = (rid: number, aid: number) =>
  `/api/procurement-results/${rid}/price-attachments/${aid}/preview`

export const deletePriceAttachment = (rid: number, aid: number) =>
  api.delete(`/procurement-results/${rid}/price-attachments/${aid}`)

// ── 中标通知书（经办人确认采购结果后由代理机构上传）──────────────────
export const listAwardNotice = (rid: number) =>
  api.get<{ ok: boolean; data: PriceAttachment[] }>(`/procurement-results/${rid}/award-notice`)

export const uploadAwardNoticeUrl = (rid: number) =>
  `/api/procurement-results/${rid}/award-notice`

export const downloadAwardNotice = (rid: number, aid: number) =>
  api.get(`/procurement-results/${rid}/award-notice/${aid}`, { responseType: 'blob' })

export const awardNoticePreviewUrl = (rid: number, aid: number) =>
  `/api/procurement-results/${rid}/award-notice/${aid}/preview`

export const deleteAwardNotice = (rid: number, aid: number) =>
  api.delete(`/procurement-results/${rid}/award-notice/${aid}`)
