/**
 * 「牛马」AI 助手：PMS 内右侧常驻面板，接 officer-agent（pi 内核）。
 * 顶替原耗子面板。仅黄新博可见（后端反代也门控）。流式回复；
 * 报告渲染成可点的文件卡片，点开即在弹窗内预览（不跳页），像微信发文件。
 *
 * 传文件：像微信一样把文件拖进面板（或点回形针选），松手即传——
 * 走 PMS 的 /doc-intake-svc/upload 反代 → OCR → 本地 Qwen 判类 → 自动归档，
 * 结果直接以文件卡片的形式回到对话里（判成什么类、归到哪个项目）。
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { Input, Button, Avatar, Spin, Typography, Modal, Tag } from 'antd'
import {
  SendOutlined, RobotOutlined, RightOutlined, FileTextOutlined,
  PaperClipOutlined, InboxOutlined, HistoryOutlined,
} from '@ant-design/icons'

const { Text } = Typography
/** 归档结果卡片：牛马收下文件、识别归档后回给用户的东西 */
type IntakeCard = {
  filename: string
  doc_type?: string        // 判成什么档案类型
  project_number?: string  // 认出的项目编号（没认出就是分类库）
  folder?: string          // 归到哪个目录
  summary?: string
  ok: boolean
}
type Msg = {
  role: 'user' | 'assistant'; content: string; report?: string
  intake?: IntakeCard; ts: string; read?: boolean
  day?: string            // YYYY-MM-DD，用来分「最近三天」与历史
}
const hhmm = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
const OPEN_KEY = 'niuma.open'
const SID_KEY = 'niuma.sid'
const LOG_KEY = 'niuma.log'          // 对话留档（本机浏览器）
const WIDTH = 360
const RECENT_DAYS = 3                 // 面板里默认只显示最近三天，更早的进「历史消息」
const KEEP_DAYS = 90                  // 留档保留期，超期自动清理，避免无限增长
const FOLD_CHARS = 220                // 超过这个长度的消息默认折叠

const dayStr = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** 读留档：顺手清掉超过保留期的，坏数据直接丢弃不影响使用 */
function loadLog(): Msg[] {
  try {
    const raw = JSON.parse(localStorage.getItem(LOG_KEY) || '[]') as Msg[]
    if (!Array.isArray(raw)) return []
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - KEEP_DAYS)
    const keep = raw.filter(m => m.day && m.day >= dayStr(cutoff))
    if (keep.length !== raw.length) localStorage.setItem(LOG_KEY, JSON.stringify(keep))
    return keep
  } catch {
    return []
  }
}

function saveLog(msgs: Msg[]) {
  try {
    localStorage.setItem(LOG_KEY, JSON.stringify(msgs.slice(-1000)))
  } catch { /* 配额满了就算了，不影响对话 */ }
}
const REPORT_RE = /\/officer-agent\/reports\/report_\d+\.html/

function sid(): string {
  let s = localStorage.getItem(SID_KEY)
  if (!s) { s = 'web_' + Math.random().toString(36).slice(2, 10); localStorage.setItem(SID_KEY, s) }
  return s
}

