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

// ── 嵌入模型设置（投标审查语义检索用）────────────────────────────
export interface EmbedModelConfig {
  embed_api: string
  embed_name: string
  embed_key: string
  suggest_api?: string
  suggest_name?: string
}

export const getEmbedConfig = () =>
  api.get<{ ok: boolean; data: EmbedModelConfig }>('/bid-board/embed-config')

export const updateEmbedConfig = (data: Partial<EmbedModelConfig>) =>
  api.put<{ ok: boolean; message: string }>('/bid-board/embed-config', data)

export const testEmbedConfig = (data: Partial<EmbedModelConfig>) =>
  api.post<{ ok: boolean; message?: string; error?: string }>('/bid-board/embed-config/test', data)
