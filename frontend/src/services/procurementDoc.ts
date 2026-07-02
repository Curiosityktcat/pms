import api from './api'

export interface BidCoverParams {
  agency_name?: string
  compile_date?: string
  round_number?: number
}

export const generateBidCover = (projectId: number, data: BidCoverParams) =>
  api.post(`/projects/${projectId}/bid-cover`, data, { responseType: 'blob' })

export interface ContentConfirmParams {
  agency_name?: string
  contact_person?: string
  contact_phone?: string
}

export const generateContentConfirm = (projectId: number, data: ContentConfirmParams) =>
  api.post(`/projects/${projectId}/content-confirm-word`, data, { responseType: 'blob' })

// 代理机构在系统填写内容确认表所需的联系人及联系方式
export const saveDocContact = (
  projectId: number,
  data: { contact_person: string; contact_phone: string },
) => api.post(`/projects/${projectId}/doc-contact`, data)

export type ConfirmKind = 'demand' | 'doc'

export const setDocConfirm = (
  projectId: number,
  kind: ConfirmKind,
  confirmed: boolean,
  packageCount?: number,
) =>
  api.post(`/projects/${projectId}/doc-confirm`, {
    kind,
    confirmed,
    ...(packageCount ? { package_count: packageCount } : {}),
  })

// 项目的轮次/包信息（供「第几次」弹窗、包数量展示用）
export interface ProjectPackage {
  id: number
  project_id: number
  package_no: number
  name: string
  status: string
  winner: string
  win_amount: number
  won_round: number
  contract_id: number
}
export interface ProjectRound {
  id: number
  project_id: number
  round_number: number
  demand_confirmed: number
  doc_confirmed: number
  status: string
}
// 设置/调整项目分包数量（仅第一轮、无包中标前可用）
export const setPackageCount = (projectId: number, count: number) =>
  api.post<{ ok: boolean; data: { package_count: number } }>(
    `/projects/${projectId}/packages`,
    { count },
  )

export const getProjectRounds = (projectId: number) =>
  api.get<{
    ok: boolean
    data: {
      rounds: ProjectRound[]
      packages: ProjectPackage[]
      round_packages: { round_id: number; package_id: number; result: string }[]
      current_round: number
    }
  }>(`/projects/${projectId}/rounds`)

export interface DocAttachment {
  id: number
  project_id: number
  kind: string
  original_name: string
  file_size: number
  sha256: string
  uploaded_by: string
  uploaded_at: string
}

export const listDocAttachments = (projectId: number, kind: ConfirmKind, roundNumber?: number) =>
  api.get<{ ok: boolean; data: DocAttachment[] }>(
    `/projects/${projectId}/doc-attachments?kind=${kind}` +
      (roundNumber ? `&round_number=${roundNumber}` : ''),
  )

// 采购需求确认历史：按轮次列出每一次已确认的需求快照（含当时上传的需求文件）
export interface DemandConfirmation {
  project_id: number
  project_name: string
  number: string
  agency_name: string
  round_number: number
  package_count: number
  confirmed_by: string
  confirmed_at: string
  files: DocAttachment[]
  files_round: number      // 需求文件实际所属轮次（本轮未改时沿用上一轮）
  files_inherited: boolean // 本轮无修改、沿用上一轮的需求
  revocable: boolean       // 是否允许撤回修改（最新轮且尚未进入文件确认后续）
}

export const getDemandConfirmations = () =>
  api.get<{ ok: boolean; data: DemandConfirmation[] }>('/projects/demand-confirmations')

export const getDocConfirmations = () =>
  api.get<{ ok: boolean; data: DemandConfirmation[] }>('/projects/doc-confirmations')

export const uploadDocAttachmentUrl = (projectId: number, kind: ConfirmKind) =>
  `/api/projects/${projectId}/doc-attachments?kind=${kind}`

export const downloadDocAttachment = (projectId: number, attId: number) =>
  api.get(`/projects/${projectId}/doc-attachments/${attId}`, { responseType: 'blob' })

export const docAttachmentDownloadUrl = (projectId: number, attId: number) =>
  `/api/projects/${projectId}/doc-attachments/${attId}`

export const docAttachmentPreviewUrl = (projectId: number, attId: number) =>
  `/api/projects/${projectId}/doc-attachments/${attId}/preview`

export const deleteDocAttachment = (projectId: number, attId: number) =>
  api.delete(`/projects/${projectId}/doc-attachments/${attId}`)

// AI 编制建议：对项目采购需求生成意见和建议（只读，不改文档）
// balance：代理机构账号会返回扣费后的剩余余额（元）
export const aiReviewDoc = (projectId: number) =>
  api.post<{ ok: boolean; data: { suggestions: string; model: string; balance?: number } }>(
    `/projects/${projectId}/ai-review`,
  )

// ── AI 一键生成采购文件定稿（初稿/模板 + 采购需求 → DeepSeek 段落级修订）──
export interface AiGenStatus {
  running: boolean
  ok: boolean | null
  msg: string
  summary?: string
  edits?: { idx: number; reason: string; old: string; new: string }[]
  usage?: { total_tokens: number }
}

export const aiGenerateDoc = (
  projectId: number, draftAttachmentId: number, demandAttachmentId: number,
) =>
  api.post<{ ok: boolean; msg: string }>(`/projects/${projectId}/ai-generate-doc`, {
    draft_attachment_id: draftAttachmentId,
    demand_attachment_id: demandAttachmentId,
  })

export const aiGenerateDocStatus = (projectId: number) =>
  api.get<{ ok: boolean; data: AiGenStatus }>(`/projects/${projectId}/ai-generate-doc/status`)
