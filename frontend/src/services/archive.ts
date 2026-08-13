import api from './api'

export interface ArchiveItem {
  id: number
  number: string
  name: string
  officer: string
  manage_dept: string
  agency_code: string
  status: string
  method?: string
  created_at?: string
  archived: boolean
  auth_letter_count: number
  contract_count: number
  result_count: number
}

export const listArchive = () =>
  api.get<{ ok: boolean; data: ArchiveItem[] }>('/archive')

export const archiveProject = (id: number) =>
  api.post(`/archive/${id}`)

export const revokeArchive = (id: number) =>
  api.post(`/archive/${id}/revoke`)

export const printBundleUrl = (id: number) =>
  `/api/archive/${id}/print-bundle`

// ── 归档「文件夹视图」：文件夹 + 文件项（每项自带下载/预览 URL） ──────────
export interface ArchiveTreeItem {
  name: string
  size: number
  url: string          // 下载 URL（浏览器保存）
  preview_url: string  // 预览 URL（内联，供 FilePreviewModal 渲染）
}
export interface ArchiveTreeFolder { folder: string; items: ArchiveTreeItem[] }

export const archiveTree = (id: number) =>
  api.get<{ ok: boolean; data: ArchiveTreeFolder[] }>(`/archive/${id}/tree`)
