/**
 * rd-web 自动填报面板（支持两种模式）：
 *  - 默认：通过 Hermes 中转
 *  - directSubmitUrl 传入时：直连 rd-web Playwright 自动化接口
 *
 * 三个业务共用：代理协议审签 / 采购项目审批 / 采购合同审签。
 */
import { useState, useEffect, useRef } from 'react'
import { Card, Input, Button, Space, Tag, App, Typography, Alert } from 'antd'
import { RobotOutlined, SendOutlined } from '@ant-design/icons'
import { submitHermes, getHermesStatus, type HermesTask } from '../services/hermes'
import api from '../services/api'

const { Text } = Typography
const { TextArea } = Input

export interface HermesField { label: string; value: string; long?: boolean; readOnly?: boolean }

const STATUS_COLOR: Record<string, string> = {
  accepted: 'blue', processing: 'processing', completed: 'success', failed: 'error',
}
const STATUS_CN: Record<string, string> = {
  accepted: '已受理', processing: '填报中', completed: '已完成', failed: '失败',
}

interface DirectStatus { running: boolean; ok: boolean | null; serial_no: string; msg: string }

export default function HermesPanel({
  taskType, projectId, title, fields, contractId,
  directSubmitUrl, directStatusUrl,
}: {
  taskType: string
  projectId?: number | null
  title?: string
  fields: HermesField[]
  contractId?: number | null
  /** 若传入，绕过 Hermes 直接调用 Playwright 接口 */
  directSubmitUrl?: string
  directStatusUrl?: string
}) {
  const { message } = App.useApp()
  const [vals, setVals] = useState<Record<string, string>>(
    () => Object.fromEntries(fields.map(f => [f.label, f.value || ''])))
  const [task, setTask] = useState<HermesTask | null>(null)
  const [directStatus, setDirectStatus] = useState<DirectStatus | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  // 外部 fields 变化（项目数据加载完）时重置预填值
  useEffect(() => {
    setVals(Object.fromEntries(fields.map(f => [f.label, f.value || ''])))
  }, [fields])

  // Hermes 模式：轮询任务状态
  useEffect(() => {
    if (directSubmitUrl) return  // 直连模式不用这里
    if (timer.current) { clearInterval(timer.current); timer.current = null }
    if (task && !['completed', 'failed'].includes(task.status)) {
      timer.current = setInterval(async () => {
        try { const r = await getHermesStatus(task.task_id); setTask(r.data.data) } catch { /* ignore */ }
      }, 2000)
    }
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [task, directSubmitUrl])

  // 直连模式：轮询状态
  const pollDirect = (url: string) => {
    if (timer.current) clearInterval(timer.current)
    timer.current = setInterval(async () => {
      try {
        const r = await api.get<{ ok: boolean; data: DirectStatus }>(url)
        const d = r.data.data
        setDirectStatus(d)
        if (!d.running) {
          clearInterval(timer.current!); timer.current = null
        }
      } catch { /* ignore */ }
    }, 2500)
  }

  // 组件挂载时：检查是否有正在进行或已完成的提交，自动恢复状态
  useEffect(() => {
    if (!directStatusUrl) return
    let cancelled = false
    api.get<{ ok: boolean; data: DirectStatus }>(directStatusUrl)
      .then(r => {
        if (cancelled) return
        const d = r.data.data
        if (d.running) {
          setDirectStatus(d)
          pollDirect(directStatusUrl)
        } else if (d.ok !== null) {
          // 有历史结果（成功或失败）直接展示
          setDirectStatus(d)
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [directStatusUrl])

  const submit = async () => {
    setSubmitting(true)
    try {
      if (directSubmitUrl) {
        // 直连模式：把用户编辑后的值传给后端
        setDirectStatus({ running: true, ok: null, serial_no: '', msg: '正在提交 rd-web，请稍候（约 2–3 分钟）…' })
        await api.post(directSubmitUrl, { data: vals })
        message.success('已开始提交 rd-web，请等待结果…')
        if (directStatusUrl) pollDirect(directStatusUrl)
      } else {
        const r = await submitHermes({ task_type: taskType, project_id: projectId, title, data: vals, contract_id: contractId })
        setTask(r.data.data)
        message.success('已提交给 Hermes，正在自动填报 rd-web…')
      }
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '提交失败')
      if (directSubmitUrl) setDirectStatus(null)
    } finally { setSubmitting(false) }
  }

  const isDirect = !!directSubmitUrl
  const isRunning = isDirect ? directStatus?.running : (task && !['completed', 'failed'].includes(task.status))
  const isSuccess = isDirect ? (directStatus && !directStatus.running && directStatus.ok === true) : (task?.status === 'completed')
  const isError   = isDirect ? (directStatus && !directStatus.running && directStatus.ok === false) : (task?.status === 'failed')

  return (
    <Card size="small"
      title={<span><RobotOutlined /> {isDirect ? '直接提交到 rd-web 审签' : '让 Hermes 自动填报 rd-web'}</span>}
      styles={{ body: { paddingTop: 12 } }}>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
        message={isDirect
          ? '核对/补全下方字段后点「提交到rd-web」，系统将自动打开浏览器填报并提交审签（约需 2–3 分钟）。'
          : '核对/补全下列信息后点「提交」，Hermes 会自动去 rd-web 填写并提交审签。'} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {fields.map(f => (
          <div key={f.label} style={{ gridColumn: f.long ? '1 / -1' : 'auto' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>{f.label}</Text>
            {f.long
              ? <TextArea value={vals[f.label] ?? ''} rows={2} readOnly={f.readOnly}
                  onChange={e => setVals(v => ({ ...v, [f.label]: e.target.value }))} />
              : <Input value={vals[f.label] ?? ''} readOnly={f.readOnly}
                  onChange={e => setVals(v => ({ ...v, [f.label]: e.target.value }))} />}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Button type="primary" icon={<SendOutlined />} loading={submitting || !!isRunning}
          disabled={!!isRunning} onClick={submit}>
          {isDirect ? '提交到 rd-web 审签' : '提交，让 Hermes 填报'}
        </Button>
        {/* Hermes 进度 */}
        {!isDirect && task && (
          <Space>
            <Tag color={STATUS_COLOR[task.status] || 'default'}>{STATUS_CN[task.status] || task.status}</Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>{task.progress || task.message}</Text>
          </Space>
        )}
        {/* 直连进度 */}
        {isDirect && directStatus?.running && (
          <Text type="secondary" style={{ fontSize: 12 }}>{directStatus.msg}</Text>
        )}
      </div>

      {/* 成功 */}
      {isSuccess && (
        <Alert type="success" showIcon style={{ marginTop: 10 }}
          message={isDirect
            ? `已成功提交到 rd-web 审签！${directStatus?.serial_no ? `流水号：${directStatus.serial_no}` : ''}`
            : `Hermes 已完成填报并提交审签。${(task as HermesTask)?.result ? '（' + (task as HermesTask).result + '）' : ''}`} />
      )}
      {/* 失败 */}
      {isError && (
        <Alert type="error" showIcon style={{ marginTop: 10 }}
          message={isDirect
            ? `提交失败：${directStatus?.msg || '未知错误'}`
            : `填报失败：${(task as HermesTask)?.message}`} />
      )}
    </Card>
  )
}
