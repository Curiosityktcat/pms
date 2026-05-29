import api from './api'

// ── Interfaces ──────────────────────────────────────────────────

export interface InquiryLetter {
  id: number
  project_id: number
  type: '询价' | '议价'
  title: string
  content: string
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

// ── Supplier API ────────────────────────────────────────────────

export const listSuppliers = (inquiryId: number) =>
  api.get<{ ok: boolean; data: InquirySupplier[] }>(`/inquiries/${inquiryId}/suppliers`)

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

// ── Email Config API ────────────────────────────────────────────

export const getEmailConfig = () =>
  api.get<{ ok: boolean; data: EmailConfig }>('/sys-config/email')

export const updateEmailConfig = (data: Partial<EmailConfig>) =>
  api.put<{ ok: boolean; message: string }>('/sys-config/email', data)

export const testEmail = () =>
  api.post<{ ok: boolean; message: string }>('/sys-config/email/test')
