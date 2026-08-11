import api from './api'

/**
 * 当前处理人：项目此刻卡在谁手上（后端 services/pending_owner.py）。
 * null = 本环节无人待办（已办完/已归档/草稿）。
 */
export interface PendingEntry {
  event: string
  label: string          // 「待确认采购需求（5.1）」
  role: 'officer' | 'agency' | string
  role_label: string     // 经办人 / 代理机构
  owner: string          // 系统账号（可能为空）
  owner_name: string     // 姓名 / 代理机构名
  is_reject: boolean     // 是被驳回后的返工
  since: string          // 停留起始（本轮最后一次审批动作时间）
  waiting_days: number | null
}
export type Pending = (PendingEntry & {
  current_round: number
  others: PendingEntry[]  // 并行待处理事项（授权函/更正公告/合同/考核等）
}) | null

export interface Project {
  id: number
  number: string
  name: string
  round: number
  display_name: string
  amount: number | null
  line: string
  method: string
  demand_dept: string
  manage_dept: string
  agency_code: string
  agency_name?: string
  agency_legal_rep?: string
  agency_phone?: string
  agency_address?: string
  officer: string
  content: string
  bid_time: string
  status: string
  is_draft: boolean
  can_open: string
  bid_note: string
  supervisor: string
  representative: string
  created_at: string
  updated_at: string
  category: string
  year: string
  is_deleted: boolean
  deleted_at: string
  demand_confirmed: boolean
  demand_confirmed_by: string
  demand_confirmed_at: string
  doc_confirmed: boolean
  doc_confirmed_by: string
  doc_confirmed_at: string
  doc_agency_contact: string
  doc_agency_phone: string
  package_count?: number
  current_round?: number
  current_stage?: string        // demand_confirm|doc_confirm|announce|bid_open|result|round_failed|done
  pending_contract?: number     // 已中标未签约的包数
  contract_rdweb_submitted?: boolean  // 合同已推送 rd-web 审签
  agency_rdweb_submitted?: boolean    // 代理协议已推送 rd-web 审签
  pending?: Pending                   // 当前处理人
}

export interface Agency {
  id: number
  code: string
  name: string
  active: number
}

export interface ProjectMeta {
  agencies: Agency[]
  methods: string[]
  statuses: string[]
}

export const getProjects = (deleted = false) =>
  api.get<{ ok: boolean; data: Project[]; total: number }>(
    deleted ? '/projects?deleted=1' : '/projects'
  )

// 授权函专用：所有处于开标窗口(bid_open)的代理项目（采购部全部可见、不按经办人隔离）
export const getBidOpenProjects = () =>
  api.get<{ ok: boolean; data: Project[]; total: number }>('/projects/bid-open')

export const restoreProject = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/projects/${id}/restore`, {})

export const getProjectMeta = () =>
  api.get<ProjectMeta & { ok: boolean }>('/projects/meta')

export const getProject = (id: number) =>
  api.get<{ ok: boolean; data: Project; agencies: Agency[]; methods: string[]; statuses: string[] }>(`/projects/${id}`)

export const createProject = (data: Record<string, unknown>) =>
  api.post<{ ok: boolean; message: string; data: Project }>('/projects', data)

export const updateProject = (id: number, data: Record<string, unknown>) =>
  api.put<{ ok: boolean; message: string; data: Project }>(`/projects/${id}`, data)

export const deleteProject = (id: number) =>
  api.delete<{ ok: boolean; message: string }>(`/projects/${id}`)

// ── 项目进展图 ────────────────────────────────────────────────
export interface ProgressNode {
  key: string
  label: string
  done: boolean
  at: string
  by: string
  result_value?: string          // 开标节点：可开标/流标
  ann_status?: string            // 公告节点：草稿/待确认/已确认
  files?: { name: string; at: string; by: string }[]
  packages?: Array<Record<string, unknown>>
}
export interface ProgressRound {
  round_number: number
  status: string
  nodes: ProgressNode[]
}
export interface ProjectProgress {
  project: {
    id: number; name: string; number: string; method: string
    current_round: number; current_stage: string
    pending?: Pending
  }
  rounds: ProgressRound[]
}

export const getProjectProgress = (id: number) =>
  api.get<{ ok: boolean; data: ProjectProgress }>(`/projects/${id}/progress`)
