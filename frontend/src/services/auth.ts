import api from './api'

export interface UserInfo {
  username: string
  role: string
  role_cn: string
  display_name: string
  agency_code: string
  perms: string[]
  is_admin: boolean
}

export const authLogin = (username: string, password: string) =>
  api.post<{ ok: boolean; user: UserInfo }>('/auth/login', { username, password })

export const authLogout = () => api.post('/auth/logout')

export const authMe = () => api.get<{ ok: boolean; user: UserInfo }>('/auth/me')

export const authChpwd = (old: string, n1: string, n2: string) =>
  api.post('/auth/chpwd', { old, n1, n2 })
