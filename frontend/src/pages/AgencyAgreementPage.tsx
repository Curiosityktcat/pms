import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Table, Button, Space, Tag, Input, Modal, Form, App, Typography,
} from 'antd'
import { FileWordOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { getProjects, type Project } from '../services/project'
import { generateAgencyAgreement } from '../services/agencyAgreement'

const { Title, Text } = Typography

/** 把日期格式化为「2026年5月29日」 */
function todayCN() {
  const d = new Date()
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

export default function AgencyAgreementPage() {
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
        // 仅「走代理」且非草稿的项目可生成委托代理协议
        const list = (res.data.data || []).filter(
          p => p.agency_code && !p.is_draft,
        )
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
      agency_address: '',
      officer_name: p.officer || '',
      officer_phone: '0832-2256120',
      sign_date: todayCN(),
    })
    setModalOpen(true)
  }

  const handleGenerate = async () => {
    if (!current) return
    const values = await form.validateFields()
    setGenerating(true)
    try {
      const res = await generateAgencyAgreement(current.id, values)
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `委托代理协议_${current.number || current.name}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('委托代理协议已生成，正在下载')
      setModalOpen(false)
    } catch (e: unknown) {
      const err = e as { response?: { data?: unknown } }
      message.error(
        err?.response?.data instanceof Blob
          ? '生成失败，请检查项目信息'
          : '生成失败',
      )
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
    { title: '经办人', dataIndex: 'officer', width: 100 },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: '操作',
      width: 150,
      render: (_: unknown, r: Project) => (
        <Button
          type="link"
          icon={<FileWordOutlined />}
          onClick={() => openModal(r)}
        >
          生成代理协议
        </Button>
      ),
    },
  ]

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <SafetyCertificateOutlined /> 委托代理协议
          </Title>
          <Text type="secondary">
            选择走代理机构的项目，按模板一键生成《委托代理协议》Word 文档。
          </Text>
        </div>

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
        title={`生成委托代理协议${current ? ` — ${current.name}` : ''}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleGenerate}
        okText="生成并下载"
        confirmLoading={generating}
        destroyOnHidden
        width={560}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item
            label="代理机构全称（乙方）"
            name="agency_name"
            rules={[{ required: true, message: '请填写代理机构全称' }]}
          >
            <Input placeholder="如：四川中锦招标代理有限公司" />
          </Form.Item>
          <Form.Item label="代理机构地址" name="agency_address">
            <Input placeholder="选填，留空则协议中地址处空白" />
          </Form.Item>
          <Form.Item
            label="甲方指定经办人"
            name="officer_name"
            rules={[{ required: true, message: '请填写经办人' }]}
          >
            <Input placeholder="如：黄新博" />
          </Form.Item>
          <Form.Item label="经办人联系电话" name="officer_phone">
            <Input />
          </Form.Item>
          <Form.Item label="签订时间" name="sign_date">
            <Input placeholder="如：2026年5月29日" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
