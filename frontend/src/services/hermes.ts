import api from './api'

export interface HermesTask {
  task_id: string
  task_type: string
  status: string      // accepted/processing/completed/failed
  progress: string
  message: string
  result: string
  title: string
}

/** 提交一个 Hermes 自动填报任务。data 用中文字段名（接口要求）。 */
export const submitHermes = (body: {
  task_type: string; project_id?: number | null; title?: string
  action?: string; data: Record<string, string>; contract_id?: number | null
}) => api.post<{ ok: boolean; data: HermesTask; error?: string }>('/hermes/submit', body)

export const getHermesStatus = (taskId: string) =>
  api.get<{ ok: boolean; data: HermesTask }>(`/hermes/status/${encodeURIComponent(taskId)}`)

export const listHermesTasks = (params: { project_id?: number; task_type?: string }) => {
  const qs = new URLSearchParams()
  if (params.project_id) qs.set('project_id', String(params.project_id))
  if (params.task_type) qs.set('task_type', params.task_type)
  return api.get<{ ok: boolean; data: HermesTask[] }>(`/hermes/tasks?${qs.toString()}`)
}
