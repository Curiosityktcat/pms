import axios from 'axios'

export interface AnnProject {
  id: number
  name: string
  number: string
  agency_code: string
  agency_name: string
  status: string
  round?: number
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
  qualifications: string   // 一般资格要求（整段文本）
  special_req: string
  reg_start: string
  reg_end: string
  reg_note: string
  response_deadline: string
  agency_address: string
  delivery_address: string
  agency_email: string
  agency_reg_phone: string
  agency_contact: string
  agency_contact_phone: string
  // 更正公告（ann_type='correction'）专用
  corr_scope: string          // 更正事项：采购公告 / 采购文件 / 采购公告、采购文件
  corr_reason: string
  corr_items_json: string     // [{item,before,after}]
  corr_in_attachment: number  // 1=内容较多详见附件
  corr_seq: number            // 第几次更正
  status: string
  confirmed_by: string
  confirmed_at: string
  created_at: string
  created_by: string
}

export interface AnnAttachment {
  id: number
  announcement_id: number
  original_name: string
  file_size: number
  uploaded_by: string
  uploaded_at: string
}

export const QUALIFICATIONS_DEFAULT =
  '（一）在中华人民共和国境内注册，具有独立法人资格；\n' +
  '（二）具有良好的商业信誉和健全的财务会计制度；\n' +
  '（三）具备履行合同所必需的设备和专业技术能力；\n' +
  '（四）参加采购活动前三年内，在经营活动中没有重大违法记录；\n' +
  '（五）本项目不接受联合体；\n' +
  '（六）本项目规定的其他要求：'

export type AnnFormData = Omit<Announcement,
  'id' | 'project_name' | 'project_number' | 'agency_name' | 'project_agency_code' |
  'ann_type_cn' | 'confirmed_by' | 'confirmed_at' | 'created_at' | 'created_by' | 'corr_seq'>

// ── 公开接口（无需登录） ────────────────────────────────────────
export function getPublicAnnouncements(annType = 'procurement') {
  return axios.get<{ ok: boolean; data: Announcement[] }>('/api/announcements/public', {
    params: { type: annType },
  })
}

export function getPublicAnnouncement(id: number) {
  return axios.get<{ ok: boolean; data: Announcement }>(`/api/announcements/public/${id}`)
}

export function getPublicAnnouncementFiles(annId: number) {
  return axios.get<{ ok: boolean; data: AnnAttachment[] }>(`/api/announcements/public/${annId}/files`)
}

export function publicDownloadFileUrl(annId: number, fileId: number) {
  return `/api/announcements/public/${annId}/files/${fileId}`
}

export function publicWordUrl(annId: number) {
  return `/api/announcements/public/${annId}/word`
}

export function getPublicAnnouncementHtml(annId: number) {
  return axios.get<{ ok: boolean; html: string }>(`/api/announcements/public/${annId}/html`)
}

// ── 公告 CRUD ──────────────────────────────────────────────────
export function getEligibleProjects(annType = 'procurement') {
  return axios.get<{ ok: boolean; data: AnnProject[] }>('/api/announcements/projects', {
    params: { type: annType },
  })
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
// 点项目名在线预览生成的公告 Word（GET，内联）
export function announcementWordUrl(id: number) {
  return `/api/announcements/${id}/word`
}

// ── 附件 ──────────────────────────────────────────────────────
export function listFiles(annId: number) {
  return axios.get<{ ok: boolean; data: AnnAttachment[] }>(`/api/announcements/${annId}/files`)
}
export function deleteFile(annId: number, fileId: number) {
  return axios.delete<{ ok: boolean; message: string }>(`/api/announcements/${annId}/files/${fileId}`)
}
export function downloadFileUrl(annId: number, fileId: number) {
  return `/api/announcements/${annId}/files/${fileId}`
}
export function previewFileUrl(annId: number, fileId: number) {
  return `/api/announcements/${annId}/files/${fileId}/preview`
}
