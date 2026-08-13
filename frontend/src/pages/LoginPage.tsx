import { useState, useEffect } from 'react'
import { Form, Input, Button, App, Typography, Spin, Tag, Empty } from 'antd'
import {
  UserOutlined, LockOutlined, BankOutlined, TeamOutlined,
  ShopOutlined, StarOutlined, ClockCircleOutlined, CheckSquareOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { authLogin, authMe } from '../services/auth'
import { getPublicAnnouncements } from '../services/announcement'
import type { Announcement } from '../services/announcement'
import { useAuth } from '../hooks/useAuth'

const { Text } = Typography

// ── 角色定义 ─────────────────────────────────────────────────────
const ROLES = [
  { key: 'officer',  label: '采购人登录',   icon: <BankOutlined />,   color: '#1677ff', bg: '#e6f4ff' },
  { key: 'agency',   label: '代理机构登录', icon: <TeamOutlined />,   color: '#52c41a', bg: '#f6ffed' },
  { key: 'supplier', label: '供应商登录',   icon: <ShopOutlined />,   color: '#fa8c16', bg: '#fff7e6' },
  { key: 'expert',   label: '评审专家登录', icon: <StarOutlined />,   color: '#722ed1', bg: '#f9f0ff' },
]

// ── 公告类型定义 ──────────────────────────────────────────────────
const ANN_TYPES = [
  { key: 'procurement',   label: '采购公告' },
  { key: 'survey',        label: '调研及意向公开公告' },
  { key: 'correction',    label: '更正公告' },
  { key: 'single_source', label: '单一来源公示' },
]

// ── 解析开标时间/判断是否已过 ─────────────────────────────────────
function parseDeadline(s: string): Date | null {
  if (!s) return null
  // 兼容全角冒号 '：' 和半角冒号 ':'
  const m = s.match(/(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})[：:](\d{2})/)
  if (m) {
    return new Date(parseInt(m[1]), parseInt(m[2]) - 1, parseInt(m[3]), parseInt(m[4]), parseInt(m[5]))
  }
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}

function getCountdown(deadline: string): { text: string; expired: boolean; color: string } {
  const d = parseDeadline(deadline)
  if (!d) return { text: '开标时间待定', expired: false, color: '#aaa' }
  const diff = d.getTime() - Date.now()
  if (diff <= 0) return { text: '已开标', expired: true, color: '#aaa' }
  const days = Math.floor(diff / 86400000)
  const hours = Math.floor((diff % 86400000) / 3600000)
  if (days > 0) return { text: `还剩 ${days} 天 ${hours} 小时`, expired: false, color: '#52c41a' }
  if (hours > 0) return { text: `还剩 ${hours} 小时`, expired: false, color: '#fa8c16' }
  return { text: `还剩 ${Math.floor((diff % 3600000) / 60000)} 分钟`, expired: false, color: '#ff4d4f' }
}

