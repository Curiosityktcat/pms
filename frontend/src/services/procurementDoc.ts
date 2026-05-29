import api from './api'

export interface BidCoverParams {
  agency_name?: string
  compile_date?: string
  round_number?: number
}

export const generateBidCover = (projectId: number, data: BidCoverParams) =>
  api.post(`/projects/${projectId}/bid-cover`, data, { responseType: 'blob' })
