import api from './api'
import type { Project } from './project'

export const getBidList = () =>
  api.get<{ ok: boolean; data: Project[] }>('/bid')

// 可开标：单步生效（代理或经办人）
export const markCanOpen = (pid: number) =>
  api.post<{ ok: boolean; message: string }>(`/bid/${pid}/can-open`, {})

// 流标第一步：代理机构提交流标 + 原因
export const proposeBidFail = (pid: number, reason: string) =>
  api.post<{ ok: boolean; message: string }>(`/bid/${pid}/propose-fail`, { reason })

// 流标第二步：经办人确认
export const confirmBidFail = (pid: number) =>
  api.post<{ ok: boolean; message: string }>(`/bid/${pid}/confirm-fail`, {})

// 撤回待确认的流标
export const revokeBidFail = (pid: number) =>
  api.post<{ ok: boolean; message: string }>(`/bid/${pid}/revoke-fail`, {})
