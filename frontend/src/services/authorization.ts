import api from './api'

export interface PermItem { key: string; label: string }
export interface PermGroup { group: string; items: PermItem[] }
export interface AuthzUser {
  username: string; display_name: string; dept_code: string; role: string; active: number
}
export interface AuthzDept { code: string; name: string; head_name: string; active: number }
export interface AuthorizationInfo {
  id: number
  grantee_username: string
  grantee_name: string
  grantee_dept_code: string
  source: 'resolution' | 'delegate'
  granter_name: string
  granter_dept_code: string
  doc_no: string
  perm_keys: string[]
  valid_from: string
  valid_to: string
  doc_name: string
  status: string
  effective_state: string
  created_at: string
  revoked_by: string
  revoked_at: string
  revoke_reason: string
}

export const listAuthorizations = (params?: Record<string, string>) =>
  api.get<{ ok: boolean; data: AuthorizationInfo[] }>('/authorizations', { params })
export const myAuthorizations = () =>
  api.get<{ ok: boolean; data: AuthorizationInfo[] }>('/authorizations/my')
export const getAuthzCatalog = () =>
  api.get<{ ok: boolean; data: PermGroup[] }>('/authorizations/perm-catalog')
export const getAuthzUsers = () =>
  api.get<{ ok: boolean; data: AuthzUser[] }>('/authorizations/users')
export const getAuthzDepts = () =>
  api.get<{ ok: boolean; data: AuthzDept[] }>('/authorizations/depts')
export const uploadAuthzDocument = (file: File) => {
  const body = new FormData()
  body.append('file', file)
  return api.post<{ ok: boolean; path: string; name: string }>('/authorizations/upload', body)
}
export const createAuthorization = (data: Record<string, unknown>) =>
  api.post<{ ok: boolean; data: AuthorizationInfo }>('/authorizations', data)
export const revokeAuthorization = (id: number, reason: string) =>
  api.post<{ ok: boolean }>(`/authorizations/${id}/revoke`, { reason })
export const authzDocumentUrl = (id: number) => `/api/authorizations/${id}/document`

