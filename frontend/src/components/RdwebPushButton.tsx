/**
 * 「推 rd-web 盖章」按钮：把本项目本轮的某个要件推到 rd-web 采购项目审批流程。
 *
 * 经办人确认要件时后端已经自动推了一次（见 routes/rdweb_approval_api.auto_push_on_confirm），
 * 这个按钮管两件事：① 看这一轮推得怎么样（单号/失败原因）；② 失败了重推。
 * 推送要跑 Playwright 走一遍登录填表，1-3 分钟，所以运行中每 5 秒轮询一次状态。
 */
import { useEffect, useRef, useState } from 'react'
import { Button, Tag, Tooltip, message, Popconfirm } from 'antd'
import { CloudUploadOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import {
  pushApproval, getApprovalStatus, KIND_LABEL,
  type ApprovalPushKind, type ApprovalPushState,
} from '../services/rdwebApproval'

export default function RdwebPushButton({
  projectId, kind, disabled, disabledHint, size = 'small',
}: {
  projectId: number
  kind: ApprovalPushKind
  disabled?: boolean
  disabledHint?: string
  size?: 'small' | 'middle'
}) {
  const [st, setSt] = useState<ApprovalPushState | null>(null)
  const timer = useRef<number | null>(null)

  const load = async () => {
    try {
      const { data } = await getApprovalStatus(projectId)
      setSt(data.data?.[kind] || null)
    } catch { /* 状态查不到不打扰用户，按钮照常可点 */ }
  }

  useEffect(() => {
    load()
    return () => { if (timer.current) window.clearInterval(timer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, kind])

  // 运行中才轮询，跑完就停，别让列表页一直打接口
  useEffect(() => {
    if (st?.running && !timer.current) {
      timer.current = window.setInterval(load, 5000)
    } else if (!st?.running && timer.current) {
      window.clearInterval(timer.current); timer.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [st?.running])

  const doPush = async () => {
    try {
      const { data } = await pushApproval(projectId, kind)
      message.success(data.msg || '已开始推送')
      setSt({ running: true, ok: null, msg: '提交中…' })
    } catch (e: any) {
      message.error(e?.response?.data?.error || '推送失败')
      load()
    }
  }

  const label = KIND_LABEL[kind]
  const pushed = st && !st.running && st.ok === true
  const failed = st && !st.running && st.ok === false

  return (
    <>
      <Tooltip title={disabled ? (disabledHint || `${label}还没生成，先补齐要件`)
        : `把「${label}」推到 rd-web 采购项目审批流程盖章`}>
        <Popconfirm
          title={`推送「${label}」到 rd-web？`}
          description={pushed ? '本轮已经推送成功过，重推会在 rd-web 里多出一张单据' : undefined}
          okText="推送" cancelText="取消" onConfirm={doPush}
          disabled={disabled || !!st?.running}
        >
          <Button size={size} icon={<CloudUploadOutlined />}
            loading={!!st?.running} disabled={disabled}>
            {st?.running ? '推送中' : pushed ? '重推 rd-web' : '推 rd-web 盖章'}
          </Button>
        </Popconfirm>
      </Tooltip>
      {pushed && (
        <Tooltip title={st?.serial_no ? `rd-web 单号 ${st.serial_no}` : st?.msg}>
          <Tag icon={<CheckCircleOutlined />} color="green" style={{ marginInlineStart: 4 }}>已推</Tag>
        </Tooltip>
      )}
      {failed && (
        <Tooltip title={st?.msg}>
          <Tag icon={<CloseCircleOutlined />} color="red" style={{ marginInlineStart: 4 }}>推送失败</Tag>
        </Tooltip>
      )}
    </>
  )
}
