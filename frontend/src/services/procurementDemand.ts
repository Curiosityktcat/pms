import api from './api'

export interface DemandItem {
  item_no: string
  category: string
  name: string
  unit_price: number
  quantity: number
  unit: string
  amount: number
  requirements: string
}

/** 流程状态：草稿 → 待分发 → 已分发 → 已立项 */
export type DemandStatus = '草稿' | '待分发' | '已分发' | '已立项'

/** 需求类型: gov=政府采购, competition=院内竞选, sole_source=单一来源, inquiry=询议价, emergency=紧急采购 */
export type DemandType = 'gov' | 'competition' | 'sole_source' | 'inquiry' | 'emergency'

export interface ProcurementDemand {
  id: number
  project_id: number | null
  project_number?: string
  demand_type: DemandType
  status: DemandStatus
  version: number
  demand_dept: string
  manage_dept: string
  project_name: string
  year: string
  compile_date: string
  category: string
  budget_amount: number
  project_overview: string
  has_related_supplier: string
  // 第二部分：需求调查
  survey_content: string
  // 第三部分：采购实施计划
  org_form: string          // gov: 采购组织形式
  budget_method: string     // gov: 预算采购方式
  procurement_method: string
  is_multi_year: string
  package_split: string
  sole_source_reason: string // 单一来源理由
  // 标的
  items: DemandItem[]
  max_price: number
  // 5-7
  tech_requirements: string
  business_requirements: string
  qualification_requirements: string
  // 第八部分（gov only）
  eval_method: string
  eval_price_score: number
  eval_tech_criteria: string
  eval_service_criteria: string
  // 第九部分
  contract_is_actual: string
  contract_period: string
  payment_terms: string
  breach_terms: string
  // 第十部分
  acceptance_procedure: string
  acceptance_time: string
  acceptance_tech: string
  acceptance_biz: string
  acceptance_standard: string
  // 第十一部分（gov only）
  risk_needed: string
  risk_measures: string
  // ── 询议价专用字段 ───────────────────────────────────────────
  inq_after_sales: string
  inq_delivery_time: string
  inq_delivery_location: string
  inq_performance_bond: string
  inq_other_requirements: string

  // ── 紧急采购专用字段 ─────────────────────────────────────────
  apply_time: string
  expected_use_time: string
  consumable_name: string
  consumable_unit_price: number
  consumable_unit: string
  apply_quantity: number
  manufacturer: string
  model_spec: string
  purpose_type: string            // 手术 / 治疗 / 检查
  license_number: string
  has_similar_product: string     // 有 / 无
  needs_companion: string         // 需要 / 无需
  surgery_name: string
  surgery_level: string
  import_domestic: string         // 进口 / 国产
  product_on_catalog: string      // 挂网产品 / 非挂网产品
  applicable_scope: string        // '1' | '2' | '3' | '4'
  clinical_use_desc: string
  attachment_path: string

  // 审签
  handler_name: string
  manager_opinion: string
  legal_opinion: string
  audit_opinion: string
  leader_opinion: string
  cfo_opinion: string
  president_opinion: string
  // 分发信息
  assigned_officer: string
  assigned_agency_code: string
  agency_name?: string
  dispatched_by: string
  dispatched_at: string
  created_by: string
  created_at: string
  updated_at: string
}

export interface DispatchPayload {
  assigned_officer: string
  assigned_agency_code?: string
}

export interface DemandPrefill {
  demand_id: number
  demand_type: DemandType   // 用于判断政府采购是否自动归档
  name: string
  category: string
  year: string
  amount: number | null
  method: string
  agency_code: string
  demand_dept: string
  manage_dept: string
  content: string
  officer: string
}

export const listDemands = (status?: string, demandType?: string) =>
  api.get<{ ok: boolean; data: ProcurementDemand[] }>('/procurement-demands', {
    params: { ...(status ? { status } : {}), ...(demandType ? { demand_type: demandType } : {}) },
  })

export const getDemand = (id: number) =>
  api.get<{ ok: boolean; data: ProcurementDemand }>(`/procurement-demands/${id}`)

export const createDemand = (data: Partial<ProcurementDemand>) =>
  api.post<{ ok: boolean; data: ProcurementDemand }>('/procurement-demands', data)

export const updateDemand = (id: number, data: Partial<ProcurementDemand>) =>
  api.put<{ ok: boolean; data: ProcurementDemand }>(`/procurement-demands/${id}`, data)

export const deleteDemand = (id: number) =>
  api.delete<{ ok: boolean }>(`/procurement-demands/${id}`)

/** 草稿 → 待分发 */
export const submitDemand = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-demands/${id}/submit`)

/** 待分发 → 草稿（撤回） */
export const recallDemand = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-demands/${id}/recall`)

/** 待分发 → 已分发（助理操作） */
export const dispatchDemand = (id: number, payload: DispatchPayload) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-demands/${id}/dispatch`, payload)

/** 已分发 → 待分发（退回，助理操作） */
export const returnDemand = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/procurement-demands/${id}/return`)

/** 获取立项预填数据（经办人操作，返回跳转到立项表单所需数据） */
export const getPrefillForProject = (id: number) =>
  api.post<{ ok: boolean; prefill: DemandPrefill }>(`/procurement-demands/${id}/create-project`)

export const getAgencies = () =>
  api.get<{ ok: boolean; data: { code: string; name: string }[] }>('/procurement-demands/agencies')

export const demandWordUrl          = (id: number) => `/api/procurement-demands/${id}/word`
export const demandTemplateUrl      = (type: string) => `/api/procurement-demands/template/${type}`

/** 上传 Excel 并解析，返回基本信息 + 标的清单 */
export const importExcel = (demandType: string, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('demand_type', demandType)
  return api.post<{
    ok: boolean
    data: { basic_data: Partial<ProcurementDemand>; items: DemandItem[] }
  }>('/procurement-demands/import-excel', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
export const demandAttachmentUrl  = (id: number) => `/api/procurement-demands/${id}/attachment`

/** 上传紧急采购附件（FormData，key="file"），需已有 demand ID */
export const uploadAttachment = (id: number, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<{ ok: boolean; path: string; original_name: string }>(
    `/procurement-demands/${id}/upload`, fd,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
}

// 兼容旧代码（已废弃，保留避免编译报错）
export const finalizeDemand = submitDemand
export const revokeDemand = recallDemand

// ── 按模板出稿：成稿 ＝ 模板 ＋ 信息 ─────────────────────────────
export interface DemandDocStatus {
  total: number
  filled: number
  missing: { name: string; label: string; kind: string }[]
}

export const getDemandDocStatus = (id: number) =>
  api.get<{ ok: boolean; data: DemandDocStatus }>(`/procurement-demands/${id}/doc-status`)

/** download=false 时后端转 PDF，直接塞进 iframe 预览 */
export const demandDocUrl = (id: number, download = false) =>
  `/api/procurement-demands/${id}/doc${download ? '?download=1' : ''}`
