import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, InputNumber, Switch, Space, Tag,
  App, Popconfirm, Typography, Alert,
} from 'antd'
import { PlusOutlined, EditOutlined, StopOutlined } from '@ant-design/icons'
import {
  listAgencies, createAgency, updateAgency, deactivateAgency, type AgencyInfo,
} from '../services/agency'
import { useAuth } from '../hooks/useAuth'

const { Text } = Typography

export default function AgencyManagePage() {
  const { message } = App.useApp()
  const { user } = useAuth()
  const canManage = ['assistant', 'pd_assistant', 'leader'].includes(user?.role || '') || !!user?.is_admin

  const [rows, setRows] = useState<AgencyInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<AgencyInfo | null>(null)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try { setRows((await listAgencies()).data.data || []) }
    catch { message.error('加载失败') }
    finally { setLoading(false) }
  }, [message])
  useEffect(() => { load() }, [load])

  const openEdit = (a: AgencyInfo | null) => {
    setEditing(a)
    form.setFieldsValue(a || {
      code: '', name: '', legal_rep: '', phone: '', address: '',
      in_rotation: 1, rotation_seq: 0, is_central: 0, active: 1,
    })
    setOpen(true)
  }

  const save = async () => {
    let v: Partial<AgencyInfo>
    try { v = await form.validateFields() } catch { return }
    setSaving(true)
    try {
      const res = editing ? await updateAgency(editing.id, v) : await createAgency(v)
      if (res.data.ok) { message.success('已保存'); setOpen(false); load() }
      else message.error(res.data.error || '保存失败')
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '保存失败')
    } finally { setSaving(false) }
  }

  const columns = [
    { title: '代码', dataIndex: 'code', width: 70 },
    {
      title: '机构名称', dataIndex: 'name',
      render: (v: string, r: AgencyInfo) => (
        <Space size={6}>
          <span style={{ fontWeight: 600 }}>{v}</span>
          {r.is_central ? <Tag color="purple">集中采购</Tag> : <Tag color="blue">社会代理</Tag>}
          {!r.active && <Tag>已停用</Tag>}
        </Space>
      ),
    },
    { title: '法定代表人', dataIndex: 'legal_rep', width: 100, render: (v: string) => v || <Text type="secondary">—</Text> },
    { title: '联系方式', dataIndex: 'phone', width: 160, render: (v: string) => v || <Text type="secondary">—</Text> },
    { title: '地址', dataIndex: 'address', render: (v: string) => v || <Text type="secondary">—</Text> },
    {
      title: '轮派', dataIndex: 'rotation_seq', width: 80,
      render: (v: number, r: AgencyInfo) => r.in_rotation ? `第 ${v} 顺位` : <Text type="secondary">不参与</Text>,
    },
    ...(canManage ? [{
      title: '操作', width: 130,
      render: (_: unknown, r: AgencyInfo) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          {!!r.active && (
            <Popconfirm title="停用该机构？历史项目不受影响。" onConfirm={async () => {
              try { await deactivateAgency(r.id); message.success('已停用'); load() }
              catch { message.error('停用失败') }
            }}>
              <Button size="small" danger icon={<StopOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    }] : []),
  ]

  return (
    <Card
      title="代理机构维护"
      extra={canManage && <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit(null)}>新增机构</Button>}
    >
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="维护代理机构的法定代表人、联系方式、地址等信息，供代理协议、合同等模块自动填充。停用不影响历史项目引用。"
      />
      <Table
        rowKey="id" size="small" loading={loading} columns={columns} dataSource={rows}
        pagination={false}
      />

      <Modal
        title={editing ? `编辑 — ${editing.name}` : '新增代理机构'}
        open={open} onCancel={() => setOpen(false)} onOk={save} confirmLoading={saving}
        okText="保存" width={560}
      >
        <Form form={form} layout="vertical">
          <Space size={12} style={{ display: 'flex' }}>
            <Form.Item label="机构代码" name="code" rules={[{ required: true, message: '必填' }]} style={{ flex: 1 }}>
              <Input placeholder="如 ZX（唯一）" disabled={!!editing} />
            </Form.Item>
            <Form.Item label="法定代表人" name="legal_rep" style={{ flex: 1 }}>
              <Input placeholder="法人姓名" />
            </Form.Item>
          </Space>
          <Form.Item label="机构名称" name="name" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="机构全称" />
          </Form.Item>
          <Form.Item label="联系方式" name="phone">
            <Input placeholder="电话 / 手机" />
          </Form.Item>
          <Form.Item label="地址" name="address">
            <Input.TextArea rows={2} placeholder="注册 / 办公地址" />
          </Form.Item>
          <Space size={20}>
            <Form.Item label="参与轮派" name="in_rotation" valuePropName="checked"
              getValueFromEvent={(c) => (c ? 1 : 0)} getValueProps={(v) => ({ checked: !!v })}>
              <Switch />
            </Form.Item>
            <Form.Item label="轮派顺位" name="rotation_seq">
              <InputNumber min={0} />
            </Form.Item>
            <Form.Item label="集中采购机构" name="is_central" valuePropName="checked"
              getValueFromEvent={(c) => (c ? 1 : 0)} getValueProps={(v) => ({ checked: !!v })}>
              <Switch />
            </Form.Item>
            <Form.Item label="启用" name="active" valuePropName="checked"
              getValueFromEvent={(c) => (c ? 1 : 0)} getValueProps={(v) => ({ checked: !!v })}>
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Card>
  )
}
