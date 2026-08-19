/**
 * 采购需求表：Agent 操作区 + 文件预览。
 *
 * 用户 2026-08-18 的要求：
 *   「按 PMS 系统的 信息+Agent操作区+文件预览 重做一下，文件预览默认小一点，
 *     占屏的 27% 左右，右上方给个按钮，点击后按 27%，45% 和完全隐藏进行调整」
 *
 * 成稿 ＝ 模板 ＋ 信息（procurement-doc-templates 那套）：左边填的信息一保存，
 * 右边点一下就能看到套打出来的成稿，不用下载下来再开 Word。
 */
import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, Progress, Space, Spin, Tag, Tooltip, Typography } from 'antd'
import {
  ReloadOutlined, DownloadOutlined, RobotOutlined,
  ColumnWidthOutlined, EyeInvisibleOutlined, FileWordOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import DemandAgentChat from './DemandAgentChat'
import api from '../services/api'
import type { DemandDocStatus } from '../services/procurementDemand'

/** 两张需求表共用同一份模板，只是接口前缀不同 */
export type DocKind = 'procurement-demands' | 'internal-bid-demands'

const docStatus = (kind: DocKind, id: number) =>
  api.get<{ ok: boolean; data: DemandDocStatus }>(`/${kind}/${id}/doc-status`)

const docUrl = (kind: DocKind, id: number, download = false) =>
  `/api/${kind}/${id}/doc${download ? '?download=1' : ''}`

const { Text } = Typography

/** 预览宽度三档：默认 27%，可切 45% 或完全隐藏 */
export type PreviewSize = 27 | 45 | 0
export const PREVIEW_SIZES: PreviewSize[] = [27, 45, 0]

export function PreviewSizeToggle(
  { value, onChange }: { value: PreviewSize; onChange: (v: PreviewSize) => void },
) {
  return (
    <Space.Compact size="small">
      {PREVIEW_SIZES.map(s => (
        <Tooltip key={s} title={s === 0
          ? '收起文件预览，Agent 操作区占满右栏'
          : `预览占屏 ${s}%`}>
          <Button
            type={value === s ? 'primary' : 'default'}
            size="small"
            icon={s === 0 ? <EyeInvisibleOutlined /> : <ColumnWidthOutlined />}
            onClick={() => onChange(s)}
          >
            {s === 0 ? '隐藏' : `${s}%`}
          </Button>
        </Tooltip>
      ))}
    </Space.Compact>
  )
}

export default function DemandDocPanel(
  { demandId, kind = 'procurement-demands', onJumpField, previewHidden = false,
    reloadToken = 0, onApplied }:
  { demandId?: number; kind?: DocKind; onJumpField?: (name: string) => void
    /** Agent 采纳后回调，外面重新拉一遍表单（值已经写进库了） */
    onApplied?: () => void
    /** 外面每保存一次就 +1，预览跟着自动重出——
     *  原来只能手动点「重新出稿」，填完保存右边还是老样子，
     *  黄新博 2026-08-19 说「预览生成的 Word 文件压根不好用」，症结就在这。 */
    reloadToken?: number
    /** 「隐藏」那一档：只收起文件预览，Agent 操作区留下并占满右栏
     *  （黄新博 2026-08-19：「可不可以只把文件预览隐藏了，然后 agent 操作区就能大一些」） */
    previewHidden?: boolean },
) {
  const [status, setStatus] = useState<DemandDocStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [previewKey, setPreviewKey] = useState(0)   // 变一下就重新拉预览
  const [agentOpen, setAgentOpen] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    if (!demandId) return
    setLoading(true); setErr('')
    docStatus(kind, demandId)
      .then(res => setStatus(res.data.data))
      .catch((e) => {
        const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
        setErr(msg || '读取出稿状态失败')
      })
      .finally(() => setLoading(false))
  }, [demandId, kind])

  const refresh = useCallback(() => {
    load()
    setPreviewKey(k => k + 1)
  }, [load])

  useEffect(() => { load() }, [load])
  // 保存后自动重出，不用人再点一次
  useEffect(() => {
    if (reloadToken) refresh()
  }, [reloadToken])          // eslint-disable-line react-hooks/exhaustive-deps

  if (!demandId) {
    return (
      <Card size="small" title="文件预览" style={{ height: '100%' }}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="先保存一次，右边就能看到套打出来的采购需求表" />
      </Card>
    )
  }

  const pct = status && status.total
    ? Math.round((status.filled / status.total) * 100) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8 }}>
      {/* ── Agent 操作区 ─────────────────────────────────────── */}
      <Card size="small" title={<span><RobotOutlined /> Agent 操作区</span>}
        // 对话开着时这张卡要能撑开，否则聊天记录挤在一条缝里
        style={(previewHidden || agentOpen)
          ? { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }
          : undefined}
        styles={{ body: { padding: '8px 12px',
                          ...((previewHidden || agentOpen)
                            ? { flex: 1, minHeight: 0, overflowY: 'auto',
                                display: 'flex', flexDirection: 'column' }
                            : {}) } }}
        extra={
          <Space size={4}>
            <Button size="small" type={agentOpen ? 'primary' : 'default'}
              ghost={!agentOpen} icon={<ThunderboltOutlined />}
              onClick={() => setAgentOpen(v => !v)}>
              {agentOpen ? '收起对话' : '让 Agent 填'}
            </Button>
            <Button size="small" icon={<ReloadOutlined />} onClick={refresh}>
              重新出稿
            </Button>
            <Button size="small" icon={<DownloadOutlined />}
              href={docUrl(kind, demandId, true)}>
              下载 Word
            </Button>
          </Space>
        }>
        {agentOpen ? (
          // 对话开着的时候，Agent 卡片整个让给它——像微信那样上面是记录、下面是输入框
          <div style={{ flex: 1, minHeight: 240 }}>
            <DemandAgentChat demandId={demandId}
              onApplied={() => { refresh(); onApplied?.() }} />
          </div>
        ) : loading && !status ? <Spin size="small" /> : status ? (
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Space size={8} wrap>
              <Text style={{ fontSize: 12 }}>信息完成度</Text>
              <Progress percent={pct} size="small" style={{ width: 140 }}
                status={pct === 100 ? 'success' : 'active'} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                已填 {status.filled}/{status.total}
              </Text>
            </Space>
            {status.missing.length > 0 && (
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  还空着（成稿里会留白，可以先出稿看看版式）：
                </Text>
                <div style={{ maxHeight: previewHidden ? 320 : 78,
                              overflowY: 'auto', marginTop: 4 }}>
                  <Space size={[4, 4]} wrap>
                    {status.missing.slice(0, 24).map(m => (
                      <Tag key={m.name} style={{ cursor: onJumpField ? 'pointer' : 'default', marginInlineEnd: 0 }}
                        onClick={() => onJumpField?.(m.name)}>
                        {m.label || m.name}
                      </Tag>
                    ))}
                    {status.missing.length > 24 && <Tag>…还有 {status.missing.length - 24} 项</Tag>}
                  </Space>
                </div>
              </div>
            )}
          </Space>
        ) : <Text type="secondary" style={{ fontSize: 12 }}>{err || '—'}</Text>}
      </Card>

      {/* ── 文件预览（「隐藏」那一档就不渲染，把地方让给 Agent 区）── */}
      {!previewHidden && (
      <Card size="small" title={<span><FileWordOutlined /> 文件预览</span>}
        style={{ flex: 1, minHeight: 0 }}
        styles={{ body: { padding: 0, height: 'calc(100% - 38px)' } }}>
        {err ? (
          <Alert type="warning" showIcon style={{ margin: 12 }}
            message="出不了稿" description={err} />
        ) : (
          <iframe
            title="采购需求表预览"
            src={`${docUrl(kind, demandId, false)}${docUrl(kind, demandId, false).includes('?') ? '&' : '?'}v=${previewKey}`}
            style={{ width: '100%', height: '100%', border: 0 }}
          />
        )}
      </Card>
      )}

    </div>
  )
}
