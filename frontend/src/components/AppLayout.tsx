import { useState } from 'react'
import { Layout, Menu, Dropdown, Space, Button, Tooltip, Grid, Drawer } from 'antd'
import { HomeOutlined, BookOutlined, MenuOutlined } from '@ant-design/icons'
import {
  FolderOpenOutlined,
  EditOutlined,
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
  ControlOutlined,
  FileDoneOutlined,
  FormOutlined,
  PlusCircleOutlined,
  UnorderedListOutlined,
  ScheduleOutlined,
  SolutionOutlined,
  BarsOutlined,
  FileSearchOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import { authLogout } from '../services/auth'
import AiGuideButton from './AiGuideButton'
import InboxBell from './InboxBell'
import ChatWidget from './ChatWidget'
import OnlineCount from './OnlineCount'
import NiumaAssistant from './NiumaAssistant'

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
  const { mode: themeMode, setMode: setThemeMode } = useTheme()
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
      return 'dispatch-list'  // 无 type → 总览页，高亮「2.1 项目分发」
    }
    if (pathParts[0] === 'internal-bid-demand') return 'internal-bid-demand'
    if (pathParts[0] === 'procurement-doc') {
      return pathParts[1] === 'demand' ? 'doc-demand' : 'doc-file'
    }
    if (pathParts[0] === 'doc-form') {
      const t = pathParts[1]
      if (t === 'procurement_doc') return 'doc-file-online'
      if (t === 'internal_demand') return 'doc-internal-online'
      return 'doc-demand-online'
    }
    return pathParts[0] || 'flow'
  })()

  // 根据路径确定默认展开的父菜单
  const getDefaultOpenKeys = () => {
    const k = activeKey
    if (['project-distribution'].includes(k)) return ['dispatch']
    if (['inquiry-review', 'project-review'].includes(k)) return ['review']
    if (['new', 'flow', 'bid', 'bid-board', 'auth-letter'].includes(k)) return ['pm']
    if (['announcement', 'correction'].includes(k)) return ['publish']
    if (['people-manage', 'template-manage', 'agency-manage'].includes(k)) return ['base-data']
    if (k.startsWith('procurement-demand-') || k === 'doc-demand-online' || k === 'doc-internal-online') return ['procurement-req']
    if (k === 'internal-bid-demand') return ['internal-procurement']
    if (['doc-demand', 'doc-file', 'doc-file-online'].includes(k)) return ['doc']
    return []   // 门户/文档工具等非业务页：不自动展开任何分组
  }

  // 响应式：md 以下视为手机/窄屏，侧栏改为抽屉
  const screens = Grid.useBreakpoint()
  const isMobile = !screens.md
  const [drawerOpen, setDrawerOpen] = useState(false)
  // 菜单手风琴：同一时间只展开一个分组，减少视觉杂乱
  const [openKeys, setOpenKeys] = useState<string[]>(getDefaultOpenKeys())

  const menuItems = [
    // ─── 1. 采购需求编制 ────────────────────────────────────────
    {
      key: 'procurement-req',
      label: '1. 采购需求编制',
      icon: <FormOutlined />,
      children: [
        {
          key: 'procurement-plan',
          label: '1.0 采购计划池',
          onClick: () => navigate('/procurement-plan'),
        },
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
        {
          key: 'doc-demand-online',
          icon: <EditOutlined />,
          label: '1.6 需求在线编制',
          onClick: () => navigate('/doc-form/procurement_demand'),
        },
        {
          key: 'doc-internal-online',
          icon: <EditOutlined />,
          label: '1.7 院内需求在线编制',
          onClick: () => navigate('/doc-form/internal_demand'),
        },
      ],
    },

    // ─── 2. 采购项目分发 ──────────────────────────────────────
    {
      key: 'dispatch',
      label: '2. 采购项目分发',
      icon: <AuditOutlined />,
      children: [
        {
          key: 'project-distribution',
          icon: <AuditOutlined />,
          label: '2.1 项目分发',
          // 新版：采购部助理分发项目 + 指定经办人 + 自动派代理（来源 rd-web/手动）
          onClick: () => navigate('/project-distribution'),
        },
        // 2.2 四川采购公告 / 2.3 采购需求分发 暂不开放——按需可恢复
      ],
    },

    // ─── 3. 代理协议 ──────────────────────────────────────────
    {
      key: 'agency-agreement',
      label: '3. 代理协议',
      icon: <SafetyCertificateOutlined />,
      onClick: () => navigate('/agency-agreement'),
    },

    // ─── 4. 采购部项目管理 ──────────────────────────────────────
    {
      key: 'pm',
      label: '4. 采购部项目管理',
      icon: <FolderOpenOutlined />,
      children: [
        {
          key: 'project-pool',
          icon: <ContainerOutlined />,
          label: '4.0 项目池',
          // 经办人本人的池子：只放本人账号抓的（view=pool），区别于 2.1 助理分发视图
          onClick: () => navigate('/project-distribution?view=pool'),
        },
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
      label: '5. 采购文件编制',
      icon: <FileTextOutlined />,
      children: [
        {
          key: 'doc-demand',
          icon: <AuditOutlined />,
          label: '5.1 采购需求确认',
          onClick: () => navigate('/procurement-doc/demand'),
        },
        {
          key: 'doc-file',
          icon: <FileTextOutlined />,
          label: '5.2 采购文件确认',
          onClick: () => navigate('/procurement-doc/file'),
        },
        {
          key: 'doc-file-online',
          icon: <EditOutlined />,
          label: '5.3 文件在线编制',
          onClick: () => navigate('/doc-form/procurement_doc'),
        },
      ],
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
        {
          key: 'survey',
          label: '6.2 调研公告',
          onClick: () => navigate('/survey'),
        },
        {
          key: 'correction',
          icon: <FileSearchOutlined />,
          label: '6.3 更正公告',
          onClick: () => navigate('/correction'),
        },
        {
          key: 'single-source',
          label: '6.4 单一来源公示',
          onClick: () => navigate('/single-source'),
        },
      ],
    },

    // ─── 7. 询/议价函 ─────────────────────────────────────────
    {
      key: 'inquiry',
      label: '7. 询/议价函、紧急采购',
      icon: <ContainerOutlined />,
      onClick: () => navigate('/inquiry'),
    },

    // ─── 8. 项目评审 ──────────────────────────────────────────
    {
      key: 'review',
      label: '8. 项目评审',
      icon: <BarChartOutlined />,
      children: [
        {
          key: 'inquiry-review',
          icon: <ContainerOutlined />,
          label: '8.1 询议价、紧急采购评审',
          onClick: () => navigate('/inquiry-review'),
        },
        { key: 'supplier-reg', label: <DevLabel label="8.2 供应商报名" />, disabled: true },
        { key: 'eval-report',  label: <DevLabel label="8.3 评定表报告" />, disabled: true },
        { key: 'online-review',label: <DevLabel label="8.4 在线评审" />,  disabled: true },
        {
          key: 'project-review',
          icon: <ContainerOutlined />,
          label: '8.5 项目评审资料上传',
          onClick: () => navigate('/project-review'),
        },
      ],
    },

    // ─── 投标文件审查（AI 辅助，独立于 8 的占位） ─────────────
    {
      key: 'bid-review',
      label: '投标文件审查',
      icon: <FileSearchOutlined />,
      onClick: () => navigate('/bid-review'),
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
      label: '11. 归档',
      icon: <FileDoneOutlined />,
      onClick: () => navigate('/archive'),
    },

    // ─── 12. 代理机构考核 ─────────────────────────────────────
    // 独立顶层项，不能塞进「2. 采购项目分发」组——那个组是权限受控的，
    // 经办人没有分发权限时整组隐藏，考核会跟着一起消失（踩过一次）。
    // 分发页面里另有入口按钮，从那边也能进。
    {
      key: 'agency-assessment',
      icon: <SafetyCertificateOutlined />,
      label: '12. 代理机构考核',
      onClick: () => navigate('/agency-assessment'),
    },

    // ─── 文件识别（工具集合，不参与采购流程编号）──────────────
    {
      key: 'file-ocr',
      label: '文件识别',
      icon: <FileSearchOutlined />,
      onClick: () => navigate('/file-ocr'),
    },

    // ─── 私人文件库（仅黄新博本人可见可用）────────────────────
    ...(user?.username === '黄新博' ? [{
      key: 'filebox',
      label: '我的文件库',
      icon: <FolderOpenOutlined />,
      onClick: () => navigate('/filebox'),
    }] : []),

    // ─── 政采数据流水线看板（仅黄新博本人可见）──────────────
    ...(user?.username === '黄新博' ? [{
      key: 'datapipe',
      label: '数据流水线看板',
      icon: <BarChartOutlined />,
      onClick: () => navigate('/datapipe'),
    }] : []),

    // ─── 政采数据检索（四川政采卫健：公告/产品/设备参数）────────
    {
      key: "ccgp-data",
      label: "政采数据检索",
      icon: <BookOutlined />,
      children: [
        {
          key: "ccgp-match",
          label: "参数匹配产品",
          onClick: () => window.open("https://rag.curiosityktcat.cn/ccgp/match", "_blank"),
        },
        {
          key: "ccgp-products",
          label: "产品/设备检索",
          onClick: () => window.open("https://rag.curiosityktcat.cn/ccgp/products", "_blank"),
        },
        {
          key: "ccgp-notices",
          label: "公告检索",
          onClick: () => window.open("https://rag.curiosityktcat.cn/ccgp", "_blank"),
        },
      ],
    },

    // ─── 13. 基础数据维护 ─────────────────────────────────────
    {
      key: 'base-data',
      label: '13. 基础数据维护',
      icon: <SettingOutlined />,
      children: [
        {
          key: 'people-manage',
          icon: <TeamOutlined />,
          label: '13.1 人员维护',
          onClick: () => navigate('/people-manage'),
        },
        {
          key: 'template-manage',
          icon: <FileTextOutlined />,
          label: '13.2 模板维护',
          onClick: () => navigate('/template-manage'),
        },
        {
          key: 'agency-manage',
          icon: <SafetyCertificateOutlined />,
          label: '13.3 代理机构维护',
          onClick: () => navigate('/agency-manage'),
        },
      ],
    },

    // ─── 法规库 ───────────────────────────────────────────────
    {
      key: 'law-library',
      label: '法规库',
      icon: <BookOutlined />,
      onClick: () => navigate('/law-library'),
    },

    // ─── 投诉质疑数据库 ───────────────────────────────────────
    {
      key: 'supervision',
      label: '投诉质疑数据库',
      icon: <AuditOutlined />,
      onClick: () => navigate('/supervision'),
    },
  ]

  // ── 按当前用户权限过滤菜单 ───────────────────────────────────
  // 受控菜单 key（与后端 PERMISSION_CATALOG 一致）；其余为"开发中"占位项，始终保留。
  const CONTROLLED_KEYS = new Set([
    'procurement-demand-gov', 'internal-bid-demand', 'procurement-demand-sole',
    'procurement-demand-inquiry', 'procurement-demand-emergency', 'dispatch',
    'agency-agreement', 'doc',
    'new', 'flow', 'bid', 'bid-board', 'auth-letter', 'announcement',
    'inquiry', 'inquiry-review', 'project-review', 'procurement-result', 'contract', 'archive', 'file-ocr', 'bid-review',
    'people-manage', 'template-manage',
  ])
  const permSet = new Set(user?.perms || [])
  // 投标文件审核：仅限「黄新博」本人可见，其余账号即便有权限也隐藏
  const BID_REVIEW_USERS = ['黄新博']
  // 项目池是黄新博本人用自己的 rd-web 账号抓来的医院内部资料：
  // 经办人里只有他本人可见，另加采购部助理/负责人/管理员；其余经办人及代理机构不可见。
  const POOL_USERS = ['黄新博', 'agent-hxb']   // 黄新博本人 + 他的 AI 经办人账号
  const POOL_MANAGE_ROLES = ['assistant', 'pd_assistant', 'leader', 'admin']
  const canSeePool = !!user && (POOL_USERS.includes(user.username) || POOL_MANAGE_ROLES.includes(user.role))
  // 系统级配置（权限/大模型/邮件）已迁至独立的后台管理系统
  const leafVisible = (key: string) => {
    if (key === 'bid-review') return !!user && BID_REVIEW_USERS.includes(user.username)
    if (key === 'project-pool') return canSeePool
    return !CONTROLLED_KEYS.has(key) || permSet.has(key)
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filteredMenuItems = (menuItems as any[])
    .map((item) => {
      if (!item.children) {
        // 顶层叶子：受控且无权限则隐藏；占位/非受控保留
        return leafVisible(item.key) ? item : null
      }
      // 父级本身受控（如 5. 采购文件编制 doc 组）：无该权限则整组隐藏
      if (CONTROLLED_KEYS.has(item.key) && !permSet.has(item.key)) return null
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const children = item.children.filter((c: any) => leafVisible(c.key))
      // 过滤后若组内已无任何可用（非禁用）项，则隐藏整组
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const hasEnabled = children.some((c: any) => !c.disabled)
      if (!hasEnabled) return null
      return { ...item, children }
    })
    .filter(Boolean)

  // ── 工作区拆分：采购流程（1~11）与 工具集合 两套侧栏 ────────────
  // 顶层工具项 key；其余顶层项都属于采购流程
  const TOOL_TOP_KEYS = new Set([
    'bid-review', 'file-ocr', 'filebox', 'base-data', 'law-library', 'supervision',
  ])
  // 判断当前页面属于哪个工作区（含工具分组的子项）
  const TOOL_ACTIVE_KEYS = new Set([
    ...TOOL_TOP_KEYS, 'people-manage', 'template-manage', 'agency-manage',
  ])
  const workspace: 'flow' | 'tools' | 'all' =
    activeKey === 'portal' || activeKey === 'chpwd'
      ? 'all'
      : TOOL_ACTIVE_KEYS.has(activeKey) ? 'tools' : 'flow'

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const flowItems = (filteredMenuItems as any[]).filter(i => !TOOL_TOP_KEYS.has(i.key))
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const toolItems = (filteredMenuItems as any[]).filter(i => TOOL_TOP_KEYS.has(i.key))
  const workspaceItems =
    workspace === 'flow'
      ? [{ type: 'group' as const, key: 'g-flow', label: '采购流程', children: flowItems }]
      : workspace === 'tools'
        ? [{ type: 'group' as const, key: 'g-tools', label: '工具集合', children: toolItems }]
        : [
            { type: 'group' as const, key: 'g-flow', label: '采购流程', children: flowItems },
            { type: 'group' as const, key: 'g-tools', label: '工具集合', children: toolItems },
          ]

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

  // 菜单手风琴展开逻辑：仅保留最新点开的分组
  const rootGroupKeys = (filteredMenuItems as Array<{ key: string; children?: unknown }>)
    .filter((i) => i.children).map((i) => i.key)
  const onOpenChange = (keys: string[]) => {
    const latest = keys.find((k) => !openKeys.includes(k))
    if (latest && rootGroupKeys.includes(latest)) setOpenKeys([latest])
    else setOpenKeys(keys)
  }

  // 侧栏内容（桌面 Sider 与移动 Drawer 共用）
  const navInner = (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 侧边栏标题 */}
      <div style={{
        padding: '16px 16px 12px',
        borderBottom: '1px solid var(--pms-border)',
        background: 'var(--pms-surface)',
      }}>
        <div
          onClick={() => navigate('/portal')}
          title="回到功能分流页"
          style={{
            color: '#202124',
            fontWeight: 600,
            fontSize: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            cursor: 'pointer',
          }}
        >
          <span style={{
            background: '#1a73e8',
            borderRadius: 8,
            width: 30, height: 30,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 800, letterSpacing: -0.5, color: '#fff',
            flexShrink: 0,
          }}>PMS</span>
          <span style={{ lineHeight: 1.3 }}>自行采购管理 PMS<br />
            <span style={{ fontSize: 11, fontWeight: 400, color: '#5f6368' }}>
              信息系统
            </span>
          </span>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', paddingTop: 6 }}>
        <Menu
          theme="light"
          mode="inline"
          selectedKeys={[activeKey]}
          openKeys={openKeys}
          onOpenChange={onOpenChange}
          onClick={() => { if (isMobile) setDrawerOpen(false) }}
          items={workspaceItems}
          style={{ borderRight: 0, background: 'transparent' }}
        />
      </div>

      {/* 底部署名 */}
      <div style={{
        flexShrink: 0,
        padding: '10px 16px',
        borderTop: '1px solid var(--pms-border)',
        background: 'var(--pms-surface)',
        color: '#9aa0a6',
        fontSize: 11,
        textAlign: 'center',
        letterSpacing: 0.3,
      }}>
        Made By Huangxb &amp; CC
      </div>
    </div>
  )

  // 分流页全屏展示，不带侧边栏；选择功能点进去后，侧栏按工作区自动出现
  const isPortal = activeKey === 'portal'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {!isMobile && !isPortal && (
        <Sider
          width={230}
          theme="light"
          style={{
            height: '100vh',
            position: 'sticky',
            top: 0,
            left: 0,
            background: 'var(--pms-surface)',
            borderRight: '1px solid var(--pms-border)',
          }}
        >
          {navInner}
        </Sider>
      )}
      {isMobile && !isPortal && (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={260}
          styles={{ body: { padding: 0 }, header: { display: 'none' } }}
        >
          {navInner}
        </Drawer>
      )}

      <Layout>
        {/* 顶部导航栏 */}
        <Header style={{
          background: 'var(--pms-surface)',
          padding: isMobile ? '0 12px' : '0 24px',
          display: 'flex',
          alignItems: 'center',
          gap: isMobile ? 4 : 0,
          borderBottom: '1px solid var(--pms-border)',
          boxShadow: '0 1px 2px 0 rgba(60,64,67,.05)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}>
          {/* 移动端：汉堡按钮打开抽屉菜单（分流页无侧栏，不显示） */}
          {isMobile && !isPortal && (
            <Button
              icon={<MenuOutlined />}
              type="text"
              onClick={() => setDrawerOpen(true)}
              style={{ fontSize: 18, color: '#5f6368' }}
            />
          )}
          {/* 公告首页入口 */}
          <Tooltip title="查看公开采购公告（无需退出登录）">
            <Button
              icon={<HomeOutlined />}
              type="text"
              onClick={() => navigate('/login')}
              style={{ color: '#666', fontSize: 13 }}
            >
              {!isMobile && '公告首页'}
            </Button>
          </Tooltip>
          <div style={{ flex: 1 }} />
          {/* 主题切换：浅色 ⇄ 暖色护眼 */}
          <Tooltip title={themeMode === 'sepia' ? '切换到浅色' : '切换到暖色护眼'}>
            <Button
              type="text"
              onClick={() => setThemeMode(themeMode === 'sepia' ? 'light' : 'sepia')}
              style={{ fontSize: 16, color: '#5f6368', marginRight: isMobile ? 0 : 4 }}
            >
              {themeMode === 'sepia' ? '☀️' : '🌿'}
            </Button>
          </Tooltip>
          {/* 在线人数 — 所有登录用户可见 */}
          <OnlineCount />
          {/* 聊天 + 待办 — 所有登录用户可见 */}
          <ChatWidget />
          <InboxBell />
          {/* AI 使用说明 — 所有用户可见 */}
          <AiGuideButton isAdmin={!!user?.is_admin} />
          {/* 后台管理入口 — 仅系统管理员可见 */}
          {user?.is_admin && (
            <Tooltip title="进入后台管理系统（权限 / 大模型 / 邮件配置）">
              <Button
                icon={<ControlOutlined />}
                type="text"
                onClick={() => navigate('/admin')}
                style={{ color: '#13c2c2', fontSize: 13, marginRight: 8 }}
              >
                {!isMobile && '后台管理'}
              </Button>
            </Tooltip>
          )}
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
                background: '#1a73e8',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <UserOutlined style={{ color: '#fff', fontSize: 14 }} />
              </div>
              {!isMobile && (
                <div style={{ lineHeight: 1.3 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: '#333' }}>
                    {user?.display_name}
                  </div>
                  <div style={{ fontSize: 11, color: '#888' }}>{user?.role_cn}</div>
                </div>
              )}
            </Space>
          </Dropdown>
        </Header>

        <Content style={{
          margin: isMobile ? 12 : 24,
          background: 'transparent',
          minHeight: 'calc(100vh - 64px - 48px)',
        }}>
          <Outlet />
        </Content>
      </Layout>
      {user?.username === '黄新博' && <NiumaAssistant />}
    </Layout>
  )
}
