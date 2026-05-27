import axios from 'axios'

export interface AnnProject {
  id: number
  name: string
  number: string
  agency_code: string
  agency_name: string
  status: string
}

export interface Announcement {
  id: number
  project_id: number
  project_name?: string
  project_number?: string
  agency_name?: string
  project_agency_code?: string
  ann_type: string
  ann_type_cn?: string
  round_number: number
  project_intro: string
  special_req: string
  // 一般资格要求
  qual_1: string
  qual_2: string
  qual_3: string
  qual_4: string
  qual_5: string
  qual_6: string
  // 时间
  reg_start: string
  reg_end: string
  reg_note: string
  response_deadline: string
  // 代理信息
  agency_address: string
  delivery_address: string
  agency_email: string
  agency_reg_phone: string
  agency_contact: string
  agency_contact_phone: string
  // 状态
  status: string
  confirmed_by: string
  confirmed_at: string
  created_at: string
  created_by: string
}

export const QUAL_DEFAULTS = [
  '（一）在中华人民共和国境内注册，具有独立法人资格；',
  '（二）具有良好的商业信誉和健全的财务会计制度；',
  '（三）具备履行合同所必需的设备和专业技术能力；',
  '（四）参加采购活动前三年内，在经营活动中没有重大违法记录；',
  '（五）本项目不接受联合体；',
  '（六）本项目规定的其他要求：',
]

export type AnnFormData = Omit<Announcement, 'id' | 'project_name' | 'project_number' | 'agency_name' | 'project_agency_code' | 'ann_type_cn' | 'confirmed_by' | 'confirmed_at' | 'created_at' | 'created_by'>

export function getEligibleProjects() {
  return axios.get<{ ok: boolean; data: AnnProject[] }>('/api/announcements/projects')
}

export function getAnnouncements(annType = 'procurement') {
  return axios.get<{ ok: boolean; data: Announcement[] }>('/api/announcements', {
    params: { type: annType },
  })
}

export function getAnnouncement(id: number) {
  return axios.get<{ ok: boolean; data: Announcement }>(`/api/announcements/${id}`)
}

export function createAnnouncement(data: AnnFormData) {
  return axios.post<{ ok: boolean; message: string; data: Announcement }>('/api/announcements', data)
}

export function updateAnnouncement(id: number, data: AnnFormData) {
  return axios.put<{ ok: boolean; message: string; data: Announcement }>(`/api/announcements/${id}`, data)
}

export function deleteAnnouncement(id: number) {
  return axios.delete<{ ok: boolean; message: string }>(`/api/announcements/${id}`)
}

export function submitAnnouncement(id: number) {
  return axios.post<{ ok: boolean; message: string; data: Announcement }>(`/api/announcements/${id}/submit`)
}

export function confirmAnnouncement(id: number) {
  return axios.post<{ ok: boolean; message: string; data: Announcement }>(`/api/announcements/${id}/confirm`)
}

export function revokeAnnouncement(id: number) {
  return axios.post<{ ok: boolean; message: string; data: Announcement }>(`/api/announcements/${id}/revoke`)
}

export function generateAnnouncementWord(id: number) {
  return axios.post(`/api/announcements/${id}/generate`, {}, { responseType: 'blob' })
}
