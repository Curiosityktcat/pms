import { useState, useEffect } from 'react'
import {
  Card, Form, Input, Button, Space, App, Typography, Divider, Alert,
} from 'antd'
import { SaveOutlined, SendOutlined, MailOutlined } from '@ant-design/icons'
import { getEmailConfig, updateEmailConfig, testEmail, type EmailConfig } from '../services/inquiry'

const { Text } = Typography

export default function EmailSettingsPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    setLoading(true)
    getEmailConfig()
      .then(res => {
        form.setFieldsValue(res.data.data)
      })
      .catch(() => message.error('加载邮件配置失败'))
      .finally(() => setLoading(false))
  }, [form, message])

  const handleSave = async () => {
    let values: Record<string, unknown>
    try { values = await form.validateFields() } catch { return }
    setSaving(true)
    try {
      await updateEmailConfig(values as Partial<EmailConfig>)
      message.success('邮件配置已保存')
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '保存失败')
    } finally { setSaving(false) }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const res = await testEmail()
      message.success(res.data.message || '测试邮件已发送')
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '发送失败，请检查邮件配置')
    } finally { setTesting(false) }
  }

  return (
    <Card
      title={
        <Space>
          <MailOutlined style={{ color: '#1677ff' }} />
          <span style={{ fontWeight: 700, fontSize: 16 }}>邮件发送设置</span>
        </Space>
      }
      style={{ maxWidth: 600 }}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
        message="163邮箱配置说明"
        description={
          <div>
            <p style={{ margin: '4px 0' }}>
              请使用 163 邮箱的<strong>授权码</strong>而非登录密码。
            </p>
            <p style={{ margin: '4px 0' }}>
              授权码获取方式：登录 163 邮箱 → 设置 → POP3/SMTP/IMAP → 开启 SMTP 服务 → 获取授权码。
            </p>
          </div>
        }
      />

      <Form
        form={form}
        layout="vertical"
        disabled={loading}
      >
        <Form.Item
          name="email_smtp_host"
          label="SMTP 服务器"
          rules={[{ required: true, message: '请输入 SMTP 服务器地址' }]}
        >
          <Input placeholder="smtp.163.com" />
        </Form.Item>

        <Form.Item
          name="email_smtp_port"
          label="端口号"
          rules={[{ required: true, message: '请输入端口号' }]}
          extra={<Text type="secondary" style={{ fontSize: 12 }}>SSL 加密：465；STARTTLS：587</Text>}
        >
          <Input placeholder="465" style={{ width: 120 }} />
        </Form.Item>

        <Form.Item
          name="email_address"
          label="发件邮箱地址"
          rules={[
            { required: true, message: '请输入发件邮箱' },
            { type: 'email', message: '请输入有效的邮箱地址' },
          ]}
        >
          <Input placeholder="example@163.com" />
        </Form.Item>

        <Form.Item
          name="email_auth_code"
          label="授权码"
          extra={
            <Text type="secondary" style={{ fontSize: 12 }}>
              已保存的授权码已脱敏显示（****xxxx），如不修改请留空或保持原值
            </Text>
          }
        >
          <Input.Password
            placeholder="输入 163 邮箱授权码（修改时填写）"
            visibilityToggle
          />
        </Form.Item>

        <Form.Item
          name="email_sender_name"
          label="发件人署名"
          rules={[{ required: true, message: '请输入发件人署名' }]}
          extra={<Text type="secondary" style={{ fontSize: 12 }}>
            显示在邮件发件人栏中，如：内江市第一人民医院采购部
          </Text>}
        >
          <Input placeholder="内江市第一人民医院采购部" />
        </Form.Item>

        <Divider />

        <Form.Item>
          <Space>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
            >
              保存配置
            </Button>
            <Button
              icon={<SendOutlined />}
              loading={testing}
              onClick={handleTest}
            >
              发送测试邮件
            </Button>
          </Space>
        </Form.Item>
      </Form>

      <div style={{ marginTop: 8, padding: '12px 16px', background: '#f6f8fc', borderRadius: 6 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          点击「发送测试邮件」将向当前配置的发件邮箱发送一封测试邮件，
          用于验证 SMTP 配置是否正确。请先保存配置后再测试。
        </Text>
      </div>
    </Card>
  )
}
