import api from './api'

export interface BidBoardProject {
  number: string
  name: string
  agency: string
  deadline: string
  deadline_iso: string
  url: string
  supervisor: string
  first_seen: string
  updated_at: string
}

export interface BidBoardData {
  ok: boolean
  items: BidBoardProject[]
  updated_at: string | null
  supervisors: string[]
  window_days: number
}

export interface RefreshResult {
  status: 'started' | 'running' | 'cooldown'
  mins_ago?: number
  wait_mins?: number
}

export const getBoardData = () =>
  api.get<BidBoardData>('/bid-board/data')

export const setBoardSupervisor = (number: string, name: string) =>
  api.post<{ ok: boolean; error?: string }>('/bid-board/supervisor', { number, name })

export const refreshBoard = () =>
  api.post<RefreshResult>('/bid-board/refresh')

export const getBoardStatus = () =>
  api.get<{ running: boolean; last_msg: string }>('/bid-board/status')

// ── 抓取模型设置 ────────────────────────────────────────────────
export interface ScraperModelConfig {
  model_api: string
  model_name: string
  api_key: string
  default_api?: string
  default_name?: string
}

export const getModelConfig = () =>
  api.get<{ ok: boolean; data: ScraperModelConfig }>('/bid-board/model-config')

export const updateModelConfig = (data: Partial<ScraperModelConfig>) =>
  api.put<{ ok: boolean; message: string }>('/bid-board/model-config', data)

export const testModelConfig = (data: Partial<ScraperModelConfig>) =>
  api.post<{ ok: boolean; message?: string; error?: string }>('/bid-board/model-config/test', data)
