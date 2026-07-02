import api from './api'

// ── 私人文件库（SFTP 式目录浏览，仅黄新博） ────────────────────────
export interface FileEntry {
  name: string
  type: 'file' | 'dir'
  size: number | null
  modified: string
}

export interface DirListing {
  path: string          // 当前目录相对根的路径（根为空串）
  items: FileEntry[]
}

export const listDir = (path: string) =>
  api.get<{ ok: boolean; data: DirListing }>('/filebox/list', { params: { path } })

// ── 传输状态（上传/下载共用）：百分比 + 实时速度 + 预计剩余时间 ──────────
export interface TransferStat {
  percent: number      // 0-100（total 未知时为 0）
  loaded: number       // 已传字节
  total: number        // 总字节（未知为 0）
  speedBps: number     // 实时速度（字节/秒）
  etaSec: number       // 预计剩余秒数（未知为 0）
}

/** 把 axios 的 progress 事件转成带速度/ETA 的统计，每 ~300ms 刷新一次速度。 */
function makeProgressHandler(onStat?: (s: TransferStat) => void) {
  let lastT = Date.now()
  let lastLoaded = 0
  let speed = 0
  return (e: { loaded: number; total?: number }) => {
    if (!onStat) return
    const now = Date.now()
    const dt = (now - lastT) / 1000
    if (dt >= 0.3) {
      speed = Math.max(0, (e.loaded - lastLoaded) / dt)
      lastT = now
      lastLoaded = e.loaded
    }
    const total = e.total || 0
    const percent = total ? Math.round((e.loaded / total) * 100) : 0
    const etaSec = speed > 0 && total ? (total - e.loaded) / speed : 0
    onStat({ percent, loaded: e.loaded, total, speedBps: speed, etaSec })
  }
}

export const uploadFiles = (
  path: string, files: File[], onStat?: (s: TransferStat) => void,
) => {
  const fd = new FormData()
  fd.append('path', path)
  files.forEach(f => fd.append('file', f))
  // 必须显式声明 multipart——否则 axios 实例默认的 application/json 会把 FormData
  // 当 JSON 序列化（文件被丢弃、body 变空）。axios 检测到 multipart 会自动补上 boundary。
  return api.post<{ ok: boolean; message?: string }>('/filebox/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: makeProgressHandler(onStat),
  })
}

/** 带进度/速度的下载：拉成 blob 后触发浏览器保存。 */
export const downloadFile = async (
  path: string, filename: string, onStat?: (s: TransferStat) => void,
) => {
  const res = await api.get('/filebox/download', {
    params: { path },
    responseType: 'blob',
    onDownloadProgress: makeProgressHandler(onStat),
  })
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export const downloadUrl = (path: string) =>
  `/api/filebox/download?path=${encodeURIComponent(path)}`

export const previewUrl = (path: string) =>
  `/api/filebox/preview?path=${encodeURIComponent(path)}`

export const mkdir = (path: string, name: string) =>
  api.post('/filebox/mkdir', { path, name })

export const deletePath = (path: string) =>
  api.post('/filebox/delete', { path })

// 路径拼接工具：当前目录 + 名字 → 子路径
export const joinPath = (dir: string, name: string) => (dir ? `${dir}/${name}` : name)
// 上一级
export const parentPath = (dir: string) => {
  if (!dir) return ''
  const i = dir.lastIndexOf('/')
  return i < 0 ? '' : dir.slice(0, i)
}
