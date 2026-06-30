import { useState, useEffect } from 'react'
import {
  Card, Form, Input, Button, Space, App, Typography, Divider, Alert,
} from 'antd'
import { SaveOutlined, ApiOutlined, ThunderboltOutlined } from '@ant-design/icons'
import {
  getModelConfig, updateModelConfig, testModelConfig,
  getEmbedConfig, updateEmbedConfig, testEmbedConfig,
  type ScraperModelConfig, type EmbedModelConfig,
} from '../services/bidBoard'

const { Text } = Typography

export default function ScraperSettingsPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [testing, setTesting] = useState(false)
  const [defaults, setDefaults] = useState<{ api?: string; name?: string }>({})

  // 嵌入模型（投标审查语义检索）
  const [embedForm] = Form.useForm()
  const [embedSaving, setEmbedSaving]   = useState(false)
  const [embedTesting, setEmbedTesting] = useState(false)
  const [embedSuggest, setEmbedSuggest] = useState<{ api?: string; name?: string }>({})

  useEffect(() => {
    setLoading(true)
    getModelConfig()
      .then(res => {
        form.setFieldsValue(res.data.data)
        setDefaults({ api: res.data.data.default_api, name: res.data.data.default_name })
      })
      .catch(() => message.error('加载模型配置失败'))
      .finally(() => setLoading(false))
    getEmbedConfig()
      .then(res => {
        embedForm.setFieldsValue(res.data.data)
        setEmbedSuggest({ api: res.data.data.suggest_api, name: res.data.data.suggest_name })
      })
      .catch(() => { /* 嵌入未配置不算错误 */ })
  }, [form, embedForm, message])

  const handleEmbedSave = async () => {
    let values: Record<string, unknown>
    try { values = await embedForm.validateFields() } catch { return }
    setEmbedSaving(true)
    try {
      await updateEmbedConfig(values as Partial<EmbedModelConfig>)
      message.success('嵌入模型配置已保存')
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '保存失败')
    } finally { setEmbedSaving(false) }
  }

  const handleEmbedTest = async () => {
    const values = embedForm.getFieldsValue()
    setEmbedTesting(true)
    try {
      const res = await testEmbedConfig(values)
      if (res.data.ok) message.success(res.data.message || '连接成功')
      else message.error(res.data.error || '连接失败')
    } catch {
      message.error('测试请求失败')
    } finally { setEmbedTesting(false) }
  }

  const fillEmbedSuggest = () => {
    embedForm.setFieldsValue({
      embed_api: embedSuggest.api,
      embed_name: embedSuggest.name,
      embed_key: 'local',
    })
    message.info('已填入本机 bge-m3 建议值，记得点「保存配置」')
  }

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
    <Space direction="vertical" size="large" style={{ display: 'flex', maxWidth: 640 }}>
    <Card
      title={
        <Space>
          <ApiOutlined style={{ color: '#1677ff' }} />
          <span style={{ fontWeight: 700, fontSize: 16 }}>大模型设置（Chat）</span>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
        message="全系统大模型统一在此配置，本机离线时可切换到在线模型"
        description={
          <div>
            <p style={{ margin: '4px 0' }}>
              此处配置的模型为<strong>全系统共用</strong>：开标看板「手动刷新」提取公告信息、
              采购文件 AI 审阅/建议等功能都调用这同一套配置。
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

    <Card
      title={
        <Space>
          <ApiOutlined style={{ color: '#52c41a' }} />
          <span style={{ fontWeight: 700, fontSize: 16 }}>嵌入模型设置（Embedding）</span>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
        message="用于投标审查的语义检索（按语义召回相关页，补关键词漏命中）"
        description={
          <div>
            <p style={{ margin: '4px 0' }}>
              <strong>留空即不启用</strong>：未配置时投标审查自动退回纯关键词检索，行为与现状一致。
            </p>
            <p style={{ margin: '4px 0' }}>
              推荐本机起一个 <strong>llama.cpp 嵌入服务</strong>（免费、不占在线额度）：
              <Text code style={{ fontSize: 12 }}>
                llama-server -m bge-m3.gguf --embedding --port 8890 -ngl 99
              </Text>
              然后接口填 <Text code style={{ fontSize: 12 }}>{embedSuggest.api || 'http://127.0.0.1:8890/v1/embeddings'}</Text>。
            </p>
          </div>
        }
      />

      <Form form={embedForm} layout="vertical">
        <Form.Item
          name="embed_api"
          label="接口地址（embeddings）"
          extra={<Text type="secondary" style={{ fontSize: 12 }}>
            需以 /v1/embeddings 结尾；留空表示不启用语义检索
          </Text>}
        >
          <Input placeholder="http://127.0.0.1:8890/v1/embeddings" />
        </Form.Item>

        <Form.Item name="embed_name" label="模型名称">
          <Input placeholder="如 bge-m3" />
        </Form.Item>

        <Form.Item
          name="embed_key"
          label="API Key"
          extra={<Text type="secondary" style={{ fontSize: 12 }}>
            已保存的 Key 已脱敏显示（****xxxx），如不修改请保持原值；本机模型可填 local
          </Text>}
        >
          <Input.Password placeholder="本机模型可填 local" visibilityToggle />
        </Form.Item>

        <Divider />

        <Form.Item>
          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={embedSaving} onClick={handleEmbedSave}>
              保存配置
            </Button>
            <Button icon={<ThunderboltOutlined />} loading={embedTesting} onClick={handleEmbedTest}>
              测试连接
            </Button>
            <Button type="link" onClick={fillEmbedSuggest}>
              填入本机 bge-m3 建议值
            </Button>
          </Space>
        </Form.Item>
      </Form>

      <div style={{ marginTop: 8, padding: '12px 16px', background: '#f6fcf7', borderRadius: 6 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          「测试连接」会向嵌入接口求一次向量，成功会显示向量维度（如 1024）。
        </Text>
      </div>
    </Card>
    </Space>
  )
}
