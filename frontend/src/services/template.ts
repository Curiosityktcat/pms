import api from './api'

export interface TemplateInfo {
  key: string
  label: string
  filename: string
  exists: boolean
  size: number
  updated_at: string
}

export const listTemplates = () =>
  api.get<{ ok: boolean; data: TemplateInfo[] }>('/templates')

export const downloadTemplate = (key: string) =>
  api.get(`/templates/${key}/download`, { responseType: 'blob' })

export const replaceTemplate = (key: string, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post(`/templates/${key}`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
