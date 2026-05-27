import { useState } from 'react'
import { Form, Input, Button, Card, Typography, App } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { authLogin } from '../services/auth'
import { useAuth } from '../hooks/useAuth'

const { Title } = Typography

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const { setUser } = useAuth()
  const navigate = useNavigate()
  const { message } = App.useApp()

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = await authLogin(values.username, values.password)
      setUser(res.data.user)
      navigate('/flow')
    } catch (err: any) {
      message.error(err.response?.data?.error || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#eef1f4', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Card style={{ width: 360, boxShadow: '0 2px 12px rgba(0,0,0,.1)' }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 28 }}>🏥 采购项目管理</Title>
        <Form onFinish={onFinish} size="large" autoComplete="off">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading}>登 录</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
