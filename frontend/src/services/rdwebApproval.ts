import api from './api'

/** rd-web 采购项目审批：要件推送（②采购文件确认函 ③授权函 ④采购结果确认函）。 */
export type ApprovalPushKind = 'doc_confirm' | 'auth_letter' | 'result'

export interface ApprovalPushState {
  running: boolean
  ok: boolean | null
  serial_no?: string
  msg?: string
  round_number?: number
}

/** 后端在「经办人确认」的响应里带回来的自动推送结果 */
/** 自动推送还包括①委托代理协议、⑤合同审签单（走的是各自的老接口） */
export type AutoPushKind = ApprovalPushKind | 'agency_agreement' | 'contract'

export interface AutoPushInfo {
  auto?: boolean
  ok?: boolean
  kind?: AutoPushKind
  msg?: string
  round?: number
  reason?: string
}

export const KIND_LABEL: Record<ApprovalPushKind, string> = {
  doc_confirm: '采购文件确认函',
  auth_letter: '授权函',
  result: '采购结果确认函',
}

const AUTO_LABEL: Record<AutoPushKind, string> = {
  ...KIND_LABEL,
  agency_agreement: '委托代理协议',
  contract: '合同审签单',
}

export const pushApproval = (projectId: number, kind: ApprovalPushKind, round?: number) =>
  api.post(`/rdweb/approval/${projectId}/${kind}`, round ? { round } : {})

export const getApprovalStatus = (projectId: number) =>
  api.get<{ ok: boolean; auto_push: boolean; data: Record<string, ApprovalPushState> }>(
    `/rdweb/approval/${projectId}/status`)

export const setAutoPush = (enabled: boolean) =>
  api.post('/rdweb/approval/auto-push', { enabled })

/** 确认接口返回里若带 rdweb_push，转成一句给人看的话（没有就返回空串）。 */
export function autoPushText(info?: AutoPushInfo): string {
  if (!info || !info.auto) return info?.reason ? `未自动推送 rd-web：${info.reason}` : ''
  if (info.ok) return `已自动推送「${info.kind ? AUTO_LABEL[info.kind] : '要件'}」到 rd-web 盖章，稍后在按钮上看结果`
  return `自动推送 rd-web 未启动：${info.msg || '未知原因'}`
}
