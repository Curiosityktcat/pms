import api from './api'

/** 向「耗子」助手提问。page 为当前页面名，用作场景上下文。返回回答文本。 */
export async function askAssistant(question: string, page: string): Promise<string> {
  const res = await api.post('/ai-assistant/ask', { question, page })
  if (!res.data?.ok) throw new Error(res.data?.error || '调用失败')
  return res.data?.data?.answer ?? ''
}

export interface AiAccount {
  display_name: string
  unlimited: boolean
  balance: number
  recharged: number
  spent: number
  price_per_million: number
  recent: { feature: string; model: string; tokens: number; cost: number; at: string }[]
}
export const getAiAccount = () =>
  api.get<{ ok: boolean; data: AiAccount }>('/ai-assistant/account')

export const aiRecharge = () =>
  api.post<{ ok: boolean; error?: string }>('/ai-assistant/recharge')

export interface KbFile { name: string; size: number }
export const listKnowledge = () =>
  api.get<{ ok: boolean; data: { files: KbFile[]; chars: number; can_manage: boolean } }>('/ai-assistant/knowledge')
export const uploadKnowledge = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/ai-assistant/knowledge', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
}
export const deleteKnowledge = (name: string) =>
  api.delete(`/ai-assistant/knowledge/${encodeURIComponent(name)}`)
