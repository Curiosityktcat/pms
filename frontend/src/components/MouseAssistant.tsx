/**
 * 「耗子」AI 助手：固定在页面右侧的常驻面板（不再是可拖动图标），随时提问。
 * 可折叠成右侧细条以让出空间；接本地 Qwen（/api/ai-assistant），逐页带场景上下文。
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { Input, Button, Avatar, Spin, Typography, App, Modal, Descriptions, Upload, List, Tag, Popconfirm } from 'antd'
import { SendOutlined, RobotOutlined, RightOutlined, WalletOutlined, UploadOutlined, DeleteOutlined } from '@ant-design/icons'
import {
  askAssistant, getAiAccount, aiRecharge, listKnowledge, uploadKnowledge, deleteKnowledge,
  type AiAccount, type KbFile,
} from '../services/aiAssistant'

const { Text } = Typography
type Msg = { role: 'user' | 'assistant'; content: string }
const OPEN_KEY = 'mouseAsst.open'
const WIDTH = 340

const PAGE_NAMES: Record<string, string> = {
  '': '公告首页', projects: '项目管理', project: '项目详情', bid: '开标看板',
  'bid-board': '开标看板', 'bid-review': '评标', inquiry: '询议价', contract: '合同',
  announcement: '公告', 'procurement-demand': '采购需求', 'procurement-doc': '采购文件',
  'procurement-result': '采购结果', people: '人员', supervision: '投诉质疑库',
  law: '法规库', archive: '归档', distributions: '采购项目分发',
  'auth-letter': '授权函', template: '模板', 'llm-usage': '大模型用量',
}
function pageName(pathname: string): string {
  const seg = pathname.split('/').filter(Boolean)[0] ?? ''
  return PAGE_NAMES[seg] ?? (seg || '首页')
}

export default function MouseAssistant() {
  const { message } = App.useApp()
  const location = useLocation()
  const [open, setOpen] = useState(() => localStorage.getItem(OPEN_KEY) !== '0')
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const [acctOpen, setAcctOpen] = useState(false)
  const [acct, setAcct] = useState<AiAccount | null>(null)
  const [kb, setKb] = useState<{ files: KbFile[]; chars: number; can_manage: boolean }>({ files: [], chars: 0, can_manage: false })
  const [kbUploading, setKbUploading] = useState(false)

  const openAccount = async () => {
    setAcctOpen(true)
    try { const r = await getAiAccount(); setAcct(r.data.data) } catch { /* ignore */ }
    try { const k = await listKnowledge(); setKb(k.data.data) } catch { /* ignore */ }
  }
  const doRecharge = async () => {
    try { const r = await aiRecharge(); message.info(r.data.error || '已提交') } catch { message.error('充值入口未开通') }
  }
  const doKbUpload = async (file: File) => {
    setKbUploading(true)
    try {
      await uploadKnowledge(file); message.success('已上传，耗子已学习这份资料')
      const k = await listKnowledge(); setKb(k.data.data)
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '上传失败')
    } finally { setKbUploading(false) }
  }
  const doKbDelete = async (name: string) => {
    try { await deleteKnowledge(name); const k = await listKnowledge(); setKb(k.data.data) } catch { message.error('删除失败') }
  }

  useEffect(() => { localStorage.setItem(OPEN_KEY, open ? '1' : '0') }, [open])
  useEffect(() => {
    if (open && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [msgs, loading, open])

  const send = useCallback(async () => {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    setMsgs((m) => [...m, { role: 'user', content: q }])
    setLoading(true)
    try {
      const ans = await askAssistant(q, pageName(location.pathname))
      setMsgs((m) => [...m, { role: 'assistant', content: ans }])
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } }; message?: string }
      const txt = err?.response?.data?.error || err?.message || '调用失败'
      setMsgs((m) => [...m, { role: 'assistant', content: `（出错了）${txt}` }])
      message.error('耗子暂时答不上来：' + txt)
    } finally {
      setLoading(false)
    }
  }, [input, loading, location.pathname, message])

  if (location.pathname === '/login') return null

  // 折叠态：右侧细条
  if (!open) {
    return (
      <div onClick={() => setOpen(true)} title="展开耗子助手"
        style={{
          position: 'fixed', right: 0, top: '40%', zIndex: 1100, cursor: 'pointer',
          background: '#1677ff', color: '#fff', padding: '14px 7px', borderRadius: '8px 0 0 8px',
          writingMode: 'vertical-rl', fontWeight: 600, letterSpacing: 3, boxShadow: '-2px 0 8px rgba(0,0,0,.15)',
        }}>
        🐭 耗子助手
      </div>
    )
  }

  return (
    <div style={{
      position: 'fixed', right: 0, top: 64, bottom: 0, width: WIDTH, zIndex: 1100,
      background: '#fff', borderLeft: '1px solid #eee', boxShadow: '-2px 0 12px rgba(0,0,0,.08)',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* 头部 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px',
        borderBottom: '1px solid #f0f0f0', background: '#f0f5ff',
      }}>
        <Avatar style={{ background: '#fff', fontSize: 18 }}>🐭</Avatar>
        <div style={{ flex: 1 }}>
          <a onClick={openAccount} style={{ cursor: 'pointer' }} title="余额 / 充值 / 知识库">
            <Text strong style={{ color: 'inherit' }}>耗子ai（hxb蒸馏版）</Text>
            <WalletOutlined style={{ fontSize: 12, color: '#999', marginLeft: 5 }} />
          </a>
          <div><Text type="secondary" style={{ fontSize: 12 }}>{pageName(location.pathname)}</Text></div>
        </div>
        <Button type="text" size="small" icon={<RightOutlined />} onClick={() => setOpen(false)} title="收起" />
      </div>

      {/* 消息区 */}
      <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: 12, background: '#fafafa' }}>
        {msgs.length === 0 && (
          <div style={{ textAlign: 'center', color: '#999', marginTop: 40 }}>
            <RobotOutlined style={{ fontSize: 30 }} />
            <div style={{ marginTop: 10, fontSize: 13 }}>
              我是耗子ai（hxb蒸馏版），采购的事尽管问～<br />
              懂本单位内控细则，比如<br />「15万的项目走什么采购方式？」「最近的项目进展」
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
            <div style={{
              maxWidth: '85%', padding: '7px 11px', borderRadius: 10, fontSize: 13, lineHeight: 1.6,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              background: m.role === 'user' ? '#1677ff' : '#fff',
              color: m.role === 'user' ? '#fff' : '#000',
              border: m.role === 'user' ? 'none' : '1px solid #eee',
            }}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && <div style={{ color: '#999', fontSize: 13 }}><Spin size="small" /> 耗子思考中…</div>}
      </div>

      {/* 输入区 */}
      <div style={{ display: 'flex', gap: 6, padding: 10, borderTop: '1px solid #f0f0f0' }}>
        <Input.TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="问点什么…（Enter 发送）"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={loading}
        />
        <Button type="primary" icon={<SendOutlined />} onClick={send} loading={loading} />
      </div>

      {/* 账户：余额 / 充值 / 知识库 */}
      <Modal title="耗子ai 账户" open={acctOpen} onCancel={() => setAcctOpen(false)} footer={null} width={460}>
        {acct && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="账号">{acct.display_name || '—'}</Descriptions.Item>
            <Descriptions.Item label="余额">
              {acct.unlimited
                ? <Tag color="gold">无限额度（不计费）</Tag>
                : <b style={{ color: acct.balance > 0 ? '#389e0d' : '#cf1322' }}>￥{acct.balance.toFixed(4)}</b>}
            </Descriptions.Item>
            {!acct.unlimited && <Descriptions.Item label="累计消费">￥{acct.spent.toFixed(4)}</Descriptions.Item>}
            <Descriptions.Item label="计费标准">{acct.price_per_million} 元 / 百万 token</Descriptions.Item>
          </Descriptions>
        )}
        {acct && !acct.unlimited && (
          <Button type="primary" icon={<WalletOutlined />} style={{ marginTop: 12 }} onClick={doRecharge}>充值</Button>
        )}
        {acct && acct.recent.length > 0 && (
          <>
            <div style={{ margin: '12px 0 6px', fontWeight: 600 }}>近期用量</div>
            <List size="small" dataSource={acct.recent}
              renderItem={(u) => (
                <List.Item>
                  <Text style={{ fontSize: 12 }}>{u.feature} · {u.tokens} tokens · ￥{u.cost.toFixed(4)}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>{u.at?.slice(5, 16)}</Text>
                </List.Item>
              )} />
          </>
        )}
        <div style={{ margin: '14px 0 6px', fontWeight: 600 }}>知识库（内控文件 / 采购经验）</div>
        <Text type="secondary" style={{ fontSize: 12 }}>已学习 {kb.chars} 字，耗子回答会依据这些资料。</Text>
        <List size="small" dataSource={kb.files} locale={{ emptyText: '暂无资料' }}
          renderItem={(f) => (
            <List.Item actions={kb.can_manage ? [
              <Popconfirm key="d" title="删除该资料？" onConfirm={() => doKbDelete(f.name)}>
                <Button size="small" type="link" danger icon={<DeleteOutlined />} />
              </Popconfirm>,
            ] : []}>
              <Text style={{ fontSize: 12 }}>{f.name}</Text>
            </List.Item>
          )} />
        {kb.can_manage && (
          <Upload showUploadList={false} accept=".docx,.txt,.md"
            beforeUpload={(f) => { doKbUpload(f as File); return false }}>
            <Button icon={<UploadOutlined />} loading={kbUploading} style={{ marginTop: 8 }}>
              上传内控文件 / 经验（docx/txt）
            </Button>
          </Upload>
        )}
      </Modal>
    </div>
  )
}
