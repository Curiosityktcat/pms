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
        theme="dark"
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'sticky',
          top: 0,
          left: 0,
          // 用青蓝色背景与业务系统的默认深蓝侧栏区分
          background: '#001529',
        }}
      >
        <div style={{
          padding: '14px 16px 12px',
          borderBottom: '1px solid rgba(255,255,255,.1)',
          background: 'rgba(0,0,0,.25)',
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
              background: '#13c2c2',
              borderRadius: 6,
              width: 28, height: 28,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16, flexShrink: 0,
            }}>⚙️</span>
            <span style={{ lineHeight: 1.3 }}>后台管理系统<br />
              <span style={{ fontSize: 11, fontWeight: 400, color: 'rgba(255,255,255,.55)' }}>
                系统级配置
              </span>
            </span>
          </div>
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[activeKey]}
          defaultOpenKeys={['sys']}
          items={menuItems}
          style={{ borderRight: 0, marginTop: 4 }}
        />
      </Sider>

      <Layout>
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
