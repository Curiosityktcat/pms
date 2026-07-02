import api from './api'

export interface Presence {
  count: number
}

/** 上报当前用户在线并取回在线人数 + 名单。前端刷新/轮询时调用。 */
export const pingPresence = () =>
  api.get<{ ok: boolean; data: Presence }>('/presence/ping')
