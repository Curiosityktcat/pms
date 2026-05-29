import { useState, useEffect } from 'react'
import {
  Card, Form, Input, Button, Space, App, Typography, Divider, Alert,
} from 'antd'
import { SaveOutlined, ApiOutlined, ThunderboltOutlined } from '@ant-design/icons'
import {
  getModelConfig, updateModelConfig, testModelConfig,
  type ScraperModelConfig,
} from '../services/bidBoard'

const { Text } = Typography

export default function ScraperSettingsPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [testing, setTesting] = useState(false)
  const [defaults, setDefaults] = useState<{ api?: string; name?: string }>({})

  useEffect(() => {
    setLoading(true)
    getModelConfig()
      .then(res => {
        form.setFieldsValue(res.data.data)
        setDefaults({ api: res.data.data.default_api, name: res.data.data.default_name })
      })
      .catch(() => message.error('加载模型配置失败'))
      .finally(() => setLoading(false))
  }, [form, message])

  const handleSave = async () => {
    let values: Record<string, unknown>
    try { values = await form.validateFields() } catch { return }
    setSaving(true)
    try {
      await updateModelConfig(values as Partial<ScraperModelConfig>)
      message.success('模型配置已保存')
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '保存失败')
    } finally { setSaving(false) }
  }

  const handleTest = async () => {
    const values = form.getFieldsValue()
    setTesting(true)
    try {
      const res = await testModelConfig(values)
      if (res.data.ok) message.success(res.data.message || '连接成功')
      else message.error(res.data.error || '连接失败')
    } catch {
      message.error('测试请求失败')
    } finally { setTesting(false) }
  }

  const restoreLocal = () => {
    form.setFieldsValue({
      model_api: defaults.api,
      model_name: defaults.name,
      api_key: 'local',
    })
    message.info('已填入本机大模型默认值，记得点「保存配置」')
  }

  return (
    <Card
      title={
        <Space>
          <ApiOutlined style={{ color: '#1677ff' }} />
          <span style={{ fontWeight: 700, fontSize: 16 }}>抓取模型设置</span>
        </Space>
      }
      style={{ maxWidth: 640 }}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
        message="本机大模型离线时，可在此切换到在线模型"
        description={
          <div>
            <p style={{ margin: '4px 0' }}>
              开标看板「手动刷新」会调用大模型从公告正文中提取项目信息。
              默认使用本机大模型（{defaults.api || '192.168.1.10:8888'}）。
            </p>
            <p style={{ margin: '4px 0' }}>
              本机模型不在线时，可改为任意 <strong>OpenAI 兼容</strong>的在线模型接口
              （如 DeepSeek、通义千问、Kimi 等），填好接口地址、模型名称和 API Key 即可。
            </p>
          </div>
        }
      />

      <Form form={form} layout="vertical" disabled={loading}>
        <Form.Item
          name="model_api"
          label="接口地址（chat/completions）"
          rules={[{ required: true, message: '请输入模型接口地址' }]}
          extra={<Text type="secondary" style={{ fontSize: 12 }}>
            需以 /v1/chat/completions 结尾，如 https://api.deepseek.com/v1/chat/completions
          </Text>}
        >
          <Input placeholder="http://192.168.1.10:8888/v1/chat/completions" />
        </Form.Item>

        <Form.Item
          name="model_name"
          label="模型名称"
          rules={[{ required: true, message: '请输入模型名称' }]}
        >
          <Input placeholder="如 deepseek-chat / qwen-plus" />
        </Form.Item>

        <Form.Item
          name="api_key"
          label="API Key"
          extra={<Text type="secondary" style={{ fontSize: 12 }}>
            已保存的 Key 已脱敏显示（****xxxx），如不修改请保持原值；本机模型可填 local
          </Text>}
        >
          <Input.Password placeholder="在线模型的 API Key（修改时填写）" visibilityToggle />
        </Form.Item>

        <Divider />

        <Form.Item>
          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
              保存配置
            </Button>
            <Button icon={<ThunderboltOutlined />} loading={testing} onClick={handleTest}>
              测试连接
            </Button>
            <Button type="link" onClick={restoreLocal}>
              恢复本机模型默认值
            </Button>
          </Space>
        </Form.Item>
      </Form>

      <div style={{ marginTop: 8, padding: '12px 16px', background: '#f6f8fc', borderRadius: 6 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          「测试连接」会用当前表单中的配置向模型发一次极简请求，验证接口、模型名与 Key 是否可用。
        </Text>
      </div>
    </Card>
  )
}
