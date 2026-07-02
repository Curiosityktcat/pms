import api from './api'

export interface DeptAnnouncement {
  id: number
  title: string
  note: string
  filename: string
  file_size: number
  uploaded_by: string
  uploaded_at: string
  status: '待审核' | '已发布' | '已驳回'
  reviewed_by: string
  reviewed_at: string
  reject_reason: string
}

export const listDeptAnnouncements = () =>
  api.get<{ ok: boolean; data: DeptAnnouncement[]; is_reviewer: boolean; can_upload: boolean }>(
    '/dept-announcements')

export const createDeptAnnouncement = (title: string, note: string, file?: File) => {
  const fd = new FormData()
  fd.append('title', title)
  fd.append('note', note)
  if (file) fd.append('file', file)
  return api.post<{ ok: boolean; message: string }>('/dept-announcements', fd,
    { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const reviewDeptAnnouncement = (id: number, action: 'approve' | 'reject', reason = '') =>
  api.post<{ ok: boolean; message: string }>(`/dept-announcements/${id}/review`, { action, reason })

export const deleteDeptAnnouncement = (id: number) =>
  api.delete<{ ok: boolean }>(`/dept-announcements/${id}`)

export const deptAnnouncementDownloadUrl = (id: number) =>
  `/api/dept-announcements/${id}/download`
