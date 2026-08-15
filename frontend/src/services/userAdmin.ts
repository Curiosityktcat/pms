import api from './api'

export interface AdminUser {
  id: number
  username: string
  display_name: string
  role: string
  active: number
  dept_code: string
  agency_code: string
}

export interface RoleInfo { role: string; role_cn: string; count: number }
export interface DeptInfo {
  id: number; code: string; name: string; aliases: string[]; category: string
  active: number; sort_no: number; note: string
}
export interface AuditInfo {
  id: number; actor: string; actor_name: string; action: string
  target_username: string; detail: Record<string, unknown>; created_at: string
}

export const listUsers = (params: Record<string, string | number | undefined>) =>
  api.get<{ ok: boolean; data: AdminUser[]; total: number; page: number; size: number }>('/admin/users', { params })
export const listRoles = () => api.get<{ ok: boolean; data: RoleInfo[] }>('/admin/users/roles')
export const createUser = (data: Partial<AdminUser> & { password?: string }) =>
  api.post<{ ok: boolean; user: AdminUser; password: string }>('/admin/users', data)
export const updateUser = (id: number, data: Partial<AdminUser>) =>
  api.put<{ ok: boolean; user: AdminUser; warning?: string }>(`/admin/users/${id}`, data)
export const resetUserPassword = (id: number) =>
  api.post<{ ok: boolean; password: string }>(`/admin/users/${id}/reset-password`)
export const toggleUser = (id: number) => api.post(`/admin/users/${id}/toggle-active`)
export const deleteUser = (id: number) => api.delete(`/admin/users/${id}`)
export const getUserAudit = (id: number) =>
  api.get<{ ok: boolean; data: AuditInfo[] }>(`/admin/users/${id}/audit`)

export const listDepts = () => api.get<{ ok: boolean; data: DeptInfo[] }>('/admin/depts')
export const createDept = (data: Partial<DeptInfo>) => api.post('/admin/depts', data)
export const updateDept = (id: number, data: Partial<DeptInfo>) => api.put(`/admin/depts/${id}`, data)
export const deleteDept = (id: number) => api.delete(`/admin/depts/${id}`)
