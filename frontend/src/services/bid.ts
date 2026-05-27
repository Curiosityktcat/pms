import api from './api'
import type { Project } from './project'

export const getBidList = () =>
  api.get<{ ok: boolean; data: Project[] }>('/bid')

export const markBid = (pid: number, value: '可开标' | '流标') =>
  api.post<{ ok: boolean; message: string }>(`/bid/${pid}/mark`, { value })
