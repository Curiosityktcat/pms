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
