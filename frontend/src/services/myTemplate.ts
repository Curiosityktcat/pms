import api from './api'

// ── 我的模板库（按登录用户隔离，可上传/删除，供审签附件等处选用）──────
export interface MyTemplate {
  name: string
  size: number
  updated_at: string
}

export const listMyTemplates = () =>
  api.get<{ ok: boolean; data: MyTemplate[] }>('/my-templates')

export const uploadMyTemplate = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ ok: boolean; data: MyTemplate[] }>('/my-templates', fd,
    { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const deleteMyTemplate = (name: string) =>
  api.delete<{ ok: boolean; data: MyTemplate[] }>(
    `/my-templates/${encodeURIComponent(name)}`)