export default function NiumaAssistant() {
  const [open, setOpen] = useState(() => localStorage.getItem(OPEN_KEY) !== '0')
  // 从留档恢复，刷新页面/换个菜单回来对话还在
  const [msgs, setMsgs] = useState<Msg[]>(() => loadLog())
  const [historyOpen, setHistoryOpen] = useState(false)
  const [folded, setFolded] = useState<Record<number, boolean>>({})
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [tool, setTool] = useState('')
  const [preview, setPreview] = useState<string>('')   // 报告预览 URL
  const [pending, setPending] = useState<{ id: string; label: string; detail: string }[]>([])
  const [dragOver, setDragOver] = useState(false)      // 拖拽悬停高亮
  const [uploading, setUploading] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  /** 收文件：一个个传，每传完一个就往对话里加一张归档结果卡片。 */
  const takeFiles = useCallback(async (files: FileList | File[]) => {
    const arr = Array.from(files)
    if (!arr.length || uploading) return
    setUploading(true)
    for (const f of arr) {
      setMsgs((m) => [...m, {
        role: 'user', content: `📎 ${f.name}`, ts: hhmm(), day: dayStr(new Date()), read: false,
      }])
      const fd = new FormData()
      fd.append('file', f)
      try {
        const r = await fetch('/doc-intake-svc/upload', { method: 'POST', body: fd })
        const d = await r.json()
        const doc = d.doc || d.data || d
        const okFlag = r.ok && (d.ok !== false)
        setMsgs((m) => [...m, {
          role: 'assistant',
          content: okFlag ? '收到，已识别并归档：' : '这份没收进去：' + (d.error || `HTTP ${r.status}`),
          intake: okFlag ? {
            filename: f.name,
            doc_type: doc.doc_type || doc.type || '',
            project_number: doc.project_number || '',
            folder: doc.folder || doc.archive_path || '',
            summary: doc.summary || '',
            ok: true,
          } : undefined,
          ts: hhmm(), day: dayStr(new Date()),
        }])
      } catch (e) {
        setMsgs((m) => [...m, {
          role: 'assistant', content: `这份没传上去：${String(e)}`, ts: hhmm(), day: dayStr(new Date()),
        }])
      }
    }
    setUploading(false)
    setMsgs((m) => m.map((x) => x.role === 'user' ? { ...x, read: true } : x))
  }, [uploading])

  const loadPending = useCallback(async () => {
    try { const d = await (await fetch('/officer-agent/api/pending')).json(); setPending(d.actions || []) } catch { /* ignore */ }
  }, [])
  const confirmAct = async (id: string, label: string) => {
    setPending((ps) => ps.filter((x) => x.id !== id))
    try {
      const d = await (await fetch('/officer-agent/api/action/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) })).json()
      setMsgs((m) => [...m, { role: 'assistant', content: d.ok ? `✅ 已执行：${label}` : `❌ 执行失败：${d.error}`, ts: hhmm(), day: dayStr(new Date()) }])
    } catch (e) { setMsgs((m) => [...m, { role: 'assistant', content: `❌ 执行失败：${e}`, ts: hhmm(), day: dayStr(new Date()) }]) }
    loadPending()
  }
  const cancelAct = async (id: string) => {
    setPending((ps) => ps.filter((x) => x.id !== id))
    try { await fetch('/officer-agent/api/action/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) }) } catch { /* ignore */ }
  }

  useEffect(() => { localStorage.setItem(OPEN_KEY, open ? '1' : '0') }, [open])
  // 每次消息变化就落档（流式回复期间也会写，保证中途刷新不丢）
  useEffect(() => { if (msgs.length) saveLog(msgs) }, [msgs])

  // 最近三天在面板里看，更早的收进「历史消息」
  const todayStr = dayStr(new Date())
  const recentCutoff = (() => {
    const d = new Date()
    d.setDate(d.getDate() - (RECENT_DAYS - 1))
    return dayStr(d)
  })()
  const recentMsgs = msgs.filter(m => !m.day || m.day >= recentCutoff)
  const olderMsgs = msgs.filter(m => m.day && m.day < recentCutoff)
  useEffect(() => { if (open && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight }, [msgs, loading, open])

  const send = useCallback(async () => {
    const q = input.trim()
    if (!q || loading) return
    setInput(''); setTool('')
    setMsgs((m) => [...m, { role: 'user', content: q, ts: hhmm(), day: todayStr, read: false }, { role: 'assistant', content: '', ts: hhmm(), day: todayStr }])
    setLoading(true)
    let acc = ''
    try {
      const r = await fetch('/officer-agent/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: sid(), message: q }),
      })
      if (!r.ok || !r.body) throw new Error('后端未就绪(' + r.status + ')')
      const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = ''
      for (;;) {
        const { value, done } = await reader.read(); if (done) break
        buf += dec.decode(value, { stream: true })
        let i: number
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const line = buf.slice(0, i); buf = buf.slice(i + 2)
          if (!line.startsWith('data: ')) continue
          const ev = JSON.parse(line.slice(6))
          if (ev.type === 'text') {
            acc += ev.delta
            const rep = acc.match(REPORT_RE)?.[0]
            setMsgs((m) => { const n = [...m]; n[n.length - 1] = { ...n[n.length - 1], content: acc, report: rep }; return n })
          } else if (ev.type === 'tool') {
            setTool(ev.name === 'make_report' ? '正在生成汇报…' : '正在查 PMS…')
          } else if (ev.type === 'error') {
            acc += '\n（出错）' + ev.error
            setMsgs((m) => { const n = [...m]; n[n.length - 1] = { ...n[n.length - 1], content: acc }; return n })
          }
        }
      }
    } catch (e) {
      setMsgs((m) => { const n = [...m]; n[n.length - 1] = { ...n[n.length - 1], content: '（连接失败）' + String(e) }; return n })
    } finally {
      setLoading(false); setTool('')
      setMsgs((m) => m.map((x) => x.role === 'user' ? { ...x, read: true } : x))   // 用户消息标记已读
      loadPending()   // 拉取本轮提议出的待确认写操作
    }
  }, [input, loading])

  if (window.location.pathname === '/login') return null

  if (!open) {
    return (
      <div onClick={() => setOpen(true)} title="展开牛马助手"
        style={{
          position: 'fixed', right: 0, top: '40%', zIndex: 1100, cursor: 'pointer',
          background: '#1677ff', color: '#fff', padding: '14px 7px', borderRadius: '8px 0 0 8px',
          writingMode: 'vertical-rl', fontWeight: 600, letterSpacing: 3, boxShadow: '-2px 0 8px rgba(0,0,0,.15)',
        }}>🐮 牛马助手</div>
    )
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); if (!dragOver) setDragOver(true) }}
      onDragLeave={(e) => {
        // 只有真正离开整个面板才取消高亮，掠过子元素不算
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault(); setDragOver(false)
        if (e.dataTransfer.files?.length) takeFiles(e.dataTransfer.files)
      }}
      style={{
        position: 'fixed', right: 0, top: 64, bottom: 0, width: WIDTH, zIndex: 1100, background: '#fff',
        borderLeft: '1px solid #eee', boxShadow: '-2px 0 12px rgba(0,0,0,.08)', display: 'flex', flexDirection: 'column',
      }}
    >
      {/* 拖文件进来时盖一层提示，松手即传 */}
      {dragOver && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 10, background: 'rgba(22,119,255,.08)',
          border: '2px dashed #1677ff', borderRadius: 4,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          pointerEvents: 'none',
        }}>
          <InboxOutlined style={{ fontSize: 46, color: '#1677ff' }} />
          <div style={{ marginTop: 10, color: '#1677ff', fontWeight: 600 }}>松手交给牛马</div>
          <div style={{ marginTop: 4, color: '#5f6368', fontSize: 12 }}>自动识别类型并归档到对应项目</div>
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderBottom: '1px solid #f0f0f0', background: '#f0f5ff' }}>
        <Avatar style={{ background: '#fff', fontSize: 18 }}>🐮</Avatar>
        <div style={{ flex: 1 }}>
          <Text strong>牛马助手</Text>
          <div><Text type="secondary" style={{ fontSize: 12 }}>黄新博的经办人 AI · 会查PMS·会记事·会汇报</Text></div>
        </div>
        <Button type="text" size="small" icon={<HistoryOutlined />}
          onClick={() => setHistoryOpen(true)}
          title={`历史消息记录（更早的 ${olderMsgs.length} 条）`} />
        <Button type="text" size="small" icon={<RightOutlined />} onClick={() => setOpen(false)} title="收起" />
      </div>

      <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: 12, background: '#fafafa' }}>
        {recentMsgs.length === 0 && (
          <div style={{ textAlign: 'center', color: '#999', marginTop: 40 }}>
            <RobotOutlined style={{ fontSize: 30 }} />
            <div style={{ marginTop: 10, fontSize: 13 }}>
              我是牛马，替你干经办的活～<br />
              试试：「我名下待立项的项目」<br />「帮我做份工作汇报」<br />「记住：立项名称不带科室」
              <div style={{ marginTop: 12, color: '#1677ff' }}>
                📎 也可以直接把文件拖进来，我识别完自动归档
              </div>
            </div>
          </div>
        )}
        {olderMsgs.length > 0 && (
          <div style={{ textAlign: 'center', marginBottom: 10 }}>
            <Button size="small" type="link" icon={<HistoryOutlined />}
              onClick={() => setHistoryOpen(true)}>
              查看更早的 {olderMsgs.length} 条历史消息
            </Button>
          </div>
        )}
        {recentMsgs.map((m, i) => {
          const isUser = m.role === 'user'
          // 长回复默认折叠——牛马查完 PMS 常常吐一大段，全展开会把前面的对话顶没
          const isLast = i === recentMsgs.length - 1
          const longMsg = (m.content || '').length > FOLD_CHARS
          const isFolded = longMsg && (folded[i] ?? !(isLast && loading))
          const shown = isFolded ? m.content.slice(0, FOLD_CHARS) + '…' : m.content
          const prevDay = i > 0 ? recentMsgs[i - 1].day : undefined
          return (
            <div key={i}>
              {/* 跨天分隔线，一眼看出哪些是今天说的 */}
              {m.day && m.day !== prevDay && (
                <div style={{ textAlign: 'center', margin: '6px 0 10px' }}>
                  <span style={{ fontSize: 11, color: '#9aa0a6', background: '#eef0f3',
                    padding: '2px 10px', borderRadius: 10 }}>
                    {m.day === todayStr ? '今天' : m.day}
                  </span>
                </div>
              )}
            <div style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: 8, marginBottom: 12 }}>
              <Avatar size={30} style={{ flex: 'none', background: isUser ? '#1677ff' : '#fff', color: isUser ? '#fff' : undefined, fontSize: isUser ? 13 : 16 }}>
                {isUser ? '博' : '🐮'}
              </Avatar>
              <div style={{ maxWidth: '76%', display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  padding: '7px 11px', borderRadius: 10, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  background: isUser ? '#1677ff' : '#fff', color: isUser ? '#fff' : '#000', border: isUser ? 'none' : '1px solid #eee',
                }}>{shown || (m.role === 'assistant' && loading ? '…' : '')}</div>
                {longMsg && (
                  <Button type="link" size="small" style={{ padding: 0, height: 20, fontSize: 11 }}
                    onClick={() => setFolded(f => ({ ...f, [i]: !isFolded }))}>
                    {isFolded ? `展开全文（${m.content.length} 字）` : '收起'}
                  </Button>
                )}
                {m.report && (
                  <div onClick={() => setPreview(m.report!)} title="点击预览汇报"
                    style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', background: '#fff', border: '1px solid #e5e8ef', borderRadius: 8, padding: '8px 10px', minWidth: 180 }}>
                    <FileTextOutlined style={{ fontSize: 22, color: '#1677ff' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>工作汇报.html</div>
                      <div style={{ fontSize: 11, color: '#9aa0a6' }}>点击预览 · 网页版</div>
                    </div>
                  </div>
                )}
                {m.intake && (
                  <div style={{
                    marginTop: 6, background: '#fff', border: '1px solid #e5e8ef',
                    borderRadius: 8, padding: '8px 10px', minWidth: 200,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <FileTextOutlined style={{ fontSize: 20, color: '#34a853' }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {m.intake.filename}
                        </div>
                        {m.intake.doc_type && (
                          <Tag color="green" style={{ marginTop: 3, marginInlineEnd: 0, fontSize: 10, lineHeight: '16px', padding: '0 5px' }}>
                            {m.intake.doc_type}
                          </Tag>
                        )}
                      </div>
                    </div>
                    {m.intake.project_number && (
                      <div style={{ fontSize: 11, color: '#5f6368', marginTop: 5 }}>
                        归入项目：<b>{m.intake.project_number}</b>
                      </div>
                    )}
                    {!m.intake.project_number && (
                      <div style={{ fontSize: 11, color: '#f9ab00', marginTop: 5 }}>
                        没认出项目编号，已放进分类库
                      </div>
                    )}
                    {m.intake.summary && (
                      <div style={{ fontSize: 11, color: '#9aa0a6', marginTop: 4, lineHeight: 1.5 }}>
                        {m.intake.summary}
                      </div>
                    )}
                  </div>
                )}
                <div style={{ fontSize: 10, color: '#bbb', marginTop: 3 }}>
                  {m.ts}{isUser && (m.read ? ' · 已读' : ' · 送达')}
                </div>
              </div>
            </div>
            </div>
          )
        })}
        {loading && <div style={{ color: '#999', fontSize: 13 }}><Spin size="small" /> {tool || '牛马思考中…'}</div>}
        {uploading && <div style={{ color: '#999', fontSize: 13 }}><Spin size="small" /> 正在识别归档…</div>}
      </div>

      {pending.length > 0 && (
        <div style={{ padding: '8px 10px', borderTop: '1px solid #f0f0f0', background: '#fffbe6' }}>
          <div style={{ fontSize: 12, color: '#ad6800', marginBottom: 6 }}>⚠️ 待你确认的写操作（点确认才真正执行）</div>
          {pending.map((a) => (
            <div key={a.id} style={{ background: '#fff', border: '1px solid #ffe58f', borderRadius: 8, padding: '8px 10px', marginBottom: 6 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{a.label}</div>
              <div style={{ fontSize: 11, color: '#9aa0a6', margin: '2px 0 6px' }}>{a.detail}</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button size="small" type="primary" onClick={() => confirmAct(a.id, a.label)}>确认执行</Button>
                <Button size="small" onClick={() => cancelAct(a.id)}>取消</Button>
              </div>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, padding: 10, borderTop: '1px solid #f0f0f0', alignItems: 'flex-end' }}>
        {/* 回形针：不方便拖的时候点它选文件，和拖拽走同一条路 */}
        <input
          ref={fileRef} type="file" multiple hidden
          onChange={(e) => {
            if (e.target.files?.length) takeFiles(e.target.files)
            e.target.value = ''      // 允许连续传同一个文件
          }}
        />
        <Button icon={<PaperClipOutlined />} onClick={() => fileRef.current?.click()}
          loading={uploading} title="发文件给牛马（识别后自动归档）" />
        <Input.TextArea value={input} onChange={(e) => setInput(e.target.value)}
          onPaste={(e) => {
            // Ctrl+V 直接粘图：截图/复制的图片走和拖拽同一条路（识别→归档）。
            // 剪贴板里的图片没有文件名，按时间生成一个，否则后端拿到空名字。
            const items = Array.from(e.clipboardData?.items || [])
            const imgs = items.filter(i => i.type.startsWith('image/'))
            if (!imgs.length) return
            e.preventDefault()
            const files: File[] = []
            imgs.forEach((it, idx) => {
              const f = it.getAsFile()
              if (!f) return
              const ext = (f.type.split('/')[1] || 'png').replace('jpeg', 'jpg')
              const name = f.name && f.name !== 'image.png'
                ? f.name
                : `粘贴图片_${new Date().toLocaleString('zh-CN', { hour12: false })
                    .replace(/[/\s:]/g, '')}${imgs.length > 1 ? `_${idx + 1}` : ''}.${ext}`
              files.push(new File([f], name, { type: f.type }))
            })
            if (files.length) takeFiles(files)
          }}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="跟牛马说…（Enter 发送，可拖文件进来）" autoSize={{ minRows: 1, maxRows: 4 }} disabled={loading} />
        <Button type="primary" icon={<SendOutlined />} onClick={send} loading={loading} />
      </div>

      <Modal open={!!preview} onCancel={() => setPreview('')} footer={null} width="80%"
        style={{ top: 24 }} styles={{ body: { padding: 0, height: '82vh' } }} title="工作汇报">
        {preview && <iframe src={preview} title="report" style={{ width: '100%', height: '82vh', border: 0 }} />}
      </Modal>

      {/* 历史消息记录：按天倒序，最近的在上面 */}
      <Modal
        open={historyOpen}
        onCancel={() => setHistoryOpen(false)}
        title={`历史消息记录（${olderMsgs.length} 条，保留 ${KEEP_DAYS} 天）`}
        width={700}
        footer={[
          <Button key="clear" danger onClick={() => {
            const keep = msgs.filter(m => !m.day || m.day >= recentCutoff)
            setMsgs(keep); saveLog(keep); setHistoryOpen(false)
          }}>清空历史</Button>,
          <Button key="c" onClick={() => setHistoryOpen(false)}>关闭</Button>,
        ]}
      >
        <div style={{ maxHeight: '62vh', overflowY: 'auto' }}>
          {Array.from(new Set(olderMsgs.map(m => m.day))).sort().reverse().map(d => (
            <div key={d} style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, color: '#1677ff', marginBottom: 6,
                position: 'sticky', top: 0, background: '#fff', padding: '2px 0' }}>{d}</div>
              {olderMsgs.filter(m => m.day === d).map((m, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, fontSize: 12.5 }}>
                  <span style={{ flex: 'none', color: '#9aa0a6', width: 46 }}>{m.ts}</span>
                  <span style={{ flex: 'none', fontWeight: 600, width: 36 }}>
                    {m.role === 'user' ? '我' : '牛马'}
                  </span>
                  <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', flex: 1 }}>
                    {m.content}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  )
}
