import api from './api'

export interface ApiProviderRow {
  id: number
  name: string
  kind: 'chat' | 'embed'
  base_url: string
  model_name: string
  api_key_masked: string
  transport: 'requests' | 'curl'
  note: string
  sort: number
  last_test_ok: number | null
  last_test_at: string
  last_test_msg: string
}

export interface ApiProviderForm {
  name: string
  kind: 'chat' | 'embed'
  base_url: string
  model_name: string
  api_key?: string
  transport: 'requests' | 'curl'
  note?: string
  sort?: number
}

export const listApiProviders = () =>
  api.get<{ ok: boolean; data: ApiProviderRow[]; active_chat_id: number | null; active_embed_id: number | null }>('/api-providers')

export const createApiProvider = (body: ApiProviderForm) =>
  api.post<{ ok: boolean; data: ApiProviderRow; error?: string }>('/api-providers', body)

export const updateApiProvider = (id: number, body: Partial<ApiProviderForm>) =>
  api.put<{ ok: boolean; data: ApiProviderRow; error?: string }>(`/api-providers/${id}`, body)

export const deleteApiProvider = (id: number) =>
  api.delete<{ ok: boolean; error?: string }>(`/api-providers/${id}`)

/** 连通测试走真实外网请求，放宽超时 */
export const testApiProvider = (id: number) =>
  api.post<{ ok: boolean; msg: string; ms: number; data: ApiProviderRow }>(
    `/api-providers/${id}/test`, {}, { timeout: 70000 })

export const activateApiProvider = (id: number) =>
  api.post<{ ok: boolean; msg?: string; error?: string }>(`/api-providers/${id}/activate`)
