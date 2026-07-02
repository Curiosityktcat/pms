import api from './api'

export interface CcgpNotice {
  id: string
  notice_type: '中标公告' | '合同公告'
  title: string
  project_no: string
  purchaser: string
  agency: string
  region: string
  win_company: string
  amount: string
  notice_time: string
  source_url: string
  updated_at: string
  content?: string
}

export interface CcgpDataResp {
  ok: boolean
  items: CcgpNotice[]
  total: number
  page: number
  page_size: number
  updated_at: string | null
}

export const getCcgpData = (params: {
  type: '中标公告' | '合同公告'
  keyword?: string
  page?: number
  page_size?: number
}) => api.get<CcgpDataResp>('/ccgp/data', { params })

export const getCcgpDetail = (id: string) =>
  api.get<{ ok: boolean; data: CcgpNotice }>(`/ccgp/detail/${id}`)

export const refreshCcgp = (pages = 3) =>
  api.post<{ status: string; wait_mins?: number }>('/ccgp/refresh', { pages })

export const getCcgpStatus = () =>
  api.get<{ running: boolean; last_msg: string }>('/ccgp/status')
