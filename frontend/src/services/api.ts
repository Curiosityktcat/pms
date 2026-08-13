import axios from 'axios'

// 普通 JSON 接口的超时：后端无响应时不让页面永久转圈。
// 注意：文件传输不能吃这个超时——291MB 上传 15s 内传不完，浏览器会中途 abort，
// 服务端拿到被截断的 multipart，Werkzeug 解析后 form/files 全空且不报错，
// 表现为「未收到文件」（2026-08-07 私人文件库上传失败的真因）。
const DEFAULT_TIMEOUT = 15000
// 文件传输的上限：对真实文件等于不限（200MB 分批在最慢的链路上也远到不了），
// 但仍留一道兜底，后端真挂了不会让页面永久转圈。
const TRANSFER_TIMEOUT = 30 * 60 * 1000

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
  timeout: DEFAULT_TIMEOUT,
})

// 文件传输放宽超时：上传（FormData）与下载（blob/arraybuffer）都有进度条反馈，
// 15s 那道闸对它们只会误伤。调用方显式写了 timeout 的（如 OCR 300s、rd-web 60s）保持原值。
api.interceptors.request.use((config) => {
  const isUpload = typeof FormData !== 'undefined' && config.data instanceof FormData
  const isBlob = config.responseType === 'blob' || config.responseType === 'arraybuffer'
  if ((isUpload || isBlob) && config.timeout === DEFAULT_TIMEOUT) {
    config.timeout = TRANSFER_TIMEOUT
  }
  return config
})

// 统一处理 401 → 跳登录
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
