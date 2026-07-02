import axios from 'axios'
import api from './api'

/** 识别引擎：paddle = PaddleOCR-VL 大模型（按 token 计费，较贵）；classic = 传统 OCR（免费） */
export type OcrEngine = 'paddle' | 'classic'

export interface OcrUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  estimated?: boolean
}

export interface OcrResult {
  filename: string
  pages: number | null
  markdown: string
  engine?: OcrEngine
  usage?: OcrUsage
  cost?: number
  balance?: number
}

/** 上传 PDF/图片，返回识别出的 Markdown。识别耗时较长，单独放宽超时。 */
export const ocrRecognize = (file: File, engine: OcrEngine = 'paddle') => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('engine', engine)
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
  api.get<{ ok: boolean; data: { online: boolean; server: string; engines?: Record<string, boolean> } }>('/ocr/health')

/** 导出识别结果为 Word / Excel / PDF（返回文件流）。 */
export type OcrExportFormat = 'docx' | 'xlsx' | 'pdf'

export const ocrExport = (markdown: string, format: OcrExportFormat, filename: string) =>
  axios.post('/api/ocr/export', { markdown, format, filename }, {
    withCredentials: true,
    responseType: 'blob',
    timeout: 180000,
  })
