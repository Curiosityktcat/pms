import { Layout, Menu, Dropdown, Space, Button, Tooltip } from 'antd'
import { HomeOutlined } from '@ant-design/icons'
import {
  FolderOpenOutlined,
  UserOutlined,
  LogoutOutlined,
  KeyOutlined,
  CalendarOutlined,
  AuditOutlined,
  FileTextOutlined,
  GlobalOutlined,
  BarChartOutlined,
  ContainerOutlined,
  TeamOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  SafetyOutlined,
  FileDoneOutlined,
  FormOutlined,
  PlusCircleOutlined,
  UnorderedListOutlined,
  ScheduleOutlined,
  SolutionOutlined,
  BarsOutlined,
  MailOutlined,
  ApiOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { authLogout } from '../services/auth'

const { Sider, Header, Content } = Layout

// 开发中菜单项标签样式
const DevLabel = ({ label }: { label: string }) => (
  <span style={{ color: '#666' }}>
    {label}
    <span style={{ fontSize: 10, marginLeft: 4, color: '#bbb' }}>开发中</span>
  </span>
)

export default function AppLayout() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const handleLogout = async () => {
    await authLogout()
    setUser(null)
    navigate('/login')
  }

  // 当前激活菜单项（处理 procurement-demand/:type 子路由）
  const pathParts = location.pathname.split('/').filter(Boolean)
  const activeKey = (() => {
    if (pathParts[0] === 'procurement-demand') {
      const t = pathParts[1]
      if (t === 'gov')          return 'procurement-demand-gov'
      if (t === 'competition')  return 'procurement-demand-competition'
      if (t === 'sole_source')  return 'procurement-demand-sole'
      if (t === 'inquiry')      return 'procurement-demand-inquiry'
      if (t === 'emergency')    return 'procurement-demand-emergency'
      return 'dispatch'  // 无 type → 总览页，高亮「采购项目分发」
    }
    if (pathParts[0] === 'internal-bid-demand') return 'internal-bid-demand'
    return pathParts[0] || 'flow'
  })()

  // 根据路径确定默认展开的父菜单
  const getDefaultOpenKeys = () => {
    const k = activeKey
    if (['new', 'flow', 'bid', 'bid-board', 'auth-letter'].includes(k)) return ['pm']
    if (['announcement'].includes(k)) return ['publish']
    if (['people-manage', 'email-settings', 'scraper-settings', 'permission-manage'].includes(k)) return ['base-data']
    if (k.startsWith('procurement-demand-')) return ['procurement-req']
    if (k === 'internal-bid-demand') return ['internal-procurement']
    return ['pm']
  }

  const menuItems = [
    // ─── 1. 采购需求编制 ────────────────────────────────────────
    {
      key: 'procurement-req',
      label: '1. 采购需求编制',
      icon: <FormOutlined />,
      children: [
        {
          key: 'procurement-demand-gov',
          label: '1.1 政府采购需求',
          onClick: () => navigate('/procurement-demand/gov'),
        },
        {
          key: 'internal-bid-demand',
          label: '1.2 院内竞选需求编制',
          onClick: () => navigate('/internal-bid-demand'),
        },
        {
          key: 'procurement-demand-sole',
          label: '1.3 单一来源需求',
          onClick: () => navigate('/procurement-demand/sole_source'),
        },
        {
          key: 'procurement-demand-inquiry',
          label: '1.4 询议价需求',
          onClick: () => navigate('/procurement-demand/inquiry'),
        },
        {
          key: 'procurement-demand-emergency',
          label: '1.5 紧急采购登记',
          onClick: () => navigate('/procurement-demand/emergency'),
        },
      ],
    },

    // ─── 2. 采购项目分发 ──────────────────────────────────────
    {
      key: 'dispatch',
      label: '2. 采购项目分发',
      icon: <AuditOutlined />,
      // 复用采购需求页面，助理在「待分发」tab 进行分发
      onClick: () => navigate('/procurement-demand'),
    },

    // ─── 3. 代理协议 ──────────────────────────────────────────
    {
      key: 'agency-agreement',
      label: <DevLabel label="3. 代理协议" />,
      icon: <SafetyCertificateOutlined />,
      disabled: true,
    },

    // ─── 4. 采购部项目管理 ──────────────────────────────────────
    {
      key: 'pm',
      label: '4. 采购部项目管理',
      icon: <FolderOpenOutlined />,
      children: [
        {
          key: 'new',
          icon: <PlusCircleOutlined />,
          label: '4.1 项目立项',
          onClick: () => navigate('/new'),
        },
        {
          key: 'flow',
          icon: <UnorderedListOutlined />,
          label: '4.2 项目流程',
          onClick: () => navigate('/flow'),
        },
        {
          key: 'bid',
          icon: <ScheduleOutlined />,
          label: '开标管理',
          onClick: () => navigate('/bid'),
        },
        {
          key: 'bid-board',
          icon: <BarChartOutlined />,
          label: '开标看板',
          onClick: () => navigate('/bid-board'),
        },
        {
          key: 'auth-letter',
          icon: <FileDoneOutlined />,
          label: '授权函',
          onClick: () => navigate('/auth-letter'),
        },
      ],
    },

    // ─── 5. 采购文件编制 ──────────────────────────────────────
    {
      key: 'doc',
      label: <DevLabel label="5. 采购文件编制" />,
      icon: <FileTextOutlined />,
      disabled: true,
    },

    // ─── 6. 挂网管理 ──────────────────────────────────────────
    {
      key: 'publish',
      label: '6. 挂网管理',
      icon: <GlobalOutlined />,
      children: [
        {
          key: 'announcement',
          icon: <CalendarOutlined />,
          label: '6.1 采购公告',
          onClick: () => navigate('/announcement'),
        },
        { key: 'survey',        label: <DevLabel label="6.2 调研公告" />,       disabled: true },
        { key: 'correction',    label: <DevLabel label="6.3 更正公告" />,       disabled: true },
        { key: 'single-source', label: <DevLabel label="6.4 单一来源公示" />,   disabled: true },
      ],
    },

    // ─── 7. 询/议价函 ─────────────────────────────────────────
    {
      key: 'inquiry',
      label: '7. 询/议价函',
      icon: <ContainerOutlined />,
      onClick: () => navigate('/inquiry'),
    },

    // ─── 8. 项目评审 ──────────────────────────────────────────
    {
      key: 'review',
      label: <DevLabel label="8. 项目评审" />,
      icon: <BarChartOutlined />,
      disabled: true,
      children: [
        { key: 'supplier-reg', label: <DevLabel label="8.1 供应商报名" />, disabled: true },
        { key: 'eval-report',  label: <DevLabel label="8.2 评定表报告" />, disabled: true },
        { key: 'online-review',label: <DevLabel label="8.3 在线评审" />,  disabled: true },
      ],
    },

    // ─── 9. 采购结果确认 ──────────────────────────────────────
    {
      key: 'procurement-result',
      label: '9. 采购结果确认',
      icon: <BarsOutlined />,
      onClick: () => navigate('/procurement-result'),
    },

    // ─── 10. 合同管理 ─────────────────────────────────────────
    {
      key: 'contract',
      label: '10. 合同管理',
      icon: <SolutionOutlined />,
      onClick: () => navigate('/contract'),
    },

    // ─── 11. 归档 ─────────────────────────────────────────────
    {
      key: 'archive',
      label: <DevLabel label="11. 归档" />,
      icon: <FileDoneOutlined />,
      disabled: true,
    },

    // ─── 12. 基础数据维护 ─────────────────────────────────────
    {
      key: 'base-data',
      label: '12. 基础数据维护',
      icon: <SettingOutlined />,
      children: [
        {
          key: 'people-manage',
          icon: <TeamOutlined />,
          label: '12.1 人员维护',
          onClick: () => navigate('/people-manage'),
        },
        { key: 'template-manage', label: <DevLabel label="12.2 模板维护" />, disabled: true },
        {
          key: 'email-settings',
          icon: <MailOutlined />,
          label: '12.3 邮件设置',
          onClick: () => navigate('/email-settings'),
        },
        {
          key: 'scraper-settings',
          icon: <ApiOutlined />,
          label: '12.4 抓取模型设置',
          onClick: () => navigate('/scraper-settings'),
        },
        ...(user?.is_admin
          ? [{
              key: 'permission-manage',
              icon: <SafetyOutlined />,
              label: '12.5 权限管理',
              onClick: () => navigate('/permission-manage'),
            }]
          : []
        ),
      ],
    },
  ]

  // ── 按当前用户权限过滤菜单 ───────────────────────────────────
  // 受控菜单 key（与后端 PERMISSION_CATALOG 一致）；其余为"开发中"占位项，始终保留。
  const CONTROLLED_KEYS = new Set([
    'procurement-demand-gov', 'internal-bid-demand', 'procurement-demand-sole',
    'procurement-demand-inquiry', 'procurement-demand-emergency', 'dispatch',
    'new', 'flow', 'bid', 'bid-board', 'auth-letter', 'announcement',
    'inquiry', 'procurement-result', 'contract',
    'people-manage', 'email-settings', 'scraper-settings',
  ])
  const permSet = new Set(user?.perms || [])
  // permission-manage 仅 admin 可见，不入受控集合（由 is_admin 控制）
  const leafVisible = (key: string) =>
    !CONTROLLED_KEYS.has(key) || permSet.has(key)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filteredMenuItems = (menuItems as any[])
    .map((item) => {
      if (!item.children) {
        // 顶层叶子：受控且无权限则隐藏；占位/非受控保留
        return leafVisible(item.key) ? item : null
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const children = item.children.filter((c: any) => leafVisible(c.key))
      // 过滤后若组内已无任何可用（非禁用）项，则隐藏整组
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const hasEnabled = children.some((c: any) => !c.disabled)
      if (!hasEnabled) return null
      return { ...item, children }
    })
    .filter(Boolean)

  const userMenu = {
    items: [
      {
        key: 'chpwd',
        label: '修改密码',
        icon: <KeyOutlined />,
        onClick: () => navigate('/chpwd'),
      },
      {
        key: 'logout',
        label: '退出登录',
        icon: <LogoutOutlined />,
        danger: true,
        onClick: handleLogout,
      },
    ],
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={230}
        theme="dark"
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'sticky',
          top: 0,
          left: 0,
        }}
      >
        {/* 侧边栏标题 */}
        <div style={{
          padding: '14px 16px 12px',
          borderBottom: '1px solid rgba(255,255,255,.1)',
          background: 'rgba(0,0,0,.2)',
        }}>
          <div style={{
            color: '#fff',
            fontWeight: 700,
            fontSize: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <span style={{
              background: '#1677ff',
              borderRadius: 6,
              width: 28, height: 28,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16, flexShrink: 0,
            }}>🏥</span>
            <span style={{ lineHeight: 1.3 }}>自行采购管理<br />
              <span style={{ fontSize: 11, fontWeight: 400, color: 'rgba(255,255,255,.55)' }}>
                信息系统
              </span>
            </span>
          </div>
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[activeKey]}
          defaultOpenKeys={getDefaultOpenKeys()}
          items={filteredMenuItems}
          style={{ borderRight: 0, marginTop: 4 }}
        />
      </Sider>

      <Layout>
        {/* 顶部导航栏 */}
        <Header style={{
          background: '#fff',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          borderBottom: '1px solid #f0f0f0',
          boxShadow: '0 1px 4px rgba(0,0,0,.06)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}>
          {/* 公告首页入口 */}
          <Tooltip title="查看公开采购公告（无需退出登录）">
            <Button
              icon={<HomeOutlined />}
              type="text"
              onClick={() => navigate('/login')}
              style={{ color: '#666', fontSize: 13 }}
            >
              公告首页
            </Button>
          </Tooltip>
          <div style={{ flex: 1 }} />
          <Dropdown menu={userMenu} placement="bottomRight">
            <Space
              style={{
                cursor: 'pointer',
                color: '#555',
                padding: '4px 8px',
                borderRadius: 6,
                transition: 'background .2s',
              }}
              onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = '#f5f5f5')}
              onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'transparent')}
            >
              <div style={{
                width: 30, height: 30, borderRadius: '50%',
                background: '#1677ff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <UserOutlined style={{ color: '#fff', fontSize: 14 }} />
              </div>
              <div style={{ lineHeight: 1.3 }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: '#333' }}>
                  {user?.display_name}
                </div>
                <div style={{ fontSize: 11, color: '#888' }}>{user?.role_cn}</div>
              </div>
            </Space>
          </Dropdown>
        </Header>

        <Content style={{
          margin: 24,
          background: '#f5f6fa',
          minHeight: 'calc(100vh - 64px - 48px)',
        }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
