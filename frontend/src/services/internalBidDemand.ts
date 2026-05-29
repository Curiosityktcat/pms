import api from './api'

export interface BidItem {
  pkg: string        // 包号，如 "包1"
  no: string         // 编号，如 "1-1"
  name: string       // 标的名称
  unit_price: string // 单价（元）
  qty: string        // 数量
  unit: string       // 计量单位
  amount: string     // 标的金额（元），= unit_price * qty
}

export interface BidPackage {
  pkg_name: string           // 合同包名称
  budget: string             // 预算金额
  limit_price: string        // 最高限价
  review_method: string      // 评审方法：综合评分法/最低评标价法/性价比法
  price_method: string       // 定价方式：固定单价/固定总价
  allow_joint: string        // 是否支持联合体投标：是/否
  allow_subcontract: string  // 是否允许合同分包：是/否
}

export interface ReviewFactor {
  factor: string      // 评审因素
  score: string       // 评审分值
  is_objective: string // 是否客观项：是/否/空
  standard: string    // 评审标准
}

export interface InternalBidDemand {
  id: number
  project_id: number | null

  // 表头
  demand_dept: string
  manage_dept: string

  // 第一部分
  year: string
  compile_date: string
  category: string           // 货物/服务/工程
  overview: string
  has_consultant: number     // 0=否 1=是
  consultant_note: string

  // 第三部分
  proc_method: string        // 院内竞选/院内单一来源
  pkg_split: string          // 不分包采购/分包采购
  multi_year: number         // 0=否 1=是

  // 第四部分
  items_json: string         // JSON string
  packages_json: string      // JSON string

  // 第五/六部分
  tech_req: string
  biz_req: string

  // 第七部分
  special_qual: string

  // 第八部分
  review_factors_json: string // JSON string

  // 第九部分
  contract_type: string      // 多选逗号分隔
  actual_settlement: number  // 0=否 1=是
  contract_period: string
  contract_location: string
  payment_terms: string
  acceptance_standard: string
  warranty: string
  ip_ownership: string
  cost_risk: string
  breach_dispute: string
  contract_other: string
  perf_bond: number          // 0=否 1=是
  perf_bond_ratio: string
  perf_bond_method: string
  perf_bond_note: string
  quality_bond: number       // 0=否 1=是

  // 第十部分
  accept_org: string         // 自行验收/委托采购代理机构验收
  invite_supplier: number
  invite_expert: number
  invite_service: number
  invite_third: number
  accept_procedure: string
  accept_time: string
  accept_other: string
  tech_accept: string
  biz_accept: string
  accept_std: string
  accept_other2: string

  status: string             // 初稿/定稿
  created_by: string
  created_at: string
  updated_at: string

  // enriched fields
  project_name?: string
  project_number?: string
  budget_amount?: number
}

export const listInternalBidDemands = (params?: { project_id?: number; status?: string }) =>
  api.get<{ ok: boolean; data: InternalBidDemand[] }>('/internal-bid-demands', { params })

export const getInternalBidDemand = (id: number) =>
  api.get<{ ok: boolean; data: InternalBidDemand }>(`/internal-bid-demands/${id}`)

export const createInternalBidDemand = (data: Partial<InternalBidDemand>) =>
  api.post<{ ok: boolean; data: InternalBidDemand }>('/internal-bid-demands', data)

export const updateInternalBidDemand = (id: number, data: Partial<InternalBidDemand>) =>
  api.put<{ ok: boolean; data: InternalBidDemand }>(`/internal-bid-demands/${id}`, data)

export const deleteInternalBidDemand = (id: number) =>
  api.delete<{ ok: boolean }>(`/internal-bid-demands/${id}`)

export const finalizeInternalBidDemand = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/internal-bid-demands/${id}/finalize`)

export const revokeInternalBidDemand = (id: number) =>
  api.post<{ ok: boolean; message: string }>(`/internal-bid-demands/${id}/revoke`)

export const internalBidDemandWordUrl = (id: number) =>
  `/api/internal-bid-demands/${id}/word`
