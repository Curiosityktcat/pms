import api from './api'

export interface AgencyAgreementParams {
  agency_name?: string
  agency_address?: string
  officer_name?: string
  officer_phone?: string
  sign_date?: string
}

export const generateAgencyAgreement = (
  projectId: number,
  data: AgencyAgreementParams,
) =>
  api.post(`/projects/${projectId}/agency-agreement`, data, {
    responseType: 'blob',
  })

export interface RdwebStatus {
  running: boolean
  ok: boolean | null
  serial_no: string
  msg: string
}

export const submitAgencyAgreementToRdweb = (
  projectId: number,
  params: AgencyAgreementParams & { legal_rep?: string; agency_phone?: string; 合同金额?: string },
) =>
  api.post<{ ok: boolean; msg: string }>(`/projects/${projectId}/agency-agreement/submit-to-rdweb`, params)

export const getRdwebAgencyStatus = (projectId: number) =>
  api.get<{ ok: boolean; data: RdwebStatus }>(`/projects/${projectId}/agency-agreement/rdweb-status`)

// ── rd-web 审签附件（自行上传 / 从模板库选用，提交审签时随单带上）──────
export interface AgencyAttachment {
  name: string
  size: number
  updated_at: string
}

export const listAgencyAttachments = (projectId: number) =>
  api.get<{ ok: boolean; data: AgencyAttachment[] }>(
    `/projects/${projectId}/agency-agreement/attachments`)

export const uploadAgencyAttachment = (projectId: number, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ ok: boolean; data: AgencyAttachment[] }>(
    `/projects/${projectId}/agency-agreement/attachments`, fd,
    { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const addAgencyAttachmentFromTemplate = (projectId: number, key: string) =>
  api.post<{ ok: boolean; data: AgencyAttachment[] }>(
    `/projects/${projectId}/agency-agreement/attachments/from-template`, { key })

export const deleteAgencyAttachment = (projectId: number, name: string) =>
  api.delete<{ ok: boolean; data: AgencyAttachment[] }>(
    `/projects/${projectId}/agency-agreement/attachments/${encodeURIComponent(name)}`)
