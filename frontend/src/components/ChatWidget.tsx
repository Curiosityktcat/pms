/**
 * 顶栏「聊天」入口：微信图标 + 未读徽标，点开抽屉（左联系人 / 右会话）。
 * 一对一聊天，支持文本 / 图片 / 文件（≤20MB），已读未读，轮询刷新（无 websocket）。
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Badge, Button, Drawer, App, Input, Avatar, Tooltip, Upload, Image, Spin, Empty,
  Typography,
} from 'antd'
import {
  WechatOutlined, SendOutlined, PictureOutlined, PaperClipOutlined,
  UserOutlined, FileOutlined, DownloadOutlined, TeamOutlined,
} from '@ant-design/icons'
import {
  getChatSummary, listContacts, getConversation, sendText, sendFileMessage,
  chatFileUrl, type ChatContact, type ChatMessage,
} from '../services/chat'
import { useAuth } from '../hooks/useAuth'

const { Text } = Typography

const SUMMARY_POLL = 20000
const CONV_POLL = 5000

function fmtSize(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
function fmtTime(s: string) {
  if (!s) return ''
  const d = new Date(s.replace(' ', 'T'))
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  return sameDay ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`
}

export default function ChatWidget() {
  const { message } = App.useApp()
  const { user } = useAuth()
  const me = user?.username || ''
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [contacts, setContacts] = useState<ChatContact[]>([])
  const [peer, setPeer] = useState<ChatContact | null>(null)
  const [msgs, setMsgs] = useState<ChatMessage[]>([])
  const [text, setText] = useState('')
  const [loadingConv, setLoadingConv] = useState(false)
  const [sending, setSending] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const loadSummary = useCallback(async () => {
    try { setUnread((await getChatSummary()).data.data.unread) } catch { /* 静默 */ }
  }, [])

  useEffect(() => {
    loadSummary()
    const t = setInterval(loadSummary, SUMMARY_POLL)
    return () => clearInterval(t)
  }, [loadSummary])

  const loadContacts = useCallback(async () => {
    try { setContacts((await listContacts()).data.data) } catch { /* 静默 */ }
  }, [])

  const loadConversation = useCallback(async (p: ChatContact, silent = false) => {
    if (!silent) setLoadingConv(true)
    try {
      const res = await getConversation(p.username)
      setMsgs(res.data.data)
    } catch { if (!silent) message.error('加载会话失败') }
    finally { if (!silent) setLoadingConv(false) }
  }, [message])

  // 打开抽屉：拉联系人
  useEffect(() => { if (open) loadContacts() }, [open, loadContacts])

  // 选中会话：拉消息 + 轮询；并刷新角标/联系人未读
  useEffect(() => {
    if (!open || !peer) return
    loadConversation(peer)
    const t = setInterval(() => {
      loadConversation(peer, true)
      loadSummary(); loadContacts()
    }, CONV_POLL)
    return () => clearInterval(t)
  }, [open, peer, loadConversation, loadSummary, loadContacts])

  // 读了会话后刷新角标与联系人未读
  useEffect(() => { if (peer) { loadSummary(); loadContacts() } }, [msgs.length]) // eslint-disable-line

  // 滚到底
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [msgs, peer])

  const doSendText = async () => {
    const t = text.trim()
    if (!t || !peer) return
    setSending(true)
    try {
      await sendText(peer.username, t)
      setText('')
      await loadConversation(peer, true)
      loadContacts()
    } catch (e: any) {
      message.error(e.response?.data?.error || '发送失败')
    } finally { setSending(false) }
  }

  const doSendFile = async (file: File) => {
    if (!peer) return false
    if (file.size > 20 * 1024 * 1024) { message.error('文件超过 20MB 限制'); return false }
    setSending(true)
    try {
      await sendFileMessage(peer.username, file)
      await loadConversation(peer, true)
      loadContacts()
    } catch (e: any) {
      message.error(e.response?.data?.error || '发送失败')
    } finally { setSending(false) }
    return false
  }

  return (
    <>
      <Tooltip title="聊天">
        <Badge count={unread} size="small" offset={[-2, 2]}>
          <Button
            type="text"
            icon={<WechatOutlined style={{ fontSize: 19 }} />}
            onClick={() => setOpen(true)}
            style={{ color: '#07c160', marginRight: 4 }}
          />
        </Badge>
      </Tooltip>

      <Drawer
        title="聊天"
        placement="right"
        width={760}
        open={open}
        onClose={() => setOpen(false)}
        styles={{ body: { padding: 0 } }}
      >
        <div style={{ display: 'flex', height: '100%' }}>
          {/* 左：联系人 */}
          <div style={{ width: 220, borderRight: '1px solid #f0f0f0', overflowY: 'auto', flexShrink: 0 }}>
            {contacts.length === 0 && (
              <div style={{ padding: 24 }}><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无联系人" /></div>
            )}
            {contacts.map(c => (
              <div
                key={c.username}
                onClick={() => setPeer(c)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                  cursor: 'pointer',
                  background: peer?.username === c.username ? '#e6f4ff' : 'transparent',
                  borderBottom: '1px solid #fafafa',
                }}
              >
                <Badge count={c.unread} size="small">
                  <Avatar size={36} style={{ background: c.role === 'agency' ? '#fa8c16' : '#1677ff' }}
                    icon={c.role === 'agency' ? <TeamOutlined /> : <UserOutlined />} />
                </Badge>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Text strong ellipsis style={{ maxWidth: 110, fontSize: 13 }}>{c.display_name}</Text>
                    <Text type="secondary" style={{ fontSize: 10 }}>{fmtTime(c.last_time)}</Text>
                  </div>
                  <Text type="secondary" ellipsis style={{ fontSize: 12, display: 'block', maxWidth: 150 }}>
                    {c.last_text || ' '}
                  </Text>
                </div>
              </div>
            ))}
          </div>

          {/* 右：会话 */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            {!peer ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择联系人开始聊天" />
              </div>
            ) : (
              <>
                <div style={{ padding: '10px 16px', borderBottom: '1px solid #f0f0f0', fontWeight: 600 }}>
                  {peer.display_name}
                  {peer.role === 'agency' && <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>代理机构</Text>}
                </div>

                <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: 16, background: '#f5f5f5' }}>
                  {loadingConv ? (
                    <div style={{ textAlign: 'center', paddingTop: 40 }}><Spin /></div>
                  ) : msgs.length === 0 ? (
                    <div style={{ textAlign: 'center', color: '#bbb', paddingTop: 40 }}>暂无消息，发送第一条吧</div>
                  ) : (
                    msgs.map(m => <Bubble key={m.id} m={m} mine={m.sender === me} />)
                  )}
                </div>

                <div style={{ borderTop: '1px solid #f0f0f0', padding: 10 }}>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                    <Upload showUploadList={false} accept="image/*" beforeUpload={doSendFile}>
                      <Tooltip title="发送图片"><Button size="small" type="text" icon={<PictureOutlined />} /></Tooltip>
                    </Upload>
                    <Upload showUploadList={false}
                      accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip,.rar,.7z"
                      beforeUpload={doSendFile}>
                      <Tooltip title="发送文件（≤20MB）"><Button size="small" type="text" icon={<PaperClipOutlined />} /></Tooltip>
                    </Upload>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <Input.TextArea
                      value={text}
                      onChange={e => setText(e.target.value)}
                      onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); doSendText() } }}
                      onPaste={e => {
                        // Ctrl+V 直接发图：截图粘进来即发送，走和「发图片」按钮同一条路。
                        // 剪贴板图片没有文件名，按时间补一个，否则后端存成空名字。
                        const imgs = Array.from(e.clipboardData?.items || [])
                          .filter(i => i.type.startsWith('image/'))
                        if (!imgs.length) return
                        e.preventDefault()
                        imgs.forEach((it, idx) => {
                          const f = it.getAsFile()
                          if (!f) return
                          const ext = (f.type.split('/')[1] || 'png').replace('jpeg', 'jpg')
                          const name = f.name && f.name !== 'image.png'
                            ? f.name
                            : `粘贴图片_${new Date().toLocaleString('zh-CN', { hour12: false })
                                .replace(/[/\s:]/g, '')}${imgs.length > 1 ? `_${idx + 1}` : ''}.${ext}`
                          doSendFile(new File([f], name, { type: f.type }))
                        })
                      }}
                      placeholder="输入消息，Enter 发送，Shift+Enter 换行，可直接 Ctrl+V 粘贴图片"
                      autoSize={{ minRows: 1, maxRows: 4 }}
                    />
                    <Button type="primary" icon={<SendOutlined />} loading={sending}
                      onClick={doSendText} disabled={!text.trim()}>发送</Button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </Drawer>
    </>
  )
}

