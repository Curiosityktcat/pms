import api from './api'

// ── Interfaces ──────────────────────────────────────────────────

export interface InquiryLetter {
  id: number
  project_id: number
  type: '询价' | '议价' | '紧急采购'
  title: string
  content: string
  detail: string         // 项目细则和限价
  requirements: string   // 相关要求
  deadline: string
  status: '草稿' | '进行中' | '已完成'
  notes: string
  created_by: string
  created_at: string
  updated_at: string
  // enriched
  project_name: string
  project_number: string
  supplier_count: number
  sent_count: number
  round: number          // 第几轮邀请（1 起）
}

export interface InquirySupplier {
  id: number
  inquiry_id: number
  supplier_name: string
  contact_name: string
  contact_phone: string
  email: string
  sent_at: string
  sent_by: string
  quote_amount: number | null
  quote_date: string
  quote_note: string
  is_selected: number  // 0 | 1
  // 评审字段（模块8.1）
  responded: number  // 0 | 1 是否递交响应
  qual_pass: '' | '通过' | '不通过'
  conform_pass: '' | '通过' | '不通过'
  final_price: string
  review_rank: string
  fail_reason: string
}

export interface InquiryAttachment {
  id: number
  inquiry_id: number
  filename: string
  filepath: string
  uploaded_at: string
  uploaded_by: string
}

export interface InquiryTemplate {
  id: number
  filename: string
  description: string
  filepath: string
  uploaded_at: string
  uploaded_by: string
}

export interface EmailConfig {
  email_smtp_host: string
  email_smtp_port: string
  email_address: string
  email_auth_code: string
  email_sender_name: string
}

// ── InquiryLetter API ───────────────────────────────────────────

export const listInquiries = (projectId?: number) =>
  api.get<{ ok: boolean; data: InquiryLetter[] }>('/inquiries', {
    params: projectId ? { project_id: projectId } : {},
  })

export const createInquiry = (data: Partial<InquiryLetter>) =>
  api.post<{ ok: boolean; data: InquiryLetter }>('/inquiries', data)

export const updateInquiry = (id: number, data: Partial<InquiryLetter>) =>
  api.put<{ ok: boolean; data: InquiryLetter }>(`/inquiries/${id}`, data)

export const deleteInquiry = (id: number) =>
  api.delete<{ ok: boolean; message: string }>(`/inquiries/${id}`)

export const completeInquiry = (id: number) =>
  api.post<{ ok: boolean; message: string; data: InquiryLetter }>(`/inquiries/${id}/complete`)

export const downloadWordUrl = (id: number) => `/api/inquiries/${id}/word`

export const previewWordUrl = (id: number) => `/api/inquiries/${id}/word/preview`

// ── Supplier API ────────────────────────────────────────────────

export const listSuppliers = (inquiryId: number) =>
  api.get<{ ok: boolean; data: InquirySupplier[] }>(`/inquiries/${inquiryId}/suppliers`)

export interface ReplyRow extends InquirySupplier {
  replied: boolean
  reply_subject?: string
  reply_from?: string
  reply_date?: string
  reply_confident?: boolean
}
export interface RepliesData {
  project_name: string
  round: number
  reply_format: string
  replied: number
  sent: number
  suppliers: ReplyRow[]
  unmatched: { subject: string; from: string; date: string }[]
}
export const getReplies = (inquiryId: number) =>
  api.get<{ ok: boolean; data: RepliesData }>(`/inquiries/${inquiryId}/replies`)

export const addSupplier = (inquiryId: number, data: Partial<InquirySupplier>) =>
  api.post<{ ok: boolean; data: InquirySupplier }>(`/inquiries/${inquiryId}/suppliers`, data)

export const updateSupplier = (
  inquiryId: number,
  supplierId: number,
  data: Partial<InquirySupplier>,
) =>
  api.put<{ ok: boolean; data: InquirySupplier }>(
    `/inquiries/${inquiryId}/suppliers/${supplierId}`,
    data,
  )

