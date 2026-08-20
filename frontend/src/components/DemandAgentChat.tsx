/**
 * 采购需求 Agent —— 对话式。
 *
 * 黄新博 2026-08-20：「可以做成像微信一样的，有消息记录，能看到我和 agent 的对话，
 * 可以直接把文件进行上传，并且直接告诉他怎么去干活」。
 *
 * 和一次性弹窗的区别：对话存下来，下次打开还在；传过的资料它后面还记得
 * （追问「质保期多久」它能答上来）；建议以卡片挂在那条回复下面，
 * 采纳过的会打上标记，回看时知道哪些已经用了。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  App, Button, Checkbox, Empty, Input, Space, Spin, Tag, Tooltip, Typography, Upload,
} from 'antd'
import {
  SendOutlined, PaperClipOutlined, RobotOutlined, UserOutlined,
  CheckCircleFilled, FileTextOutlined,
} from '@ant-design/icons'
import {
  getChat, sendChat, applyChat,
  type ChatMessage, type ChatSuggestions,
} from '../services/procurementDemand'

const { TextArea } = Input
const { Text } = Typography

function SuggestionCard(
  { msg, demandId, onApplied }:
  { msg: ChatMessage; demandId: number; onApplied: () => void },
) {
  const { message } = App.useApp()
  const sug = msg.suggestions as ChatSuggestions
  const already = new Set(msg.applied || [])
  const [picked, setPicked] = useState<Set<string>>(() => {
    const s = new Set<string>()
    Object.keys(sug?.fields || {}).forEach(k => { if (!already.has(k)) s.add(k) })
    ;(sug?.packages || []).forEach((p, i) =>
      Object.keys(p).forEach(k => { if (!already.has(`包${i + 1}·${k}`)) s.add(`${i}|${k}`) }))
    return s
  })
  const [busy, setBusy] = useState(false)

  const toggle = (k: string, on: boolean) =>
    setPicked(s => { const n = new Set(s); on ? n.add(k) : n.delete(k); return n })

  const apply = async () => {
    const f: Record<string, string> = {}
    Object.entries(sug.fields || {}).forEach(([k, v]) => { if (picked.has(k)) f[k] = v.value })
    const pkgs: Record<string, string>[] = []
    ;(sug.packages || []).forEach((p, i) => {
      const one: Record<string, string> = {}
      Object.entries(p).forEach(([k, v]) => { if (picked.has(`${i}|${k}`)) one[k] = v.value })
      pkgs[i] = one
    })
    setBusy(true)
    try {
      const r = await applyChat(demandId, msg.id, f, pkgs)
      message.success(r.data.message || '已采纳')
      onApplied()
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '采纳失败')
    } finally { setBusy(false) }
  }

  const rows: { key: string; label: string; value: string; evidence: string; done: boolean }[] = []
  Object.entries(sug?.fields || {}).forEach(([k, v]) =>
    rows.push({ key: k, label: k, value: v.value, evidence: v.evidence, done: already.has(k) }))
  ;(sug?.packages || []).forEach((p, i) =>
    Object.entries(p).forEach(([k, v]) =>
      rows.push({
        key: `${i}|${k}`, label: `合同包${i + 1} · ${k}`,
        value: v.value, evidence: v.evidence, done: already.has(`包${i + 1}·${k}`),
      })))

  if (!rows.length) return null

  return (
    <div style={{
      marginTop: 8, border: '1px solid #e6f4ff', background: '#f6fbff',
      borderRadius: 8, padding: '8px 10px',
    }}>
      <Text style={{ fontSize: 12, color: '#5f6368' }}>可以填这些（勾选后采纳）：</Text>
      {rows.map(r => (
        <div key={r.key} style={{ marginTop: 6 }}>
          <Checkbox checked={picked.has(r.key)} disabled={r.done}
            onChange={e => toggle(r.key, e.target.checked)}>
            <Text strong style={{ fontSize: 13 }}>{r.label}</Text>
            {r.done && <Tag color="green" style={{ marginLeft: 6 }}>
              <CheckCircleFilled /> 已采纳</Tag>}
          </Checkbox>
          <div style={{ marginLeft: 24, fontSize: 13, whiteSpace: 'pre-wrap' }}>{r.value}</div>
          <Tooltip title={r.evidence}>
            <div style={{
              marginLeft: 24, fontSize: 11, color: '#8c8c8c',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>依据：{r.evidence}</div>
          </Tooltip>
        </div>
      ))}
      {(sug?.notes || []).length > 0 && (
        <div style={{ marginTop: 6, fontSize: 11, color: '#8c8c8c' }}>
          {sug.notes.join('；')}
        </div>
      )}
      <div style={{ textAlign: 'right', marginTop: 8 }}>
        <Button size="small" type="primary" loading={busy}
          disabled={!picked.size} onClick={apply}>
          采纳选中的（{picked.size}）
        </Button>
      </div>
    </div>
  )
}

export default function DemandAgentChat(
  { demandId, onApplied }: { demandId?: number; onApplied?: () => void },
) {
  const { message } = App.useApp()
  const [msgs, setMsgs] = useState<ChatMessage[]>([])
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const endRef = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    if (!demandId) { setLoading(false); return }
    getChat(demandId)
      .then(r => setMsgs(r.data.data || []))
      .catch(() => { /* 读不到就当空的，不挡着人用 */ })
      .finally(() => setLoading(false))
  }, [demandId])

  useEffect(() => { load() }, [load])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, busy])

  const send = async () => {
    if (!demandId) return
    if (!text.trim() && !files.length) { message.warning('说点什么，或者传个文件'); return }
    setBusy(true)
    const myText = text.trim()
    const myFiles = files
    setText(''); setFiles([])
    try {
      const r = await sendChat(demandId, myText, myFiles)
      setMsgs(m => [...m, r.data.data.user, r.data.data.agent])
    } catch (e: unknown) {
      // 把后端说的原话显示出来。原来一律显示「没发出去」——
      // 2026-08-20 后端没重启导致 405 时，界面上只有这四个字，看不出是什么问题。
      const err = e as {
        response?: { status?: number; data?: { error?: string } }
        message?: string
      }
      const detail = err?.response?.data?.error
      const status = err?.response?.status
      message.error({
        content: detail
          || (status === 413 ? '文件太大了，传不上去'
            : status === 401 ? '登录过期了，刷新页面重新登录'
            : status ? `没发出去（HTTP ${status}）`
            : `没发出去：${err?.message || '网络不通'}`),
        duration: 6,
      })
      setText(myText); setFiles(myFiles)
    } finally { setBusy(false) }
  }

  if (!demandId) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
      description="先保存一次，就能让 Agent 帮你填了" />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* ── 消息记录 ─────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 2px', minHeight: 0 }}>
        {loading ? <div style={{ textAlign: 'center', padding: 20 }}><Spin size="small" /></div>
          : msgs.length === 0 ? (
            <div style={{ padding: '12px 8px', fontSize: 12, color: '#5f6368', lineHeight: 1.7 }}>
              把科室报的需求说明、参数表、报价单传给我，或者直接说要我干什么。<br />
              我只摘资料里有的，<b>不会替你编</b>；金额、编号、日期这类不碰。<br />
              每条建议都会附上原文依据，你点了采纳才写进去。
            </div>
          ) : msgs.map(m => {
            const mine = m.role === 'user'
            return (
              <div key={m.id} style={{
                display: 'flex', gap: 6, marginBottom: 12,
                flexDirection: mine ? 'row-reverse' : 'row',
              }}>
                <div style={{
                  width: 24, height: 24, borderRadius: 12, flexShrink: 0,
                  background: mine ? '#1a73e8' : '#34a853', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12,
                }}>
                  {mine ? <UserOutlined /> : <RobotOutlined />}
                </div>
                <div style={{ maxWidth: '82%' }}>
                  {m.text && (
                    <div style={{
                      background: mine ? '#e8f0fe' : '#f5f5f5',
                      padding: '7px 10px', borderRadius: 8,
                      fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}>{m.text}</div>
                  )}
                  {(m.files || []).length > 0 && (
                    <Space size={4} wrap style={{ marginTop: 4 }}>
                      {m.files.map((f, i) => (
                        <Tag key={i} color={f.error ? 'red' : 'blue'}
                          icon={<FileTextOutlined />}>
                          {f.name}{f.error ? `（${f.error}）` : ''}
                        </Tag>
                      ))}
                    </Space>
                  )}
                  {!mine && m.suggestions && (
                    <SuggestionCard msg={m} demandId={demandId}
                      onApplied={() => { load(); onApplied?.() }} />
                  )}
                  <div style={{
                    fontSize: 10, color: '#bbb', marginTop: 2,
                    textAlign: mine ? 'right' : 'left',
                  }}>{(m.created_at || '').replace('T', ' ').slice(5, 16)}</div>
                </div>
              </div>
            )
          })}
        {busy && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
            <div style={{
              width: 24, height: 24, borderRadius: 12, background: '#34a853',
              color: '#fff', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontSize: 12,
            }}><RobotOutlined /></div>
            <div style={{ background: '#f5f5f5', padding: '7px 10px', borderRadius: 8 }}>
              <Spin size="small" /> <Text type="secondary" style={{ fontSize: 12 }}>
                正在读…资料多的话要几十秒</Text>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* ── 输入区 ───────────────────────────────────── */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 8 }}>
        {files.length > 0 && (
          <Space size={4} wrap style={{ marginBottom: 6 }}>
            {files.map((f, i) => (
              <Tag key={i} icon={<PaperClipOutlined />} closable
                onClose={() => setFiles(v => v.filter((_, j) => j !== i))}>
                {f.name}
              </Tag>
            ))}
          </Space>
        )}
        <TextArea rows={2} value={text} disabled={busy}
          placeholder="传资料给我，或者直接说要我干什么。Enter 发送，Shift+Enter 换行"
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
          }} />
        <div style={{ display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', marginTop: 6 }}>
          <Upload multiple showUploadList={false}
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.txt"
            beforeUpload={(f) => { setFiles(v => [...v, f as File]); return false }}>
            <Button size="small" icon={<PaperClipOutlined />} disabled={busy}>
              传文件
            </Button>
          </Upload>
          <Button size="small" type="primary" icon={<SendOutlined />}
            loading={busy} onClick={send}>发送</Button>
        </div>
      </div>
    </div>
  )
}
