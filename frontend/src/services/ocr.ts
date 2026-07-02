import axios from 'axios'
import api from './api'

export interface OcrResult {
  filename: string
  pages: number | null
  markdown: string
}

/** 上传 PDF/图片，返回识别出的 Markdown。识别耗时较长，单独放宽超时。 */
export const ocrRecognize = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return axios.post<{ ok: boolean; data: OcrResult; error?: string }>(
    '/api/ocr/recognize',
    fd,
    {
      withCredentials: true,
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    },
  )
}

/** 探测识别服务是否在线。 */
export const ocrHealth = () =>
  api.get<{ ok: boolean; data: { online: boolean; server: string } }>('/ocr/health')
