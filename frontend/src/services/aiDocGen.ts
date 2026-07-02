import api from './api'

export interface DocGenStatus {
  running: boolean
  ok: boolean | null
  msg: string
  summary?: string
  edits?: { idx: number; reason: string; old: string; new: string }[]
  usage?: { total_tokens: number }
  has_file?: boolean
}

export const startDocGen = (draft: File, demand: File, outName: string) => {
  const fd = new FormData()
  fd.append('draft', draft)
  fd.append('demand', demand)
  fd.append('out_name', outName)
  return api.post<{ ok: boolean; job_id: string; error?: string }>(
    '/tools/doc-gen/start', fd,
    { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const docGenStatus = (jobId: string) =>
  api.get<{ ok: boolean; data: DocGenStatus }>(`/tools/doc-gen/status/${jobId}`)

export const docGenDownloadUrl = (jobId: string) =>
  `/api/tools/doc-gen/download/${jobId}`
