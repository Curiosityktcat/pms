import api from './api'

export interface RdwebField {
  key: string
  required: boolean
  hint: string
  options?: string[]
}

export interface RdwebStatus {
  running: boolean
  ok: boolean | null
  serial_no: string
  msg: string
  last_run: number
  detail: Record<string, unknown>
}

export const getRdwebFields = () =>
  api.get<{ ok: boolean; fields: RdwebField[] }>('/rdweb/contract/fields')

export const getRdwebStatus = () =>
  api.get<{ ok: boolean; data: RdwebStatus }>('/rdweb/contract/status')

export interface RdwebAttachment {
  path: string
  name: string
}

export const submitRdweb = (data: Record<string, string>, attachments: RdwebAttachment[]) =>
  api.post<{ ok: boolean; msg?: string; error?: string }>('/rdweb/contract/submit',
    { data, attachments })

export interface RdwebMyAccount {
  ok: boolean
  configured: boolean
  phone_masked: string
  owner: string
  hint?: string
}

export const getRdwebMyAccount = () =>
  api.get<RdwebMyAccount>('/rdweb/contract/my-account')

export const saveRdwebMyAccount = (phone: string, password: string) =>
  api.post<{ ok: boolean; message?: string; error?: string }>(
    '/rdweb/contract/my-account', { phone, password })

export const uploadRdwebFile = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ ok: boolean; path: string; name: string; error?: string }>(
    '/rdweb/contract/upload', fd,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 })
}

/** 合同附件（file_path，首选）或粘贴文字 → 大模型抽取审签字段（识别较慢，放宽超时） */
export const autofillRdweb = (src: { text?: string; file_path?: string }) =>
  api.post<{ ok: boolean; data: Record<string, string>; filled: number; error?: string }>(
    '/rdweb/contract/autofill', src, { timeout: 300000 })

export interface RdwebPushRecord {
  id: number
  username: string
  display_name: string
  contract_name: string
  file_name: string
  status: 'running' | 'ok' | 'fail' | 'interrupted'
  serial_no: string
  msg: string
  created_at: string
  finished_at: string
}

export const getRdwebRecords = () =>
  api.get<{ ok: boolean; data: RdwebPushRecord[] }>('/rdweb/contract/records')
