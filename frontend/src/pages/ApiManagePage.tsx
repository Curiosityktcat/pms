/**
 * 后台「API 管理」：全系统大模型 API 台账。
 *
 * 每行一个 OpenAI 兼容端点（chat / embeddings），支持连通测试与
 * 一键设为全局对话/嵌入模型（写 sys_config，llm_client 即时生效）。
 */
import { useEffect, useState } from 'react'
import {
  Alert, App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm,
  Select, Space, Table, Tag, Tooltip, Typography,
} from 'antd'
import {
  ApiOutlined, CheckCircleOutlined, DeleteOutlined, EditOutlined,
  PlusOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import {
  activateApiProvider, createApiProvider, deleteApiProvider,
  listApiProviders, testApiProvider, updateApiProvider,
  type ApiProviderRow,
} from '../services/apiProvider'

const { Text } = Typography

export default function ApiManagePage() {
  const { message, modal } = App.useApp()
  const [rows, setRows] = useState<ApiProviderRow[]>([])
  const [activeChat, setActiveChat] = useState<number | null>(null)
  const [activeEmbed, setActiveEmbed] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [editing, setEditing] = useState<ApiProviderRow | null | 'new'>(null)
  const [form] = Form.useForm()

  const reload = async () => {
    setLoading(true)
    try {
      const r = await listApiProviders()
      setRows(r.data.data)
      setActiveChat(r.data.active_chat_id)
      setActiveEmbed(r.data.active_embed_id)
    } catch { message.error('加载失败') } finally { setLoading(false) }
  }
  useEffect(() => { reload() }, [])

  const openEdit = (row: ApiProviderRow | 'new') => {
    setEditing(row)
    if (row === 'new') {
      form.resetFields()
      form.setFieldsValue({ kind: 'chat', transport: 'requests', sort: rows.length + 1 })
    } else {
      form.setFieldsValue({ ...row, api_key: '' })
    }
  }

  const saveEdit = async () => {
    const values = await form.validateFields()
    try {
      if (editing === 'new') {
        if (!values.api_key) { message.warning('新增必须填 API Key'); return }
        await createApiProvider(values)
      } else if (editing) {
        await updateApiProvider(editing.id, values)
      }
      message.success('已保存')
      setEditing(null)
      reload()
    } catch (e: any) {
      message.error(e?.response?.data?.error || '保存失败')
    }
  }

  const doTest = async (row: ApiProviderRow) => {
    setTestingId(row.id)
    try {
      const r = await testApiProvider(row.id)
      if (r.data.ok) message.success(r.data.msg)
      else message.error(r.data.msg || '测试失败')
    } catch (e: any) {
      message.error(e?.response?.data?.msg || e?.message || '测试失败')
    } finally { setTestingId(null); reload() }
  }

  const doActivate = (row: ApiProviderRow) => {
    modal.confirm({
      title: `启用「${row.name}」为全局${row.kind === 'embed' ? '嵌入' : '对话'}模型？`,
      content: '开标看板抓取、AI 采购文件、合同审签 AI 识别等全部功能将立即切到该 API。',
      okText: '启用',
      cancelText: '取消',
      onOk: async () => {
        try {
          const r = await activateApiProvider(row.id)
          if (!r.data.ok) throw new Error(r.data.error)
          message.success(r.data.msg || '已启用')
          reload()
        } catch (e: any) {
          message.error(e?.response?.data?.error || e?.message || '启用失败')
        }
      },
    })
  }

  const doDelete = async (row: ApiProviderRow) => {
    try {
      const r = await deleteApiProvider(row.id)
      if (!r.data.ok) throw new Error(r.data.error)
      message.success('已删除')
      reload()
    } catch (e: any) {
      message.error(e?.response?.data?.error || e?.message || '删除失败')
    }
  }

  const columns = [
    {
      title: '名称', dataIndex: 'name', width: 190,
      render: (v: string, row: ApiProviderRow) => (
        <Space size={4}>
          <Text strong>{v}</Text>
          {row.id === activeChat && <Tag color="blue">全局对话</Tag>}
          {row.id === activeEmbed && <Tag color="purple">全局嵌入</Tag>}
        </Space>
      ),
    },
    {
      title: '类型', dataIndex: 'kind', width: 70,
      render: (v: string) => v === 'embed' ? <Tag>嵌入</Tag> : <Tag color="geekblue">对话</Tag>,
    },
    { title: '模型', dataIndex: 'model_name', width: 160, ellipsis: true },
    {
      title: '端点', dataIndex: 'base_url', ellipsis: true,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text>,
    },
    { title: 'Key', dataIndex: 'api_key_masked', width: 130, render: (v: string) => <Text code>{v || '—'}</Text> },
    {
      title: '通道', dataIndex: 'transport', width: 90,
      render: (v: string) => v === 'curl'
        ? <Tooltip title="本机透明代理下该外网 API 用 requests 会挂死，走 curl 系统栈"><Tag color="orange">curl</Tag></Tooltip>
        : <Tag>requests</Tag>,
    },
    {
      title: '最近测试', width: 200,
      render: (_: unknown, row: ApiProviderRow) => row.last_test_ok == null
        ? <Text type="secondary">未测试</Text>
        : (
          <Tooltip title={`${row.last_test_at} ${row.last_test_msg}`}>
            <Tag color={row.last_test_ok ? 'green' : 'red'}>
              {row.last_test_ok ? '通' : '不通'}
            </Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>{row.last_test_msg.slice(0, 22)}</Text>
          </Tooltip>
        ),
    },
    {
      title: '操作', width: 230, fixed: 'right' as const,
      render: (_: unknown, row: ApiProviderRow) => (
        <Space size={4}>
          <Button size="small" icon={<ThunderboltOutlined />}
            loading={testingId === row.id} onClick={() => doTest(row)}>测试</Button>
          <Button size="small" type="primary" ghost icon={<CheckCircleOutlined />}
            disabled={row.id === activeChat || row.id === activeEmbed}
            onClick={() => doActivate(row)}>启用</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          <Popconfirm title="删除这条 API 登记？" okText="删除" cancelText="取消"
            onConfirm={() => doDelete(row)}>
            <Button size="small" danger icon={<DeleteOutlined />}
              disabled={row.id === activeChat || row.id === activeEmbed} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title={<span><ApiOutlined /> API 管理</span>}
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit('new')}>登记 API</Button>}
    >
      <Alert
        style={{ marginBottom: 12 }}
        type="info" showIcon
        message="全系统大模型 API 台账。「启用」即切换全局模型（开标看板、AI 采购文件、合同审签 AI 识别等共用），无需重启；外网 agnesai / Gemini 必须选 curl 通道。"
      />
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
        scroll={{ x: 1150 }}
      />

      <Modal
        title={editing === 'new' ? '登记 API' : `编辑「${(editing as ApiProviderRow)?.name || ''}」`}
        open={editing !== null}
        onOk={saveEdit}
        onCancel={() => setEditing(null)}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如：agnesai 账号1" />
          </Form.Item>
          <Form.Item name="kind" label="类型" rules={[{ required: true }]}>
            <Select options={[{ value: 'chat', label: '对话（chat/completions）' },
                              { value: 'embed', label: '嵌入（embeddings）' }]} />
          </Form.Item>
          <Form.Item name="base_url" label="端点 URL（完整地址）"
            rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="https://…/v1/chat/completions" />
          </Form.Item>
          <Form.Item name="model_name" label="模型名" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如：agnes-2.0-flash" />
          </Form.Item>
          <Form.Item name="api_key" label={editing === 'new' ? 'API Key' : 'API Key（留空 = 不修改）'}>
            <Input.Password placeholder={editing === 'new' ? 'sk-…' : '不修改请留空'} autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="transport" label="HTTP 通道"
            tooltip="外网 agnesai / Gemini 在本机代理下必须选 curl，否则调用会挂死">
            <Select options={[{ value: 'requests', label: 'requests（本地/国内直连）' },
                              { value: 'curl', label: 'curl（agnesai / Gemini 等外网）' }]} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="限额、计费、使用注意等" />
          </Form.Item>
          <Form.Item name="sort" label="排序">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
