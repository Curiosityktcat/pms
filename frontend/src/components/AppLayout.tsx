import { Layout, Menu, Dropdown, Space, Typography } from 'antd'
import {
  FolderOpenOutlined,
  AuditOutlined,
  UserOutlined,
  LogoutOutlined,
  KeyOutlined,
  CalendarOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { authLogout } from '../services/auth'

const { Sider, Header, Content } = Layout
const { Text } = Typography

export default function AppLayout() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const handleLogout = async () => {
    await authLogout()
    setUser(null)
    navigate('/login')
  }

  // 当前激活的菜单项
  const activeKey = location.pathname.split('/')[1] || 'flow'
  // 展开含当前页的父菜单
  const defaultOpenKeys = activeKey === 'announcement' ? ['pm', 'publish'] : ['pm']

  const menuItems = [
    {
      key: 'pm',
      label: '采购项目管理',
      icon: <FolderOpenOutlined />,
      children: [
        ...(user?.role === 'officer'
          ? [{ key: 'new', label: '项目立项', onClick: () => navigate('/new') }]
          : []),
        { key: 'flow', label: '项目流程', onClick: () => navigate('/flow') },
        { key: 'bid', label: '开标管理', onClick: () => navigate('/bid') },
        { key: 'auth-letter', label: '授权函', onClick: () => navigate('/auth-letter') },
        { key: 'people-manage', label: '人员管理', onClick: () => navigate('/people-manage') },
      ],
    },
    { key: 'dispatch', label: '采购项目分发（开发中）', icon: <AuditOutlined />, disabled: true },
    { key: 'doc', label: '采购文件编制（开发中）', icon: <FolderOpenOutlined />, disabled: true },
    {
      key: 'publish',
      label: '挂网管理',
      icon: <CalendarOutlined />,
      children: [
        { key: 'announcement', label: '采购公告', onClick: () => navigate('/announcement') },
        { key: 'survey', label: '调研公告（开发中）', disabled: true },
        { key: 'correction', label: '更正公告（开发中）', disabled: true },
        { key: 'single-source', label: '单一来源公示（开发中）', disabled: true },
      ],
    },
  ]

  const userMenu = {
    items: [
      { key: 'chpwd', label: '修改密码', icon: <KeyOutlined />, onClick: () => navigate('/chpwd') },
      { key: 'logout', label: '退出登录', icon: <LogoutOutlined />, danger: true, onClick: handleLogout },
    ],
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark" style={{ overflow: 'auto' }}>
        <div style={{ padding: '16px 18px', color: '#fff', fontWeight: 'bold', fontSize: 15, borderBottom: '1px solid #2c3e50' }}>
          🏥 采购项目管理
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[activeKey]}
          defaultOpenKeys={defaultOpenKeys}
          items={menuItems}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', borderBottom: '1px solid #f0f0f0' }}>
          <div style={{ flex: 1 }} />
          <Dropdown menu={userMenu} placement="bottomRight">
            <Space style={{ cursor: 'pointer', color: '#555' }}>
              <UserOutlined />
              <Text>{user?.display_name}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>（{user?.role_cn}）</Text>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 24, background: '#f5f6fa', minHeight: 'calc(100vh - 64px - 48px)' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
