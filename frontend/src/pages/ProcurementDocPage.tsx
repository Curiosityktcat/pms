import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Table, Button, Space, Tag, Input, Modal, Form, InputNumber, App, Typography, Alert,
} from 'antd'
import { FileWordOutlined, FileTextOutlined } from '@ant-design/icons'
import { getProjects, type Project } from '../services/project'
import { generateBidCover } from '../services/procurementDoc'

const { Title, Text } = Typography

function todayCN() {
  const d = new Date()
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

export default function ProcurementDocPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [projects, setProjects] = useState<Project[]>([])
  const [keyword, setKeyword] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [current, setCurrent] = useState<Project | null>(null)
  const [generating, setGenerating] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(() => {
    setLoading(true)
    getProjects()
      .then(res => {
        const list = (res.data.data || []).filter(p => p.agency_code && !p.is_draft)
        setProjects(list)
      })
      .catch(() => message.error('加载项目失败'))
      .finally(() => setLoading(false))
  }, [message])
  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    const kw = keyword.trim()
    if (!kw) return projects
    return projects.filter(
      p =>
        (p.name || '').includes(kw) ||
        (p.number || '').includes(kw) ||
        (p.agency_name || '').includes(kw),
    )
  }, [projects, keyword])

  const openModal = (p: Project) => {
    setCurrent(p)
    form.setFieldsValue({
      agency_name: p.agency_name || '',
      round_number: p.round || 1,
      compile_date: todayCN(),
    })
    setModalOpen(true)
  }

  const handleGenerate = async () => {
    if (!current) return
    const values = await form.validateFields()
    setGenerating(true)
    try {
      const res = await generateBidCover(current.id, values)
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `招标文件封面_${current.number || current.name}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('招标文件封面已生成，正在下载')
      setModalOpen(false)
    } catch {
      message.error('生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const columns = [
    {
      title: '项目编号',
      dataIndex: 'number',
      width: 180,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    { title: '项目名称', dataIndex: 'name', ellipsis: true },
    {
      title: '代理机构',
      dataIndex: 'agency_name',
      width: 220,
      render: (v: string, r: Project) =>
        v ? <Tag color="blue">{v}</Tag> : <Tag>{r.agency_code}</Tag>,
    },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: '操作',
      width: 160,
      render: (_: unknown, r: Project) => (
        <Button type="link" icon={<FileWordOutlined />} onClick={() => openModal(r)}>
          生成招标文件封面
        </Button>
      ),
    },
  ]

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <FileTextOutlined /> 采购文件编制
          </Title>
          <Text type="secondary">
            选择走代理机构的项目，按模板生成招标文件封面。完整招标文件正文编制将后续支持。
          </Text>
        </div>

        <Alert
          type="info"
          showIcon
          message="当前支持「招标文件封面」自动生成；《内容确认表》原模板为旧版 .doc 格式，需转换为 .docx 后方可接入。"
        />

        <Input.Search
          placeholder="搜索项目名称 / 编号 / 代理机构"
          allowClear
          style={{ maxWidth: 360 }}
          onChange={e => setKeyword(e.target.value)}
        />

        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={filtered}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          size="middle"
        />
      </Space>

      <Modal
        title={`生成招标文件封面${current ? ` — ${current.name}` : ''}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleGenerate}
        okText="生成并下载"
        confirmLoading={generating}
        destroyOnHidden
        width={520}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item
            label="代理机构全称"
            name="agency_name"
            rules={[{ required: true, message: '请填写代理机构全称' }]}
          >
            <Input placeholder="如：四川中锦招标代理有限公司" />
          </Form.Item>
          <Form.Item label="第几次" name="round_number">
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="编制日期" name="compile_date">
            <Input placeholder="如：2026年5月29日" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
