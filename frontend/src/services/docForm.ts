import api from './api'

export type FieldType = 'text' | 'textarea' | 'number' | 'date' | 'select' | 'table'
export type FieldLayout = 'inline' | 'block'

export type TableRow = Record<string, string>
export type FieldValue = string | number | TableRow[]

export interface DocField {
  key: string
  label: string
  type: FieldType
  layout: FieldLayout
  options?: string[]
  columns?: { key: string; label: string }[]
  required?: boolean
}
export interface DocSection {
  key: string
  title: string
  fields: DocField[]
}
export interface DocTemplate {
  key: string
  name: string
  subtitle?: string
  sections: DocSection[]
}

export interface DocFormData {
  id: number
  project_id: number
  template_key: string
  data: Record<string, FieldValue>
  status: '草稿' | '已完成'
  updated_by: string
  updated_at: string
  project_name?: string
  project_number?: string
  progress?: { filled: number; total: number }
}

export interface DocStatus {
  status: string
  filled: number
  total: number
  updated_at: string
}

export const getDocTemplate = (key: string) =>
  api.get<{ ok: boolean; data: DocTemplate }>(`/doc-forms/template/${key}`)

export const getDocStatusMap = (key: string) =>
  api.get<{ ok: boolean; data: Record<string, DocStatus> }>(`/doc-forms/status/${key}`)

export const getDocForm = (projectId: number, key: string) =>
  api.get<{ ok: boolean; data: DocFormData }>(`/doc-forms/${projectId}/${key}`)

export const saveDocForm = (
  projectId: number,
  key: string,
  body: { data?: Record<string, FieldValue>; status?: '草稿' | '已完成' },
) => api.put<{ ok: boolean; data: DocFormData }>(`/doc-forms/${projectId}/${key}`, body)

export const docWordUrl = (projectId: number, key: string) =>
  `/api/doc-forms/${projectId}/${key}/word`
