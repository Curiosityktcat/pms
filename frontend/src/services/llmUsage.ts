import api from './api'

export interface UsageSummaryRow {
  username: string
  display_name: string
  calls: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost: number
  last_used: string
}

export interface AgencyBalance {
  agency_code: string
  agency_name: string
  balance: number
  updated_at: string
}

export interface BillingInfo {
  price_per_million: number
  init_balance: number
  balances: AgencyBalance[]
}

export interface UsageRecord {
  id: number
  username: string
  display_name: string
  feature: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  created_at: string
}

export const getUsageSummary = () =>
  api.get<{ ok: boolean; data: UsageSummaryRow[]; price_per_million: number }>('/llm-usage/summary')

export const getUsageRecent = (limit = 100) =>
  api.get<{ ok: boolean; data: UsageRecord[] }>(`/llm-usage/recent?limit=${limit}`)

export const getBilling = () =>
  api.get<{ ok: boolean; data: BillingInfo }>('/llm-usage/billing')

export const updatePrice = (price: number) =>
  api.put<{ ok: boolean; data: { price_per_million: number } }>('/llm-usage/price', { price })

export const updateBalance = (agency_code: string, balance: number) =>
  api.put<{ ok: boolean; data: { balance: number } }>('/llm-usage/balance', { agency_code, balance })
