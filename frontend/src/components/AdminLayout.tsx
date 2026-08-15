import { Layout, Menu, Dropdown, Space, Button } from 'antd'
import {
  SafetyOutlined,
  ApiOutlined,
  MailOutlined,
  RollbackOutlined,
  UserOutlined,
  LogoutOutlined,
  KeyOutlined,
  ControlOutlined,
  BarChartOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { authLogout } from '../services/auth'

const { Sider, Header, Content } = Layout

/**
 * 后台管理系统布局。
 * 与业务系统（AppLayout）完全独立的一套界面，仅系统管理员可进入，
 * 承载权限管理、大模型配置、邮件配置等系统级设置。
 */
export default function AdminLayout() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  // 仅系统管理员可访问后台；其余角色回到业务系统
  if (!user?.is_admin) {
    return <Navigate to="/flow" replace />
  }

  const handleLogout = async () => {
    await authLogout()
    setUser(null)
    navigate('/login')
  }

  const activeKey = location.pathname.split('/').filter(Boolean)[1] || 'permissions'

  const menuItems = [
    {
      key: 'sys',
      label: '系统配置',
      icon: <ControlOutlined />,
      children: [
        {
          key: 'users',
          icon: <UserOutlined />,
          label: '用户管理',
          onClick: () => navigate('/admin/users'),
        },
        {
          key: 'permissions',
          icon: <SafetyOutlined />,
          label: '权限管理',
          onClick: () => navigate('/admin/permissions'),
        },
        {
          key: 'model',
          icon: <ApiOutlined />,
          label: '大模型配置',
          onClick: () => navigate('/admin/model'),
        },
        {
          key: 'api',
          icon: <KeyOutlined />,
          label: 'API 管理',
          onClick: () => navigate('/admin/api'),
        },
        {
          key: 'usage',
          icon: <BarChartOutlined />,
          label: 'Token 用量',
          onClick: () => navigate('/admin/usage'),
        },
        {
          key: 'email',
          icon: <MailOutlined />,
          label: '邮件配置',
          onClick: () => navigate('/admin/email'),
        },
      ],
    },
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

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={220}
        theme="light"
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'sticky',
          top: 0,
          left: 0,
          background: '#fff',
          borderRight: '1px solid #e8eaed',
        }}
      >
        <div style={{
          padding: '16px 16px 12px',
          borderBottom: '1px solid #e8eaed',
          background: '#fff',
        }}>
          <div style={{
            color: '#202124',
            fontWeight: 600,
            fontSize: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}>
            <span style={{
              background: '#137333',
              borderRadius: 8,
              width: 30, height: 30,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16, flexShrink: 0,
            }}>⚙️</span>
            <span style={{ lineHeight: 1.3 }}>后台管理系统<br />
              <span style={{ fontSize: 11, fontWeight: 400, color: '#5f6368' }}>
                系统级配置
              </span>
            </span>
          </div>
        </div>

        <Menu
          theme="light"
          mode="inline"
          selectedKeys={[activeKey]}
          defaultOpenKeys={['sys']}
          items={menuItems}
          style={{ borderRight: 0, marginTop: 6, background: 'transparent' }}
        />
      </Sider>

      <Layout>
        <Header style={{
          background: '#fff',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          borderBottom: '1px solid #e8eaed',
          boxShadow: '0 1px 2px 0 rgba(60,64,67,.05)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}>
          <Button
            icon={<RollbackOutlined />}
            type="text"
            onClick={() => navigate('/flow')}
            style={{ color: '#666', fontSize: 13 }}
          >
            返回业务系统
          </Button>
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
                background: '#13c2c2',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <UserOutlined style={{ color: '#fff', fontSize: 14 }} />
              </div>
              <div style={{ lineHeight: 1.3 }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: '#333' }}>
                  {user?.display_name}
                </div>
                <div style={{ fontSize: 11, color: '#888' }}>管理员</div>
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
