import api from './api'

export interface ReviewAttachment {
  id: number
  original_name: string
  file_size: number
  uploaded_by: string
  uploaded_at: string
}

export interface ReviewProject {
  id: number
  name: string
  number: string
  method: string
  agency_code: string
  agency_name?: string
  officer: string
  current_round: number
  attachments: ReviewAttachment[]
  past_result?: boolean   // true=项目已推进过采购结果阶段，此处为历史资料查看
  // 本轮评审资料的审核状态："" 未提交 | 待确认 | 已确认 | 已驳回
  review_status?: string
  review_reject_reason?: string
  review_reject_count?: number
  review_confirmed_by?: string
  review_confirmed_at?: string
}

export const listReviewProjects = () =>
  api.get<{ ok: boolean; data: ReviewProject[] }>('/project-review/projects')

/**
 * 上传评审资料。**优先直传对象存储**，拿不到直传能力就回落老路（POST 给 PMS 中转）。
 *
 * 为什么要直传：公网走 cloudflared，免费版请求体 100MB 硬限，大附件老路必然 413；
 * 直传时字节浏览器→OSS 直连，不经过 PMS、不占家宽上行，实测 120MB 约 11 秒。
 * 为什么保留老路：OSS 故障 / 没配密钥时业务不能停，任何一步出错都自动降级，用户无感。
 */
export const uploadReviewFile = async (pid: number, file: File) => {
  try {
    const sign = await api.post<{
      ok: boolean; direct: boolean; rel_path?: string; filename?: string
      form?: Record<string, string>
    }>('/storage/sign-upload', { module: 'project_review', filename: file.name, project_id: pid })

    if (sign.data?.direct && sign.data.form) {
      const f = sign.data.form
      const fd = new FormData()
      fd.append('key', f.key)
      fd.append('policy', f.policy)
      fd.append('OSSAccessKeyId', f.OSSAccessKeyId)
      fd.append('signature', f.signature)
      fd.append('success_action_status', '200')
      fd.append('file', file)                 // file 必须放最后，OSS 要求
      const r = await fetch(f.host, { method: 'POST', body: fd })
      if (!r.ok) throw new Error(`直传失败 HTTP ${r.status}`)
      // 传完回来登记，服务端会核实对象确实存在
      return api.post(`/project-review/${pid}/attachments/register`, {
        rel_path: sign.data.rel_path, filename: file.name, size: file.size,
      })
    }
  } catch (e) {
    console.warn('[评审资料] 直传不可用，回落服务器中转：', e)
  }

  const fd = new FormData()
  fd.append('file', file)
  return api.post(`/project-review/${pid}/attachments`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const deleteReviewFile = (pid: number, aid: number) =>
  api.delete(`/project-review/${pid}/attachments/${aid}`)

/** 代理机构把已上传的评审资料提交给经办人审核 */
export const submitReview = (pid: number) =>
  api.post<{ ok: boolean; message: string }>(`/project-review/${pid}/submit`)

/** 经办人确认评审资料 */
export const confirmReview = (pid: number) =>
  api.post<{ ok: boolean; message: string }>(`/project-review/${pid}/confirm`)

/** 经办人驳回评审资料，必须写明原因（记入审批过程记录，归档留存） */
export const rejectReview = (pid: number, reason: string) =>
  api.post<{ ok: boolean; message: string }>(`/project-review/${pid}/reject`, { reason })

export const reviewPreviewUrl = (pid: number, aid: number) =>
  `/api/project-review/${pid}/attachments/${aid}/preview`

export const reviewDownloadUrl = (pid: number, aid: number) =>
  `/api/project-review/${pid}/attachments/${aid}/download`
