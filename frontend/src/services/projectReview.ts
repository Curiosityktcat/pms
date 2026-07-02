import api from './api'

export interface ReviewAttachment {
  id: number
  original_name: string
  file_size: number
  uploaded_by: string
  uploaded_at: string
}

export interface ReviewProject {
  id: number
  name: string
  number: string
  method: string
  agency_code: string
  agency_name?: string
  officer: string
  current_round: number
  attachments: ReviewAttachment[]
}

export const listReviewProjects = () =>
  api.get<{ ok: boolean; data: ReviewProject[] }>('/project-review/projects')

export const uploadReviewFile = (pid: number, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post(`/project-review/${pid}/attachments`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const deleteReviewFile = (pid: number, aid: number) =>
  api.delete(`/project-review/${pid}/attachments/${aid}`)

export const reviewPreviewUrl = (pid: number, aid: number) =>
  `/api/project-review/${pid}/attachments/${aid}/preview`

export const reviewDownloadUrl = (pid: number, aid: number) =>
  `/api/project-review/${pid}/attachments/${aid}/download`
