import axios from 'axios'

export interface AgencyTemplate {
  id: number
  agency_code: string
  template_name: string
  agency_address: string
  delivery_address: string
  agency_email: string
  agency_reg_phone: string
  agency_contact: string
  agency_contact_phone: string
  created_at: string
  updated_at: string
}

export type TemplateFormData = Omit<AgencyTemplate, 'id' | 'created_at' | 'updated_at'>

export function getTemplates(agencyCode?: string) {
  return axios.get<{ ok: boolean; data: AgencyTemplate[] }>('/api/agency-templates', {
    params: agencyCode ? { agency_code: agencyCode } : {},
  })
}

export function createTemplate(data: TemplateFormData) {
  return axios.post<{ ok: boolean; message: string; data: AgencyTemplate }>('/api/agency-templates', data)
}

export function updateTemplate(id: number, data: TemplateFormData) {
  return axios.put<{ ok: boolean; message: string; data: AgencyTemplate }>(`/api/agency-templates/${id}`, data)
}

export function deleteTemplate(id: number) {
  return axios.delete<{ ok: boolean; message: string }>(`/api/agency-templates/${id}`)
}
