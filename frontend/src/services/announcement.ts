import type { Pending } from './project'
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

export interface AnnPortal {
  portal_status: string      // 挂网中|已挂网|挂网失败|撤网中|已撤网|官网上找不到
  portal_url: string         // 公网详情页地址
  portal_news_id: number     // 官网那条记录的 id
  portal_error: string
  portal_at?: string
  running?: boolean
  enabled?: boolean
}

export const getAnnPortal = (id: number) =>
  axios.get<{ ok: boolean; data: AnnPortal }>(`/api/announcements/${id}/portal`,
    { withCredentials: true })

export const publishAnnPortal = (id: number) =>
  axios.post<{ ok: boolean; message: string }>(`/api/announcements/${id}/portal/publish`, {},
    { withCredentials: true })

export const revokeAnnPortal = (id: number) =>
  axios.post<{ ok: boolean; message: string }>(`/api/announcements/${id}/portal/revoke`, {},
    { withCredentials: true })

export const recheckAnnPortal = (id: number) =>
  axios.post<{ ok: boolean; online: boolean; data: AnnPortal }>(
    `/api/announcements/${id}/portal/recheck`, {}, { withCredentials: true })

export interface Announcement {
  pending?: Pending          // 当前处理人
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
  // 医院官网挂网
  portal_status?: string
  portal_url?: string
  portal_news_id?: number
  portal_error?: string
  portal_at?: string
  corr_scope: string          // 更正事项：采购公告 / 采购文件 / 采购公告、采购文件
  corr_reason: string
  corr_items_json: string     // [{item,before,after}]
  corr_in_attachment: number  // 1=内容较多详见附件
  corr_seq: number            // 第几次更正
  // 6.2 调研公告
  survey_content?: string
  survey_qualification?: string
  survey_quote_req?: string
  survey_materials?: string
  survey_deadline?: string
  survey_submit_way?: string
  survey_note?: string
  // 6.4 单一来源公示（法定必备内容，财政部令第74号第38条）
  ss_goods_desc?: string
  ss_reason?: string
  ss_supplier_name?: string
  ss_supplier_addr?: string
  ss_experts_json?: string
  ss_publicity_start?: string
  ss_publicity_end?: string
  ss_objection_dept?: string
  ss_objection_contact?: string
  ss_objection_phone?: string
  ss_objection_addr?: string
  status: string              // 草稿|待确认|已确认|已驳回
  confirmed_by: string
  confirmed_at: string
  reject_reason?: string
  reject_count?: number
  rejected_by?: string
  rejected_at?: string
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
/** 驳回：打回代理机构修改，必须写明原因（记入审批过程记录，归档留存） */
export function rejectAnnouncement(id: number, reason: string) {
  return axios.post<{ ok: boolean; message: string; data: Announcement }>(
    `/api/announcements/${id}/reject`, { reason })
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
