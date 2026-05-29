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
