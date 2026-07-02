import api from './api'

// ── 投标文件 AI 审查（条目抽取 + 分阶段审查 + 评分/比价） ────────────

export type Category = '资格' | '实质性' | '商务' | '打分'
export const CATEGORIES: Category[] = ['资格', '实质性', '商务', '打分']
export const LOT_COMMON = '通用'

export interface ReviewLot {
  lot_no: string
  name: string
  budget: string
}

export interface SummaryEntry {
  kind: string            // 分包|标的
  content: string
  source_page: number | null
}

export interface ReviewTask {
  id: number
  task_name: string
  project_id: number | null
  status: string          // draft|ocr_proc_doc|extracting|criteria_ready|done|failed
  error_msg: string
  progress: string
  proc_doc_name: string
  has_proc_doc_ocr: boolean
  eval_method: string     // 综合评分法|最低评标价法|''=未识别
  price_score_max: string
  price_formula: string
  lots: ReviewLot[]
  summary: SummaryEntry[]
  created_by: string
  created_at: string
  updated_at: string
  criteria_count?: number
  result_count?: number
  criteria?: ReviewCriteria[]
  results?: ReviewResult[]
}

export interface ReviewCriteria {
  id: number
  task_id: number
  seq: number
  category: Category
  lot_no: string
  content: string
  max_score: number | null
  score_rule: string
  source_page: number | null
}

export interface ReviewResultFile {
  id: number
  file_name: string
  seq: number
}

export interface ReviewResult {
  id: number
  task_id: number
  bid_file_name: string   // 投标方名称
  lot_no: string
  bid_price: string
  price_page: string
  price_edited_by: string
  ocr_status: string      // pending|running|done|failed
  status: string          // pending|running|done|failed
  progress: string
  error_msg: string
  created_at: string
  files?: ReviewResultFile[]
  file_count?: number
}

export interface ReviewItem {
  id: number
  result_id: number
  criteria_id: number
  criteria_seq: number
  criteria_content: string
  category: Category
  lot_no: string
  max_score: number | null
  score_rule: string
  verdict: string         // 满足|不满足|未找到（判定类）
  evidence_page: string
  evidence_text: string
  confidence: string
  ai_score: number | null
  ai_reason: string
  final_score: number | null
  note: string
  reviewed_by: string
}

export interface SummaryRow {
  result_id: number
  bid_file_name: string
  lot_no: string
  bid_price: number | null
  price_edited_by: string
  qual_fails: number[]
  qual_unfound: number[]
  compliance_fails: number[]
  compliance_unfound: number[]
  tech_score: number
  price_score: number | null
  total: number | null
  rank: number | null
  eliminated: string      // 资格性淘汰|符合性淘汰|''
}

export interface TaskSummary {
  eval_method: string
  price_score_max: string
  price_formula: string
  groups: { lot_no: string; rows: SummaryRow[] }[]
}

export const listTasks = () =>
  api.get<{ ok: boolean; data: ReviewTask[] }>('/bid-review/tasks')

export const createTask = (taskName: string) =>
  api.post<{ ok: boolean; data: ReviewTask }>('/bid-review/tasks', { task_name: taskName })

export const getTask = (tid: number) =>
  api.get<{ ok: boolean; data: ReviewTask }>(`/bid-review/tasks/${tid}`)

export const updateTask = (tid: number, data: {
  eval_method?: string; price_score_max?: string; price_formula?: string
  lots?: ReviewLot[]; summary?: SummaryEntry[]
}) =>
  api.put<{ ok: boolean; data: ReviewTask }>(`/bid-review/tasks/${tid}`, data)

export const deleteTask = (tid: number) =>
  api.delete(`/bid-review/tasks/${tid}`)

export const getTaskStatus = (tid: number) =>
  api.get<{ ok: boolean; data: { status: string; error_msg: string; progress: string; criteria_count: number } }>(
    `/bid-review/tasks/${tid}/status`)

export const uploadProcDocUrl = (tid: number) => `/api/bid-review/tasks/${tid}/proc-doc`