function Bubble({ m, mine }: { m: ChatMessage; mine: boolean }) {
  const bg = mine ? '#95ec69' : '#fff'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: mine ? 'flex-end' : 'flex-start', marginBottom: 14 }}>
      <Text type="secondary" style={{ fontSize: 10, marginBottom: 2 }}>
        {mine ? '我' : m.sender_name} · {fmtTime(m.created_at)}
      </Text>
      <div style={{ maxWidth: '78%' }}>
        {m.msg_type === 'image' ? (
          <Image src={chatFileUrl(m.id)} style={{ maxWidth: 220, maxHeight: 220, borderRadius: 8 }} />
        ) : m.msg_type === 'file' ? (
          <a href={chatFileUrl(m.id, true)} target="_blank" rel="noreferrer"
            style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#fff', padding: '10px 12px', borderRadius: 8, border: '1px solid #eee', minWidth: 180 }}>
            <FileOutlined style={{ fontSize: 26, color: '#1677ff' }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, wordBreak: 'break-all' }}>{m.file_name}</div>
              <Text type="secondary" style={{ fontSize: 11 }}>{fmtSize(m.file_size)}</Text>
            </div>
            <DownloadOutlined style={{ color: '#999' }} />
          </a>
        ) : (
          <div style={{ background: bg, padding: '8px 12px', borderRadius: 8, fontSize: 14, whiteSpace: 'pre-wrap', wordBreak: 'break-word', display: 'inline-block', textAlign: 'left' }}>
            {m.text}
          </div>
        )}
      </div>
      {mine && (
        <Text style={{ fontSize: 10, marginTop: 2, color: m.is_read ? '#52c41a' : '#bbb' }}>
          {m.is_read ? '已读' : '未读'}
        </Text>
      )}
    </div>
  )
}
