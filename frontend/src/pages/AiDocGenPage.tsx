/**
 * AI 采购文件生成（独立工具，工具集合入口，不绑定项目）。
 * 上传「初稿/模板」+「采购需求」两个 Word → DeepSeek 段落级修订生成定稿 → 下载。
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import {
  Card, Upload, Button, Space, Typography, Input, App, Alert, Spin, Steps, Result,
} from 'antd'
import {
  InboxOutlined, RobotOutlined, ThunderboltOutlined, DownloadOutlined,
  FileWordOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { startDocGen, docGenStatus, docGenDownloadUrl, type DocGenStatus } from '../services/aiDocGen'

const { Title, Text, Paragraph } = Typography
const { Dragger } = Upload

function pickFile(list: UploadFile[]): File | undefined {
  return (list[0]?.originFileObj as File | undefined) || undefined
}

export default function AiDocGenPage() {
  const { message } = App.useApp()
  const [draftList, setDraftList] = useState<UploadFile[]>([])
  const [demandList, setDemandList] = useState<UploadFile[]>([])
  const [outName, setOutName] = useState('采购文件（AI定稿）')
  const [jobId, setJobId] = useState<string>()
  const [status, setStatus] = useState<DocGenStatus | null>(null)
  const [starting, setStarting] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }
  useEffect(() => stopPoll, [])

  const poll = useCallback((jid: string) => {
    stopPoll()
    timer.current = setInterval(async () => {
      try {
        const res = await docGenStatus(jid)
        setStatus(res.data.data)
        if (!res.data.data.running) stopPoll()
      } catch { stopPoll() }
    }, 5000)
  }, [])

  const dragger = (
    list: UploadFile[], setList: (l: UploadFile[]) => void, hint: string,
  ) => (
    <Dragger
      accept=".doc,.docx"
      maxCount={1}
      fileList={list}
      beforeUpload={(file) => {
        setList([{ uid: String(Date.now()), name: file.name, status: 'done',
          originFileObj: file as unknown as UploadFile['originFileObj'] }])
        return false
      }}
      onRemove={() => { setList([]); return true }}
      disabled={!!status?.running}
    >
      <p className="ant-upload-drag-icon"><InboxOutlined /></p>
      <p className="ant-upload-text">{hint}</p>
      <p className="ant-upload-hint">仅 Word（doc/docx）</p>
    </Dragger>
  )

  const run = async () => {
    const draft = pickFile(draftList)
    const demand = pickFile(demandList)
    if (!draft || !demand) { message.warning('请上传初稿/模板和采购需求两个文件'); return }
    setStarting(true)
    setStatus(null)
    try {
      const res = await startDocGen(draft, demand, outName.trim() || '采购文件（AI定稿）')
      if (!res.data.ok) throw new Error(res.data.error)
      setJobId(res.data.job_id)
      setStatus({ running: true, ok: null, msg: 'AI 生成中（约 2~5 分钟）…' })
      poll(res.data.job_id)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } }; message?: string }
      message.error(err?.response?.data?.error || err?.message || '启动失败')
    } finally {
      setStarting(false)
    }
  }

  const reset = () => {
    stopPoll(); setStatus(null); setJobId(undefined)
    setDraftList([]); setDemandList([])
  }

  const stepIdx = !status ? 0 : status.running ? 1 : 2

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', maxWidth: 920, margin: '0 auto' }}>
      <Card>
        <Title level={4} style={{ margin: 0 }}>
          <RobotOutlined /> AI 采购文件生成
        </Title>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          上传一份「初稿 / 模板」和一份「采购需求」，AI 依据需求逐段修订初稿：修正预算/限价/参数、
          补齐技术要求与评分标准，保留原文件版式，产出可复核的定稿 Word。
        </Paragraph>
      </Card>

      <Card>
        <Steps size="small" current={stepIdx} style={{ marginBottom: 20 }}
          items={[{ title: '上传文件' }, { title: 'AI 生成' }, { title: '下载定稿' }]} />

        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          message="按 token 计费（一次约 2~4 万 token）"
          description="代理机构从 AI 余额扣费，内部账号不计费。生成结果为初稿，须人工复核后使用。" />

        <Space align="start" style={{ width: '100%' }} size="large" wrap>
          <div style={{ flex: 1, minWidth: 280 }}>
            <Text strong><FileWordOutlined /> ① 初稿 / 模板</Text>
            <div style={{ marginTop: 6 }}>{dragger(draftList, setDraftList, '拖入初稿或空白模板')}</div>
          </div>
          <div style={{ flex: 1, minWidth: 280 }}>
            <Text strong><FileWordOutlined /> ② 采购需求</Text>
            <div style={{ marginTop: 6 }}>{dragger(demandList, setDemandList, '拖入采购需求文件')}</div>
          </div>
        </Space>

        <div style={{ marginTop: 16 }}>
          <Text type="secondary">导出文件名</Text>
          <Input style={{ maxWidth: 360, marginTop: 4 }} value={outName}
            onChange={e => setOutName(e.target.value)} suffix=".docx"
            disabled={!!status?.running} />
        </div>

        <div style={{ marginTop: 16 }}>
          <Button type="primary" size="large" icon={<ThunderboltOutlined />}
            loading={starting || !!status?.running}
            disabled={!pickFile(draftList) || !pickFile(demandList)}
            onClick={run}>
            {status?.running ? '生成中…' : '开始生成定稿'}
          </Button>
        </div>
      </Card>

      {status?.running && (
        <Card><Space><Spin /> <Text>{status.msg}</Text></Space>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            生成需 2~5 分钟，请保持页面打开。
          </Paragraph>
        </Card>
      )}

      {status && !status.running && status.ok === true && jobId && (
        <Card>
          <Result status="success" title={status.msg}
            subTitle={<Text type="secondary">
              {status.usage?.total_tokens ? `消耗 ${status.usage.total_tokens} token。` : ''}
              请下载后人工复核修订处。
            </Text>}
            extra={[
              <Button type="primary" key="dl" icon={<DownloadOutlined />}
                href={docGenDownloadUrl(jobId)} target="_blank">下载定稿 Word</Button>,
              <Button key="again" onClick={reset}>再生成一份</Button>,
            ]} />
          {status.summary && (
            <Alert type="info" showIcon message="AI 修订说明"
              description={<Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{status.summary}</Paragraph>} />
          )}
        </Card>
      )}

      {status && !status.running && status.ok === false && (
        <Card><Result status="error" title="生成失败" subTitle={status.msg}
          extra={<Button onClick={reset}>重试</Button>} /></Card>
      )}
    </Space>
  )
}