export default function LoginPage() {
  const [activeRole, setActiveRole] = useState('officer')
  const [activeAnnType, setActiveAnnType] = useState('procurement')
  const [publicAnns, setPublicAnns] = useState<Announcement[]>([])
  const [annLoading, setAnnLoading] = useState(false)
  const [loginLoading, setLoginLoading] = useState(false)
  // 检测是否已登录（从系统内通过"首页"按钮跳转过来的情况）
  const [alreadyLoggedIn, setAlreadyLoggedIn] = useState(false)
  const [loggedInName, setLoggedInName] = useState('')
  const { setUser } = useAuth()
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [form] = Form.useForm()

  // 因长时间未操作被自动登出时，提示用户
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('expired') === '1') {
      message.warning('因长时间未操作，您已自动退出，请重新登录')
    }
  }, [message])

  // 检测当前登录状态
  useEffect(() => {
    authMe()
      .then(res => {
        setAlreadyLoggedIn(true)
        setLoggedInName(res.data.user?.display_name || '')
      })
      .catch(() => {
        setAlreadyLoggedIn(false)
      })
  }, [])

  // 加载公开公告
  useEffect(() => {
    setAnnLoading(true)
    setPublicAnns([])
    getPublicAnnouncements(activeAnnType)
      .then(res => setPublicAnns(res.data.data || []))
      .catch(() => setPublicAnns([]))
      .finally(() => setAnnLoading(false))
  }, [activeAnnType])

  const onFinish = async (values: { username: string; password: string }) => {
    // 先过滑块验证，拿到一次性通行令牌再提交登录（防撞库）
    const cg = (window as any).CGCaptcha
    const captchaToken: string = await new Promise(resolve => {
      if (!cg) { resolve(''); return }   // widget 未加载则不阻断，由后端拦截
      cg.open({ action: 'pms_login', title: '安全验证', onPass: (t: string) => resolve(t) })
    })
    setLoginLoading(true)
    try {
      const res = await authLogin(values.username, values.password, captchaToken)
      setUser(res.data.user)
      navigate('/portal')
    } catch (err: any) {
      message.error(err.response?.data?.error || '登录失败，请检查用户名或密码')
    } finally {
      setLoginLoading(false)
    }
  }

  const activeRoleInfo = ROLES.find(r => r.key === activeRole) || ROLES[0]

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#f0f4f8' }}>

      {/* ════════════════ 顶部横幅 ════════════════ */}
      <div style={{
        background: 'linear-gradient(135deg, #0d2c5e 0%, #1a4a8a 60%, #1677ff 100%)',
        padding: '0 40px',
        height: 64,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: '0 2px 12px rgba(0,0,0,.3)',
        flexShrink: 0,
      }}>
        {/* 左侧：Logo + 标题 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 38, height: 38, borderRadius: '50%',
            background: 'rgba(255,255,255,.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20, border: '1.5px solid rgba(255,255,255,.35)',
          }}>🏥</div>
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 18, lineHeight: 1.2, letterSpacing: 1 }}>
              自行采购管理信息系统
            </div>
            <div style={{ color: 'rgba(255,255,255,.65)', fontSize: 12, marginTop: 1 }}>
              Self-managed Procurement System
            </div>
          </div>
        </div>

        {/* 右侧：公告类型快速导航 */}
        <div style={{ display: 'flex', gap: 4 }}>
          {ANN_TYPES.map(t => (
            <button
              key={t.key}
              onClick={() => {
                setActiveAnnType(t.key)
                document.getElementById('ann-panel')?.scrollIntoView({ behavior: 'smooth' })
              }}
              style={{
                background: activeAnnType === t.key ? 'rgba(255,255,255,.25)' : 'transparent',
                border: '1px solid rgba(255,255,255,.3)',
                color: '#fff',
                padding: '5px 12px',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 13,
                transition: 'all .2s',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ════════════════ 主体内容 ════════════════ */}
      <div style={{
        flex: 1,
        display: 'flex',
        gap: 24,
        padding: '32px 48px',
        maxWidth: 1280,
        margin: '0 auto',
        width: '100%',
        boxSizing: 'border-box',
      }}>

        {/* ── 左侧：登录区域 ──────────────────────────────────── */}
        <div style={{ width: 380, flexShrink: 0 }}>
          <div style={{
            background: '#fff',
            borderRadius: 12,
            boxShadow: '0 4px 24px rgba(0,0,0,.1)',
            overflow: 'hidden',
          }}>
            {/* 登录卡片顶部装饰 */}
            <div style={{
              background: alreadyLoggedIn
                ? 'linear-gradient(135deg, #52c41a22 0%, #52c41a11 100%)'
                : `linear-gradient(135deg, ${activeRoleInfo.color}22 0%, ${activeRoleInfo.color}11 100%)`,
              borderBottom: `3px solid ${alreadyLoggedIn ? '#52c41a' : activeRoleInfo.color}`,
              padding: '20px 24px 16px',
            }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#1a2035', margin: 0 }}>
                {alreadyLoggedIn ? '✅ 您已登录' : '请选择登录身份'}
              </div>
              <Text type="secondary" style={{ fontSize: 13 }}>
                {alreadyLoggedIn
                  ? `当前账号：${loggedInName}，可直接返回工作台`
                  : '选择您的身份后输入账号密码'}
              </Text>
            </div>

            <div style={{ padding: '20px 24px 28px' }}>
              {alreadyLoggedIn ? (
                /* ── 已登录：显示返回工作台按钮 ── */
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{
                    background: '#f6ffed',
                    border: '1px solid #b7eb8f',
                    borderRadius: 8,
                    padding: '16px',
                    textAlign: 'center',
                    color: '#52c41a',
                    fontSize: 13,
                  }}>
                    🎉 您好，<strong>{loggedInName}</strong>！<br />
                    <span style={{ color: '#666', fontSize: 12 }}>
                      当前正在浏览公告首页，您可以随时返回工作台
                    </span>
                  </div>
                  <Button
                    type="primary"
                    block
                    size="large"
                    icon={<ArrowRightOutlined />}
                    style={{ height: 44, borderRadius: 8, fontSize: 15, fontWeight: 600 }}
                    onClick={() => navigate('/portal')}
                  >
                    返回工作台
                  </Button>
                </div>
              ) : (
                /* ── 未登录：正常显示登录表单 ── */
                <>
                  {/* 角色选择 */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 10,
                    marginBottom: 24,
                  }}>
                    {ROLES.map(role => (
                      <button
                        key={role.key}
                        onClick={() => setActiveRole(role.key)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '10px 14px',
                          borderRadius: 8,
                          border: `1.5px solid ${activeRole === role.key ? role.color : '#e8e8e8'}`,
                          background: activeRole === role.key ? role.bg : '#fafafa',
                          color: activeRole === role.key ? role.color : '#555',
                          cursor: 'pointer',
                          fontWeight: activeRole === role.key ? 600 : 400,
                          fontSize: 13,
                          transition: 'all .2s',
                          boxShadow: activeRole === role.key ? `0 2px 8px ${role.color}33` : 'none',
                        }}
                      >
                        <span style={{ fontSize: 16 }}>{role.icon}</span>
                        <span style={{ lineHeight: 1.3 }}>{role.label}</span>
                      </button>
                    ))}
                  </div>

                  {/* 提示信息 */}
                  <div style={{
                    background: `${activeRoleInfo.color}11`,
                    border: `1px solid ${activeRoleInfo.color}33`,
                    borderRadius: 6,
                    padding: '8px 12px',
                    marginBottom: 20,
                    fontSize: 12,
                    color: '#555',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}>
                    <span style={{ color: activeRoleInfo.color, fontSize: 14 }}>{activeRoleInfo.icon}</span>
                    {activeRole === 'officer' && '采购人账号由系统管理员创建，如有问题请联系信息科。'}
                    {activeRole === 'agency' && '代理机构账号由系统管理员分配，登录后可编制采购公告。'}
                    {activeRole === 'supplier' && '供应商登录功能即将上线，敬请期待。'}
                    {activeRole === 'expert' && '评审专家登录功能即将上线，敬请期待。'}
                  </div>

                  {/* 登录表单 */}
                  <Form form={form} onFinish={onFinish} size="large" autoComplete="off">
                    <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                      <Input
                        prefix={<UserOutlined style={{ color: '#bbb' }} />}
                        placeholder="用户名"
                        autoFocus
                        style={{ borderRadius: 8 }}
                      />
                    </Form.Item>
                    <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                      <Input.Password
                        prefix={<LockOutlined style={{ color: '#bbb' }} />}
                        placeholder="密码"
                        style={{ borderRadius: 8 }}
                      />
                    </Form.Item>
                    <Form.Item style={{ marginBottom: 0 }}>
                      <Button
                        type="primary"
                        htmlType="submit"
                        block
                        loading={loginLoading}
                        style={{
                          height: 44,
                          borderRadius: 8,
                          fontSize: 16,
                          fontWeight: 600,
                          background: activeRoleInfo.color,
                          borderColor: activeRoleInfo.color,
                        }}
                      >
                        登 录
                      </Button>
                    </Form.Item>
                  </Form>
                </>
              )}
            </div>
          </div>

          {/* 系统说明卡片 */}
          <div style={{
            background: '#fff',
            borderRadius: 10,
            boxShadow: '0 2px 12px rgba(0,0,0,.06)',
            padding: '16px 20px',
            marginTop: 16,
          }}>
            <div style={{ fontSize: 13, color: '#666', lineHeight: 2 }}>
              <div style={{ fontWeight: 600, color: '#333', marginBottom: 4 }}>📋 系统功能</div>
              <div>• 采购需求审签与立项管理</div>
              <div>• 采购项目全流程跟踪</div>
              <div>• 采购公告编制与挂网发布</div>
              <div>• 开标评审与结果管理</div>
              <div>• 合同管理与归档</div>
            </div>
          </div>
        </div>

        {/* ── 右侧：公告展示区域 ──────────────────────────────── */}
        <div style={{ flex: 1, minWidth: 0 }} id="ann-panel">
          <div style={{
            background: '#fff',
            borderRadius: 12,
            boxShadow: '0 4px 24px rgba(0,0,0,.1)',
            overflow: 'hidden',
            minHeight: 500,
          }}>
            {/* 公告类型标签 */}
            <div style={{
              display: 'flex',
              borderBottom: '1px solid #f0f0f0',
              background: '#fafafa',
            }}>
              {ANN_TYPES.map(t => (
                <button
                  key={t.key}
                  onClick={() => setActiveAnnType(t.key)}
                  style={{
                    padding: '14px 20px',
                    border: 'none',
                    borderBottom: `3px solid ${activeAnnType === t.key ? '#1677ff' : 'transparent'}`,
                    background: 'transparent',
                    color: activeAnnType === t.key ? '#1677ff' : '#666',
                    fontWeight: activeAnnType === t.key ? 600 : 400,
                    fontSize: 14,
                    cursor: 'pointer',
                    transition: 'all .2s',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* 公告列表 */}
            <div style={{ padding: '0 0 8px' }}>
              {annLoading ? (
                <div style={{ textAlign: 'center', padding: 60 }}>
                  <Spin tip="加载中..." />
                </div>
              ) : publicAnns.length === 0 ? (
                <div style={{ padding: '40px 0' }}>
                  <Empty
                    description={
                      activeAnnType === 'procurement'
                        ? '暂无挂网公告'
                        : '该栏目功能即将上线，敬请期待'
                    }
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                  />
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {/* 表头 */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: '1.3fr 2.4fr 1fr 1.3fr 1.8fr 1.3fr',
                    gap: 6,
                    padding: '9px 16px',
                    background: '#f5f7fa',
                    fontSize: 12,
                    color: '#888',
                    fontWeight: 600,
                    borderBottom: '1px solid #e8e8e8',
                  }}>
                    <span>项目编号</span>
                    <span>项目名称</span>
                    <span>代理机构</span>
                    <span>发布时间</span>
                    <span>开标时间</span>
                    <span>状态</span>
                  </div>

                  {publicAnns.map((ann, idx) => {
                    const { text, expired, color } = getCountdown(ann.response_deadline)
                    // 格式化发布时间 "2026-05-27T21:55:53" → "2026-05-27"
                    const pubDate = ann.confirmed_at ? ann.confirmed_at.split('T')[0] : '—'
                    return (
                      <div
                        key={ann.id}
                        onClick={() => navigate(`/public/announcement/${ann.id}`)}
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '1.3fr 2.4fr 1fr 1.3fr 1.8fr 1.3fr',
                          gap: 6,
                          padding: '11px 16px',
                          borderBottom: idx < publicAnns.length - 1 ? '1px solid #f0f0f0' : 'none',
                          alignItems: 'center',
                          cursor: 'pointer',
                          transition: 'background .15s',
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = '#f0f7ff')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                      >
                        {/* 项目编号 */}
                        <div style={{ fontSize: 12, color: '#1677ff', fontFamily: 'monospace', fontWeight: 500 }}>
                          {ann.project_number || '—'}
                        </div>

                        {/* 项目名称 */}
                        <div>
                          <div style={{
                            fontSize: 13, color: '#1a2035', fontWeight: 500,
                            lineHeight: 1.4, textDecoration: 'underline',
                            textDecorationColor: 'transparent',
                            transition: 'text-decoration-color .15s',
                          }}
                            onMouseEnter={e => ((e.currentTarget as HTMLElement).style.textDecorationColor = '#1677ff')}
                            onMouseLeave={e => ((e.currentTarget as HTMLElement).style.textDecorationColor = 'transparent')}
                          >
                            {ann.project_name || '未命名项目'}
                          </div>
                          {ann.round_number > 1 && (
                            <Tag color="orange" style={{ marginTop: 2, fontSize: 10, lineHeight: '16px' }}>
                              第{'一二三四五'[ann.round_number - 1]}次
                            </Tag>
                          )}
                        </div>

                        {/* 代理机构 */}
                        <div style={{ fontSize: 12, color: '#666' }}>
                          {ann.agency_name || '—'}
                        </div>

                        {/* 发布时间 */}
                        <div style={{ fontSize: 12, color: '#888' }}>
                          {pubDate}
                        </div>

                        {/* 开标时间 */}
                        <div style={{ fontSize: 12, color: '#555' }}>
                          {ann.response_deadline || '—'}
                        </div>

                        {/* 状态 */}
                        <div>
                          {expired ? (
                            <Tag icon={<CheckSquareOutlined />} color="default" style={{ fontSize: 11 }}>
                              已开标
                            </Tag>
                          ) : (
                            <Tag
                              icon={<ClockCircleOutlined />}
                              style={{ fontSize: 11, color, borderColor: color, background: `${color}11` }}
                            >
                              {text}
                            </Tag>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ════════════════ 底部页脚 ════════════════ */}
      <div style={{
        background: '#1a2035',
        color: 'rgba(255,255,255,.5)',
        textAlign: 'center',
        padding: '14px 40px',
        fontSize: 12,
        flexShrink: 0,
      }}>
        <span>© 2026 自行采购管理信息系统</span>
        <span style={{ margin: '0 16px', opacity: .4 }}>|</span>
        <span>仅供内部使用</span>
        <span style={{ margin: '0 16px', opacity: .4 }}>|</span>
        <span>如有问题请联系系统管理员</span>
      </div>
    </div>
  )
}
