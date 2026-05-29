import { useEffect, useState } from 'react'
import {
  Card, Table, Button, Tag, Space, Drawer, Form, Input, Select,
  Upload, App, Popconfirm, Typography, Segmented, Alert,
} from 'antd'
import {
  PlusOutlined, EditOutlined, StopOutlined, UploadOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import api from '../services/api'

const { Text } = Typography

interface Person {
  id: number
  name: string
  id_card: string
  department: string
  position: string
  photo: string
  role_type: 'supervisor' | 'representative'
  active: number
}

const ROLE_LABEL: Record<string, string> = {
  supervisor: '监督人员',
  representative: '采购人代表',
}

export default function PeopleManagePage() {
  const [people, setPeople] = useState<Person[]>([])
  const [loading, setLoading] = useState(true)
  const [roleFilter, setRoleFilter] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingPerson, setEditingPerson] = useState<Person | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [dupWarning, setDupWarning] = useState('')
  const [form] = Form.useForm()
  const { message } = App.useApp()

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get<{ ok: boolean; data: Person[] }>('/people')
      setPeople(res.data.data)
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openAdd = () => {
    setEditingPerson(null)
    setFileList([])
    setDupWarning('')
    form.resetFields()
    form.setFieldsValue({ role_type: 'representative' })
    setDrawerOpen(true)
  }

  const openEdit = (p: Person) => {
    setEditingPerson(p)
    setFileList([])
    setDupWarning('')
    form.setFieldsValue({
      name: p.name,
      id_card: p.id_card,
      department: p.department,
      position: p.position,
      role_type: p.role_type,
    })
    setDrawerOpen(true)
  }

  const handleNameBlur = async () => {
    if (editingPerson) return
    const name = form.getFieldValue('name')?.trim()
    if (!name) return
    const exists = people.filter(p => p.name === name && p.active === 1)
    if (exists.length > 0) {
      setDupWarning(`已有 ${exists.length} 位同名人员（${exists.map(e => e.department || '未填科室').join('、')}），请在科室或身份证号中加以区分`)
    } else {
      setDupWarning('')
    }
  }

  const handleSubmit = async () => {
    try {
      await form.validateFields()
    } catch {
      return
    }
    const values = form.getFieldsValue()
    const fd = new FormData()
    fd.append('name', values.name)
    fd.append('id_card', values.id_card || '')
    fd.append('department', values.department || '')
    fd.append('position', values.position || '')
    fd.append('role_type', values.role_type)
    if (fileList.length > 0 && fileList[0].originFileObj) {
      fd.append('photo', fileList[0].originFileObj)
    }

    setSubmitting(true)
    try {
      if (editingPerson) {
        const res = await api.put(`/people/${editingPerson.id}`, fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        message.success('已保存')
        if (res.data.warning) message.warning(res.data.warning)
      } else {
        const res = await api.post('/people', fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        message.success('已新增')
        if (res.data.warning) message.warning(res.data.warning)
      }
      setDrawerOpen(false)
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDisable = async (id: number) => {
    try {
      await api.delete(`/people/${id}`)
      message.success('已停用')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '操作失败')
    }
  }

  // 过滤
  const filtered = people.filter(p => {
    const matchRole = roleFilter === 'all' || p.role_type === roleFilter
    const q = search.trim()
    const matchSearch = !q ||
      p.name.includes(q) ||
      p.id_card.includes(q) ||
      p.department.includes(q) ||
      (p.position || '').includes(q)
    return matchRole && matchSearch
  })

  const supervisors = people.filter(p => p.role_type === 'supervisor')
  const representatives = people.filter(p => p.role_type === 'representative')

  const columns = [
    {
      title: '姓名',
      dataIndex: 'name',
      width: 100,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '科室/部门',
      dataIndex: 'department',
      width: 140,
      render: (v: string) => v || <Text type="secondary">未填</Text>,
    },
    {
      title: '职位',
      dataIndex: 'position',
      width: 180,
      ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: '身份证号',
      dataIndex: 'id_card',
      width: 180,
      render: (v: string) =>
        v ? <Text code style={{ fontSize: 12 }}>{v}</Text>
          : <Text type="secondary">未录入</Text>,
    },
    {
      title: '类型',
      dataIndex: 'role_type',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'supervisor' ? 'purple' : 'blue'}>
          {ROLE_LABEL[v] || v}
        </Tag>
      ),
    },
    {
      title: '照片',
      dataIndex: 'photo',
      width: 80,
      render: (v: string) =>
        v ? <Tag color="green">有</Tag>
          : <Tag color="default">无</Tag>,
    },
    {
      title: '操作',
      width: 100,
      render: (_: unknown, row: Person) => (
        <Space size={4}>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Popconfirm
            title="停用后该人员不再出现在选择列表中"
            onConfirm={() => handleDisable(row.id)}
            okText="停用"
            okButtonProps={{ danger: true }}
            cancelText="取消"
          >
            <Button size="small" type="link" danger icon={<StopOutlined />}>
              停用
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 12 }}>
        <span style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50' }}>人员管理</span>
        <Text type="secondary">
          监督人员 {supervisors.length} 位 · 采购人代表 {representatives.length} 位
        </Text>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={openAdd}
          style={{ marginLeft: 'auto' }}
        >
          新增人员
        </Button>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        <Segmented
          value={roleFilter}
          onChange={v => setRoleFilter(v as string)}
          options={[
            { label: '全部', value: 'all' },
            { label: '监督人员', value: 'supervisor' },
            { label: '采购人代表', value: 'representative' },
          ]}
        />
        <Input.Search
          placeholder="搜索姓名 / 科室 / 身份证号"
          allowClear
          style={{ width: 260 }}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={filtered}
        loading={loading}
        size="small"
        pagination={{ pageSize: 20, showTotal: t => `共 ${t} 位` }}
        locale={{ emptyText: '暂无人员' }}
      />

      {/* 新增/编辑抽屉 */}
      <Drawer
        title={editingPerson ? `编辑：${editingPerson.name}` : '新增人员'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={440}
        footer={
          <Space style={{ float: 'right' }}>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={submitting} onClick={handleSubmit}>保存</Button>
          </Space>
        }
      >
        {dupWarning && (
          <Alert
            type="warning"
            icon={<WarningOutlined />}
            showIcon
            message={dupWarning}
            style={{ marginBottom: 16 }}
          />
        )}

        <Form form={form} layout="vertical">
          <Form.Item label="姓名" name="name" rules={[{ required: true, message: '请填写姓名' }]}>
            <Input onBlur={handleNameBlur} />
          </Form.Item>

          <Form.Item label="类型" name="role_type" rules={[{ required: true }]}>
            <Select options={[
              { value: 'representative', label: '采购人代表' },
              { value: 'supervisor', label: '监督人员' },
            ]} />
          </Form.Item>

          <Form.Item
            label="科室 / 部门"
            name="department"
            extra="有同名人员时请填写以便区分"
          >
            <Input placeholder="如：外科、设备科、行政办公室…" />
          </Form.Item>

          <Form.Item label="职位" name="position">
            <Input placeholder="如：主任、副主任、护士长…" />
          </Form.Item>

          <Form.Item label="身份证号" name="id_card">
            <Input placeholder="18位身份证号" maxLength={18} />
          </Form.Item>

          <Form.Item
            label="身份证照片"
            extra="支持 jpg/png，如有旧照片会被替换"
          >
            {editingPerson?.photo && (
              <div style={{ marginBottom: 8, color: '#888', fontSize: 12 }}>
                当前：{editingPerson.photo.split('/').pop()}
              </div>
            )}
            <Upload
              maxCount={1}
              beforeUpload={() => false}
              fileList={fileList}
              onChange={({ fileList: fl }) => setFileList(fl)}
              accept=".jpg,.jpeg,.png"
            >
              <Button icon={<UploadOutlined />}>选择照片</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Drawer>
    </Card>
  )
}
