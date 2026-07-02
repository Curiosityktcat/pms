import api from './api'

export interface SupervisionChannel {
  id: number
  region: string
  region_full: string
  level: string
  org_type: string
  channel: string
  name: string
  url: string
  source: string
  source_url: string
  page_title: string
  http_status: number | null
  snapshot_file: string
  fetched_at: string
}

export interface SupervisionListResp {
  ok: boolean
  items: SupervisionChannel[]
  total: number
  page: number
  page_size: number
}

export interface SupervisionFiltersResp {
  ok: boolean
  total: number
  alive: number
  regions: string[]
  org_types: { value: string; count: number }[]
  levels: { value: string; count: number }[]
}

export const getSupervision = (params: {
  keyword?: string
  region?: string
  level?: string
  org_type?: string
  page?: number
  page_size?: number
}) => api.get<SupervisionListResp>('/supervision', { params })

export const getSupervisionFilters = () =>
  api.get<SupervisionFiltersResp>('/supervision/filters')

export const getSupervisionDetail = (id: number) =>
  api.get<{ ok: boolean; data: SupervisionChannel }>(`/supervision/${id}`)
