import api from './api'

export interface DistAttachment {
  id: number
  distribution_id: number
  category?: string          // 附件 / 审签表
  original_name: string
  saved_name: string
  file_size: number
  mime_type: string
  uploaded_by: string
  uploaded_at: string
}

export interface Distribution {
  id: number
  serial_no: string
  originator: string
  form_type: string
  name: string
  content: string
  budget: number | null
  price_limit: number | null
  method: string
  org_form: string
  manage_dept: string
  demand_dept: string
  project_number: string
  extra: string          // 各流程专有字段(JSON字符串)
  is_central: number
  officer: string
  agency_code: string
  agency_name: string
  source: string
  status: string
  project_id: number | null
  created_by: string
  created_at: string
  updated_at: string
  attachments: DistAttachment[]
}

export const listDistributions = () =>
  api.get<{ ok: boolean; data: Distribution[] }>('/distributions')

export const createDistribution = (data: Partial<Distribution>) =>
  api.post<{ ok: boolean; data: Distribution }>('/distributions', data)

export const updateDistribution = (id: number, data: Partial<Distribution>) =>
  api.put<{ ok: boolean; data: Distribution }>(`/distributions/${id}`, data)

export const deleteDistribution = (id: number) =>
  api.delete<{ ok: boolean }>(`/distributions/${id}`)

export const reassignAgency = (id: number, agency_code?: string) =>
  api.post<{ ok: boolean; data: Distribution }>(`/distributions/${id}/reassign-agency`, { agency_code })

export const uploadDistAttachment = (did: number, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post(`/distributions/${did}/attachments`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const deleteDistAttachment = (did: number, aid: number) =>
  api.delete(`/distributions/${did}/attachments/${aid}`)

export const distAttachmentPreviewUrl = (did: number, aid: number) =>
  `/api/distributions/${did}/attachments/${aid}/preview`

export const distAttachmentDownloadUrl = (did: number, aid: number) =>
  `/api/distributions/${did}/attachments/${aid}/download`

// 合并选中的 PDF 为一个 PDF（一键打印）
export const distPrintUrl = (did: number, ids: number[]) =>
  `/api/distributions/${did}/print?ids=${ids.join(',')}`

export const scrapeRdweb = () =>
  api.post<{ ok: boolean; message?: string; error?: string }>('/distributions/scrape-rdweb')

export const scrapeStatus = () =>
  api.get<{ ok: boolean; data: { running: boolean; last_msg: string } }>('/distributions/scrape-status')

// ── rd-web 办理动作（接收/驳回/撤回，后端 Playwright RPA，异步）──
export const rdwebAction = (
  did: number, action: 'accept' | 'reject' | 'withdraw', officer?: string, opinion?: string,
) =>
  api.post<{ ok: boolean; message?: string; error?: string }>(
    `/distributions/${did}/rdweb-action`, { action, officer, opinion })

export const rdwebActionStatus = () =>
  api.get<{ ok: boolean; data: { running: boolean; last_msg: string; ok: boolean | null; action?: string; serial?: string } }>(
    '/distributions/rdweb-action-status')

// ── rd-web 账号维护 ──
export interface RdwebAccount {
  id: number
  owner: string
  phone: string
  password: string
  usage: string     // 分发 / 执行
  note: string
  updated_at: string
}
export const listRdwebAccounts = () =>
  api.get<{ ok: boolean; data: RdwebAccount[] }>('/distributions/rdweb-accounts')
export const createRdwebAccount = (data: Partial<RdwebAccount>) =>
  api.post('/distributions/rdweb-accounts', data)
export const updateRdwebAccount = (id: number, data: Partial<RdwebAccount>) =>
  api.put(`/distributions/rdweb-accounts/${id}`, data)
export const deleteRdwebAccount = (id: number) =>
  api.delete(`/distributions/rdweb-accounts/${id}`)

// 导出 Excel（按时间范围/采购方式[多选]筛选）。返回可直接下载的 URL。
export const distExportUrl = (p: { date_from?: string; date_to?: string; methods?: string[] }) => {
  const qs = new URLSearchParams()
  if (p.date_from) qs.set('date_from', p.date_from)
  if (p.date_to) qs.set('date_to', p.date_to)
  if (p.methods && p.methods.length) qs.set('methods', p.methods.join(','))
  return `/api/distributions/export?${qs.toString()}`
}