export interface CriteriaFields {
  content?: string
  category?: Category
  lot_no?: string
  max_score?: number | null
  score_rule?: string
  seq?: number
}

export const addCriteria = (tid: number, data: CriteriaFields) =>
  api.post(`/bid-review/tasks/${tid}/criteria`, data)

export const updateCriteria = (tid: number, cid: number, data: CriteriaFields) =>
  api.put(`/bid-review/tasks/${tid}/criteria/${cid}`, data)

export const deleteCriteria = (tid: number, cid: number) =>
  api.delete(`/bid-review/tasks/${tid}/criteria/${cid}`)

export const uploadBidFileUrl = (tid: number) => `/api/bid-review/tasks/${tid}/results`

export interface UploadStat {
  percent: number       // 0-100
  rate: number          // 字节/秒（瞬时）
  estimated: number     // 预计剩余秒数
}
type ProgressCb = (stat: UploadStat) => void

// multipart 上传配置：覆盖实例默认的 application/json 头（否则后端无法解析 files），
// 并透传上传进度/速率（axios 自带 rate/estimated 计算）。
function uploadCfg(onProgress?: ProgressCb) {
  return {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e: { loaded: number; total?: number; rate?: number; estimated?: number }) => {
      if (onProgress && e.total) {
        onProgress({
          percent: Math.round((e.loaded / e.total) * 100),
          rate: e.rate || 0,
          estimated: e.estimated || 0,
        })
      }
    },
  }
}

// 新建投标方并一次上传其全部文件
export const createSupplier = (tid: number, label: string, lotNo: string,
  files: File[], onProgress?: ProgressCb) => {
  const fd = new FormData()
  fd.append('label', label)
  fd.append('lot_no', lotNo)
  files.forEach(f => fd.append('file', f))
  return api.post<{ ok: boolean; data: ReviewResult; message?: string }>(
    `/bid-review/tasks/${tid}/results`, fd, uploadCfg(onProgress))
}

// 给已有投标方追加文件
export const addResultFiles = (tid: number, rid: number, files: File[],
  onProgress?: ProgressCb) => {
  const fd = new FormData()
  files.forEach(f => fd.append('file', f))
  return api.post<{ ok: boolean; message?: string }>(
    `/bid-review/tasks/${tid}/results/${rid}/files`, fd, uploadCfg(onProgress))
}

export const deleteResultFile = (tid: number, rid: number, fid: number) =>
  api.delete(`/bid-review/tasks/${tid}/results/${rid}/files/${fid}`)

export const updateResult = (tid: number, rid: number,
  data: { bid_price?: string; lot_no?: string }) =>
  api.put<{ ok: boolean; data: ReviewResult }>(`/bid-review/tasks/${tid}/results/${rid}`, data)

export const deleteResult = (tid: number, rid: number) =>
  api.delete(`/bid-review/tasks/${tid}/results/${rid}`)

export const startReview = (tid: number, rid: number) =>
  api.post<{ ok: boolean; message: string }>(`/bid-review/tasks/${tid}/results/${rid}/start`)

export const getResultStatus = (tid: number, rid: number) =>
  api.get<{ ok: boolean; data: ReviewResult }>(`/bid-review/tasks/${tid}/results/${rid}/status`)

export const listItems = (tid: number, rid: number) =>
  api.get<{ ok: boolean; data: ReviewItem[] }>(`/bid-review/tasks/${tid}/results/${rid}/items`)

export const updateItem = (tid: number, rid: number, iid: number,
  data: { verdict?: string; final_score?: number | null; note?: string }) =>
  api.put(`/bid-review/tasks/${tid}/results/${rid}/items/${iid}`, data)

export const getSummary = (tid: number) =>
  api.get<{ ok: boolean; data: TaskSummary }>(`/bid-review/tasks/${tid}/summary`)

export const exportCsvUrl = (tid: number, rid: number) =>
  `/api/bid-review/tasks/${tid}/results/${rid}/export`

export const exportSummaryUrl = (tid: number) =>
  `/api/bid-review/tasks/${tid}/export-summary`
