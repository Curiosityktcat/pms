import api from './api'

export interface PermItem {
  key: string
  label: string
}

export interface PermGroup {
  group: string
  items: PermItem[]
}

export interface RoleInfo {
  role: string
  role_cn: string
}

export interface PermMatrix {
  ok: boolean
  catalog: PermGroup[]
  roles: RoleInfo[]
  perms: Record<string, string[]>
}

export const getPermMatrix = () => api.get<PermMatrix>('/permissions/matrix')

export const setRolePerms = (role: string, keys: string[]) =>
  api.put<{ ok: boolean; perms: string[] }>(`/permissions/${role}`, { keys })

export const resetRolePerms = (role: string) =>
  api.post<{ ok: boolean; perms: string[] }>(`/permissions/${role}/reset`)
