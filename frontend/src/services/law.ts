import api from './api'

export interface Law {
  id: number
  ycait_id: number | null
  source: string
  source_url: string
  level: string
  issue_unit: string
  issue_date: string
  implementation_date: string
  expiration_date: string
  timeliness: string
  region: string
  category: string
  law_number: string
  title: string
  alias_title: string
  catalog_num: number | null
  catalog_category: string
  // 详情附加
  notify_title?: string
  info_content?: string
  info_inscribe?: string
  full_text?: string
  body_json?: string
}

export interface LawListResp {
  ok: boolean
  items: Law[]
  total: number
  page: number
  page_size: number
}

export interface LawLevelsResp {
  ok: boolean
  levels: { level: string; count: number }[]
  total: number
  catalog_total: number
}

export const getLaws = (params: {
  keyword?: string
  level?: string
  region?: string
  timeliness?: string
  catalog_only?: boolean
  page?: number
  page_size?: number
}) => api.get<LawListResp>('/laws', { params })

export const getLawLevels = () => api.get<LawLevelsResp>('/laws/levels')

export const getLawDetail = (id: number) =>
  api.get<{ ok: boolean; data: Law }>(`/laws/${id}`)
