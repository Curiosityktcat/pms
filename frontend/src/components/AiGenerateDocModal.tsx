/**
 * AI 一键生成采购文件定稿。
 * 选择「初稿/模板」（采购文件附件）+「采购需求」（需求附件）→ DeepSeek 段落级修订 →
 * 定稿自动存为该项目采购文件附件（文件名带「AI定稿」）。按 token 计费。
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { Modal, Select, Alert, Button, App, Typography, Spin, Space } from 'antd'
import { RobotOutlined, ThunderboltOutlined } from '@ant-design/icons'
import type { Project } from '../services/project'
import {
  listDocAttachments, aiGenerateDoc, aiGenerateDocStatus,
  type DocAttachment, type AiGenStatus,
} from '../services/procurementDoc'

const { Text, Paragraph } = Typography

const isWord = (n: string) => /\.(docx?|DOCX?)$/.test(n)

export default function AiGenerateDocModal({
  project, open, onClose, onGenerated,
}: {
  project: Project | null
  open: boolean
  onClose: () => void
  onGenerated?: () => void
}) {
  const { message } = App.useApp()
  const [docs, setDocs] = useState<DocAttachment[]>([])
  const [demands, setDemands] = useState<DocAttachment[]>([])
  const [draftId, setDraftId] = useState<number>()
  const [demandId, setDemandId] = useState<number>()
  const [status, setStatus] = useState<AiGenStatus | null>(null)
  const [starting, setStarting] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }

  const poll = useCallback((pid: number) => {
    stopPoll()
    timer.current = setInterval(async () => {
      try {
        const res = await aiGenerateDocStatus(pid)
        const st = res.data.data
        setStatus(st)
        if (!st.running) {
          stopPoll()
          if (st.ok) onGenerated?.()
        }
      } catch { /* 轮询失败下次再试 */ }
    }, 5000)
  }, [onGenerated])

  useEffect(() => {
    if (!open || !project) { stopPoll(); setStatus(null); setDraftId(undefined); setDemandId(undefined); return }
    Promise.all([
      listDocAttachments(project.id, 'doc'),
      listDocAttachments(project.id, 'demand'),
    ]).then(([d1, d2]) => {
      const ds = (d1.data.data || []).filter(a => isWord(a.original_name))
      const dm = (d2.data.data || []).filter(a => isWord(a.original_name))
      setDocs(ds)
      setDemands(dm)
      if (ds.length === 1) setDraftId(ds[0].id)
      if (dm.length === 1) setDemandId(dm[0].id)
    }).catch(() => message.error('加载附件失败'))
    // 打开时同步一次状态（可能上次生成还在跑）
    aiGenerateDocStatus(project.id).then(res => {
      setStatus(res.data.data)
      if (res.data.data.running) poll(project.id)
    }).catch(() => {})
    return stopPoll
  }, [open, project, message, poll])

  const start = async () => {
    if (!project || !draftId || !demandId) {
      message.warning('请分别选择初稿/模板和采购需求文件')
      return
    }
    setStarting(true)
    try {
      await aiGenerateDoc(project.id, draftId, demandId)
      setStatus({ running: true, ok: null, msg: 'AI 生成中（约 2~5 分钟）…' })
      poll(project.id)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '启动失败')
    } finally {
      setStarting(false)
    }
  }

  const opt = (a: DocAttachment) => ({
    value: a.id,
    label: `${a.original_name}（${a.uploaded_by} · ${(a.uploaded_at || '').slice(0, 10)}）`,
  })

  return (
    <Modal
      title={<><RobotOutlined /> AI 生成采购文件定稿{project ? ` — ${project.name}` : ''}</>}
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
      width={640}
    >
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 12 }}
        message="按 token 计费（一次约 2~4 万 token），代理机构从 AI 余额扣费"
        description="AI 依据采购需求逐段修订初稿：修正不一致的预算/限价/参数，补充缺失的技术要求与评分标准；原文件版式保留。生成的定稿仅供参考，须人工复核后再确认。"
      />
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Text strong>① 初稿 / 模板文件</Text>（采购文件附件，Word 格式）
          <Select style={{ width: '100%', marginTop: 4 }} placeholder="选择初稿或模板"
            value={draftId} onChange={setDraftId} options={docs.map(opt)} />
        </div>
        <div>
          <Text strong>② 采购需求文件</Text>（需求附件，Word 格式）
          <Select style={{ width: '100%', marginTop: 4 }} placeholder="选择采购需求"
            value={demandId} onChange={setDemandId} options={demands.map(opt)} />
        </div>

        {status?.running && (
          <Alert type="info" showIcon icon={<Spin size="small" />}
            message={status.msg || 'AI 生成中…'}
            description="可关闭此窗口，生成完成后到「采购文件」附件里查看（AI定稿）文件。" />
        )}
        {status && !status.running && status.ok === true && (
          <Alert type="success" showIcon message={status.msg}
            description={
              <>
                <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 4 }}>
                  {status.summary}
                </Paragraph>
                {!!status.usage?.total_tokens && (
                  <Text type="secondary">消耗 {status.usage.total_tokens} token；
                    定稿已存入「采购文件」附件，请下载复核。</Text>
                )}
              </>
            } />
        )}
        {status && !status.running && status.ok === false && (
          <Alert type="error" showIcon message={status.msg || '生成失败'} />
        )}

        <Button type="primary" block icon={<ThunderboltOutlined />}
          loading={starting || !!status?.running}
          disabled={!draftId || !demandId}
          onClick={start}>
          {status?.running ? '生成中…' : '开始生成定稿'}
        </Button>
      </Space>
    </Modal>
  )
}
