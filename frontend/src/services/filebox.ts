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

/** 文件夹上传：每个条目带相对路径（相对所选文件夹根），后端还原子目录结构。 */
export interface UploadEntry { file: File; relpath: string }

/**
 * 单个 POST 的体积上限。分批的三个理由：
 *  ① 后端 MAX_CONTENT_LENGTH=5GB，一次全塞进去可能整批 413；
 *  ② 传到一半断掉时只损失当前这批，前面的已经落盘；
 *  ③ Werkzeug 解析 multipart 时截断会丢掉整个请求的所有字段（见 api.ts 注释），
 *    批越小，一次中断的代价越小。
 * 单个文件超过这个体积时自成一批（不再拆分——后端不支持分片续传）。
 */
const BATCH_BYTES = 200 * 1024 * 1024

/** 把条目按累计体积切成若干批。 */
function splitBatches(entries: UploadEntry[]): UploadEntry[][] {
  const batches: UploadEntry[][] = []
  let cur: UploadEntry[] = []
  let curBytes = 0
  for (const e of entries) {
    const sz = e.file.size || 0
    if (cur.length && curBytes + sz > BATCH_BYTES) {
      batches.push(cur); cur = []; curBytes = 0
    }
    cur.push(e); curBytes += sz
  }
  if (cur.length) batches.push(cur)
  return batches
}

function postBatch(
  path: string, entries: UploadEntry[], preserve: boolean,
  onProgress?: (loaded: number) => void,
) {
  const fd = new FormData()
  fd.append('path', path)
  if (preserve) fd.append('preserve_paths', '1')
  // 以相对路径作为 filename 传给后端（保留子目录时）
  entries.forEach(e => fd.append('file', e.file, preserve ? e.relpath : e.file.name))
  // 必须显式声明 multipart——否则 axios 实例默认的 application/json 会把 FormData
  // 当 JSON 序列化（文件被丢弃、body 变空）。axios 检测到 multipart 会自动补上 boundary。
  // 超时由 api.ts 的请求拦截器自动置 0（FormData 一律免超时）。
  return api.post<{ ok: boolean; message?: string }>('/filebox/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e: { loaded: number }) => onProgress?.(e.loaded),
  })
}

/**
 * 上传（自动分批，进度跨批累计）。
 * 返回体保持 { data: { ok, message } } 形状，调用方无需改动。
 */
export const uploadEntries = async (
  path: string, entries: UploadEntry[], onStat?: (s: TransferStat) => void,
) => {
  const preserve = entries.some(e => e.relpath.includes('/'))
  const batches = splitBatches(entries)
  const totalBytes = entries.reduce((s, e) => s + (e.file.size || 0), 0)
  const report = makeProgressHandler(onStat)

  let doneBytes = 0
  let okFiles = 0
  const msgs: string[] = []

  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i]
    const batchBytes = batch.reduce((s, e) => s + (e.file.size || 0), 0)
    try {
      const res = await postBatch(path, batch, preserve,
        (loaded) => report({ loaded: doneBytes + loaded, total: totalBytes }))
      okFiles += batch.length
      if (res.data?.message) msgs.push(res.data.message)
    } catch (err) {
      // 前面的批已经落盘，把进度如实告诉用户，别让人以为一个都没传
      if (okFiles > 0) {
        const e = err as { response?: { data?: { error?: string } } }
        const why = e?.response?.data?.error || '传输中断'
        throw new Error(`第 ${i + 1}/${batches.length} 批上传失败（${why}）；`
          + `前 ${okFiles} 个文件已上传成功，可只重传剩余文件`)
      }
      throw err
    }
    doneBytes += batchBytes
  }

  const message = batches.length > 1
    ? `已上传 ${okFiles} 个文件（分 ${batches.length} 批）`
    : (msgs[0] || `已上传 ${okFiles} 个文件`)
  return { data: { ok: true, message } }
}

/** 平铺上传（不保留目录结构）。 */
export const uploadFiles = (
  path: string, files: File[], onStat?: (s: TransferStat) => void,
) => uploadEntries(path, files.map(f => ({ file: f, relpath: f.name })), onStat)

/**
 * 超过这个体积就不走 blob，交给浏览器原生下载。
 * blob 下载会把整个文件读进标签页内存（378MB 的制度汇编、整库打包 zip 都会撑爆），
 * 原生下载由浏览器下载器落盘，无内存压力，也不受页面刷新影响。
 */
export const NATIVE_DOWNLOAD_BYTES = 150 * 1024 * 1024

/** 触发浏览器原生下载（带 Cookie，同源）。 */
function nativeDownload(url: string) {
  const a = document.createElement('a')
  a.href = url
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/** 带进度/速度的下载：拉成 blob 后触发浏览器保存。大文件请改用原生下载。 */
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

/** 大文件：直接走浏览器下载器，不经内存。 */
export const downloadFileNative = (path: string) => nativeDownload(downloadUrl(path))

/** 文件夹下载：后端打包 zip。体积事先未知（可能上 GB），一律走原生下载。 */
export const downloadFolderNative = (path: string) => nativeDownload(downloadFolderUrl(path))

export const downloadUrl = (path: string) =>
  `/api/filebox/download?path=${encodeURIComponent(path)}`

export const downloadFolderUrl = (path: string) =>
  `/api/filebox/download-folder?path=${encodeURIComponent(path)}`

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