export const deleteSupplier = (inquiryId: number, supplierId: number) =>
  api.delete<{ ok: boolean; message: string }>(
    `/inquiries/${inquiryId}/suppliers/${supplierId}`,
  )

export const sendEmailToSupplier = (inquiryId: number, supplierId: number) =>
  api.post<{ ok: boolean; message: string; data: InquirySupplier }>(
    `/inquiries/${inquiryId}/suppliers/${supplierId}/send`,
  )

// 一键群发：发送给所有「已填邮箱且未发送」的供应商
export const sendAllToSuppliers = (inquiryId: number) =>
  api.post<{
    ok: boolean
    message: string
    sent: string[]
    failed: { email: string; error: string }[]
    data: InquiryLetter
  }>(`/inquiries/${inquiryId}/send-all`)

// ── Attachment API ──────────────────────────────────────────────

export const listAttachments = (inquiryId: number) =>
  api.get<{ ok: boolean; data: InquiryAttachment[] }>(`/inquiries/${inquiryId}/attachments`)

export const uploadAttachment = (inquiryId: number, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ ok: boolean; data: InquiryAttachment }>(
    `/inquiries/${inquiryId}/attachments`,
    fd,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

export const deleteAttachment = (inquiryId: number, attachmentId: number) =>
  api.delete<{ ok: boolean; message: string }>(
    `/inquiries/${inquiryId}/attachments/${attachmentId}`,
  )

export const attachmentDownloadUrl = (inquiryId: number, attachmentId: number) =>
  `/api/inquiries/${inquiryId}/attachments/${attachmentId}/download`

export const attachmentPreviewUrl = (inquiryId: number, attachmentId: number) =>
  `/api/inquiries/${inquiryId}/attachments/${attachmentId}/preview`

export const attachFromTemplate = (inquiryId: number, templateIds: number[]) =>
  api.post<{ ok: boolean; message: string; added: string[] }>(
    `/inquiries/${inquiryId}/attachments/from-template`,
    { template_ids: templateIds },
  )

// ── Template Library API ────────────────────────────────────────

export const listTemplates = () =>
  api.get<{ ok: boolean; data: InquiryTemplate[] }>('/inquiry-templates')

export const uploadTemplate = (file: File, description: string) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('description', description)
  return api.post<{ ok: boolean; data: InquiryTemplate }>(
    '/inquiry-templates',
    fd,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

export const updateTemplate = (id: number, description: string) =>
  api.put<{ ok: boolean; data: InquiryTemplate }>(`/inquiry-templates/${id}`, { description })

export const deleteTemplate = (id: number) =>
  api.delete<{ ok: boolean; message: string }>(`/inquiry-templates/${id}`)

// ── 询议价评审（模块8.1） ───────────────────────────────────────

export interface InquirySupplierFile {
  id: number
  inquiry_id: number
  supplier_id: number
  filename: string
  filepath: string
  uploaded_at: string
  uploaded_by: string
}

export interface InquiryReview {
  id: number
  inquiry_id: number
  project_id: number
  round_no: number
  project_name: string
  project_number: string
  package_no: string
  content: string
  budget: string
  review_date: string
  location: string
  method: '院内询价' | '院内议价'
  result_type: '' | '中选' | '废标'
  result_text: string
  remark: string
  review_place: string
  committee: string
  bid_open_info: string
  status: '草稿' | '已完成'
  completed_by: string
  completed_at: string
  created_by: string
  created_at: string
  updated_at: string
  early_open: number
  early_open_by: string
  early_open_at: string
  // enriched
  letter_type: '询价' | '议价' | '紧急采购'
  letter_status: string
  deadline: string
  deadline_passed: boolean
  method_switchable: boolean
  suppliers: InquirySupplier[]
  pass_count: number
  responded_count: number
  supplier_files: Record<number, InquirySupplierFile[]>
}

export interface FetchRepliesResult {
  replied: number
  imported: number
  suppliers: {
    supplier_id: number
    supplier_name: string
    replied: boolean
    imported: string[]
    reply_subject?: string
    reply_date?: string
  }[]
  unmatched: { subject: string; from: string; date: string }[]
}

export interface InquiryReviewListRow {
  inquiry_id: number
  project_id: number
  project_name: string
  project_number: string
  type: '询价' | '议价' | '紧急采购'
  title: string
  deadline: string
  deadline_passed: boolean
  letter_status: string
  round_no: number
  supplier_count: number
  responded_count: number
  early_open: number
  review_status: '' | '草稿' | '已完成'
  result_type: '' | '中选' | '废标'
  method: string
  completed_at: string
}

export const listInquiryReviews = () =>
  api.get<{ ok: boolean; data: InquiryReviewListRow[] }>('/inquiry-reviews')

export const getInquiryReview = (inquiryId: number) =>
  api.get<{ ok: boolean; data: InquiryReview }>(`/inquiries/${inquiryId}/review`)

export const saveInquiryReview = (
  inquiryId: number,
  data: Partial<Omit<InquiryReview, 'suppliers'>> & { suppliers?: Partial<InquirySupplier>[] },
) =>
  api.put<{ ok: boolean; data: InquiryReview }>(`/inquiries/${inquiryId}/review`, data)

export const completeInquiryReview = (
  inquiryId: number,
  resultType: '中选' | '废标',
  winnerSupplierId?: number,
) =>
  api.post<{ ok: boolean; message: string; data: InquiryReview }>(
    `/inquiries/${inquiryId}/review/complete`,
    { result_type: resultType, winner_supplier_id: winnerSupplierId },
  )

export const earlyOpenReview = (inquiryId: number) =>
  api.post<{ ok: boolean; message: string; data: InquiryReview }>(
    `/inquiries/${inquiryId}/review/early-open`,
  )

export const reopenInquiryReview = (inquiryId: number) =>
  api.post<{ ok: boolean; message: string; data: InquiryReview }>(
    `/inquiries/${inquiryId}/review/reopen`,
  )

export const startNextRound = (inquiryId: number) =>
  api.post<{ ok: boolean; message: string; data: InquiryLetter }>(
    `/inquiries/${inquiryId}/next-round`,
  )

// 从收件箱抓取供应商回复：匹配的供应商置「已响应」并导入邮件附件为响应文件
export const fetchReviewReplies = (inquiryId: number) =>
  api.post<{ ok: boolean; message: string; data: FetchRepliesResult }>(
    `/inquiries/${inquiryId}/review/fetch-replies`,
  )

export const reviewExcelUrl = (inquiryId: number) =>
  `/api/inquiries/${inquiryId}/review/excel`

export const uploadSupplierFile = (inquiryId: number, supplierId: number, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ ok: boolean; data: InquirySupplierFile }>(
    `/inquiries/${inquiryId}/suppliers/${supplierId}/files`,
    fd,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

export const deleteSupplierFile = (inquiryId: number, fileId: number) =>
  api.delete<{ ok: boolean; message: string }>(
    `/inquiries/${inquiryId}/supplier-files/${fileId}`,
  )

export const supplierFileDownloadUrl = (inquiryId: number, fileId: number) =>
  `/api/inquiries/${inquiryId}/supplier-files/${fileId}/download`

export const supplierFilePreviewUrl = (inquiryId: number, fileId: number) =>
  `/api/inquiries/${inquiryId}/supplier-files/${fileId}/preview`

// ── Email Config API ────────────────────────────────────────────

export const getEmailConfig = () =>
  api.get<{ ok: boolean; data: EmailConfig }>('/sys-config/email')

export const updateEmailConfig = (data: Partial<EmailConfig>) =>
  api.put<{ ok: boolean; message: string }>('/sys-config/email', data)

export const testEmail = () =>
  api.post<{ ok: boolean; message: string }>('/sys-config/email/test')
