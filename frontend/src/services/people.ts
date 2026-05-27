import api from './api'

export interface Person {
  id: number
  name: string
  id_card: string
  photo: string
  role_type: 'supervisor' | 'representative'
  active: number
  department: string
}

export const getSupervisors = () =>
  api.get<{ ok: boolean; data: Person[] }>('/people?role_type=supervisor')

export const getRepresentatives = () =>
  api.get<{ ok: boolean; data: Person[] }>('/people?role_type=representative')

export const generateAuthLetter = (
  projectId: number,
  supervisorId: number,
  representativeIds: number[],
  roundNumber = 1,
  bidTimeOverride = '',
) =>
  api.post(
    `/projects/${projectId}/auth-letter`,
    {
      supervisor_id: supervisorId,
      representative_ids: representativeIds,
      round_number: roundNumber,
      bid_time_override: bidTimeOverride,
    },
    { responseType: 'blob' }
  )
