import api from './api'

/**
 * 智能上传：公网自动绕开 Cloudflare，局域网保持原样。
 *
 * 背景（2026-08-11 实测，同机同时刻）：
 *   40MB 走公网 cloudflared → 131 秒时被 Cloudflare 免费版 100 秒源站超时掐断（524）；
 *   40MB 直传阿里云 OSS（成都）→ 4.3 秒成功。
 * 所以公网用户先把文件直传到 OSS 暂存区，再让业务接口从暂存区把它拉回本地原路径
 * （服务端 services/upload_relay.py）。业务接口的落盘位置、下载/预览/推送逻辑都没变。
 *
 * 局域网用户 `/api/storage/status` 会返回 direct_upload=false（内网直连 .12 只有 2ms、
 * 千兆、不计流量费，绕成都反而慢），这时原样走 multipart，行为与改造前完全一致。
 */

export interface UploadProgress { loaded: number; total: number; percent: number }
type OnProgress = (p: UploadProgress) => void

interface StorageStatus { direct_upload: boolean; max_mb: number; lan: boolean }

let statusCache: { at: number; val: StorageStatus } | null = null
const STATUS_TTL = 60_000

async function storageStatus(): Promise<StorageStatus> {
  const now = Date.now()
  if (statusCache && now - statusCache.at < STATUS_TTL) return statusCache.val
  try {
    const r = await api.get<{ ok: boolean } & StorageStatus>('/storage/status')
    const val = { direct_upload: !!r.data.direct_upload, max_mb: r.data.max_mb || 500, lan: !!r.data.lan }
    statusCache = { at: now, val }
    return val
  } catch {
    // 问不到就当不能直传，退回老路——宁可慢，不可传不上去
    return { direct_upload: false, max_mb: 500, lan: true }
  }
}

/** 小于这个体积不值得绕 OSS（多两趟请求，反而慢）。 */
const RELAY_MIN_BYTES = 4 * 1024 * 1024

function progressOf(onProgress?: OnProgress) {
  return (e: { loaded: number; total?: number }) => {
    if (!onProgress) return
    const total = e.total || 0
    onProgress({ loaded: e.loaded, total, percent: total ? Math.round((e.loaded / total) * 100) : 0 })
  }
}

/**
 * 把文件传到 `url`（业务接口）。
 * @param fields 业务接口需要的其它表单字段（如合同的 stage）
 */
export async function smartUpload<T = unknown>(
  url: string, file: File, fields: Record<string, string> = {}, onProgress?: OnProgress,
) {
  const st = await storageStatus()
  const useRelay = st.direct_upload && file.size >= RELAY_MIN_BYTES

  if (useRelay) {
    try {
      return await relayUpload<T>(url, file, fields, onProgress)
    } catch (err) {
      // 直传链路出问题（OSS 不可达、策略过期…）不能让人传不了东西，回落老路
      console.warn('[upload] OSS 中转失败，回落服务器中转', err)
    }
  }
  return directPost<T>(url, file, fields, onProgress)
}

/** 老路：文件字节经 PMS 服务器（局域网走这条，公网小文件也走这条）。 */
function directPost<T>(
  url: string, file: File, fields: Record<string, string>, onProgress?: OnProgress,
) {
  const fd = new FormData()
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v))
  fd.append('file', file)
  return api.post<T>(url, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: progressOf(onProgress),
  })
}

/** 新路：浏览器 → OSS 暂存区 → 业务接口凭 oss_key 取走。 */
async function relayUpload<T>(
  url: string, file: File, fields: Record<string, string>, onProgress?: OnProgress,
) {
  const sign = await api.post<{
    ok: boolean; direct: boolean; rel_path: string; reason?: string
    form: { host: string; key: string; policy: string; OSSAccessKeyId: string; signature: string }
  }>('/storage/sign-upload', { module: 'staging', filename: file.name })

  if (!sign.data.direct) throw new Error(sign.data.reason || '未启用直传')

  const f = sign.data.form
  const oss = new FormData()
  oss.append('key', f.key)
  oss.append('policy', f.policy)
  oss.append('OSSAccessKeyId', f.OSSAccessKeyId)
  oss.append('signature', f.signature)
  oss.append('file', file)          // OSS 要求 file 放最后

  // 直传不经 PMS，也就不经 api 实例（不能带 Cookie 到 OSS 去）
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', f.host, true)
    xhr.upload.onprogress = (e) => {
      if (!onProgress) return
      // 留 5% 给后面「服务器取回」那一步，进度条不至于卡在 100% 干等
      const pct = e.lengthComputable ? Math.round((e.loaded / e.total) * 95) : 0
      onProgress({ loaded: e.loaded, total: e.total || file.size, percent: pct })
    }
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300
      ? resolve()
      : reject(new Error(`OSS 直传失败 HTTP ${xhr.status}`)))
    xhr.onerror = () => reject(new Error('OSS 直传网络错误'))
    xhr.ontimeout = () => reject(new Error('OSS 直传超时'))
    xhr.timeout = 30 * 60 * 1000
    xhr.send(oss)
  })

  onProgress?.({ loaded: file.size, total: file.size, percent: 96 })

  // 业务接口凭 oss_key 把文件从暂存区取回本地原路径，其余逻辑与老路完全一致
  const fd = new FormData()
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v))
  fd.append('oss_key', sign.data.rel_path)
  fd.append('original_name', file.name)
  const res = await api.post<T>(url, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  onProgress?.({ loaded: file.size, total: file.size, percent: 100 })
  return res
}

/**
 * 与页面里原来写的 `axios.post('/api/xxx', formData)` 同形的入口。
 * 传绝对路径（带 /api 前缀）即可，内部转成 api 实例的相对路径。
 */
export function smartUploadAbs<T = unknown>(
  absUrl: string, file: File, fields: Record<string, string> = {}, onProgress?: OnProgress,
) {
  const rel = absUrl.startsWith('/api/') ? absUrl.slice(4) : absUrl
  return smartUpload<T>(rel, file, fields, onProgress)
}
