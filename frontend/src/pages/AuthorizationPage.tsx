import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App, Button, Card, Checkbox, DatePicker, Drawer, Form, Input, Modal,
  Radio, Select, Space, Table, Tag, Typography, Upload,
} from 'antd'
import { FilePdfOutlined, PlusOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useAuth } from '../hooks/useAuth'
import {
  authzDocumentUrl, createAuthorization, getAuthzCatalog, getAuthzDepts,
  getAuthzUsers, listAuthorizations, revokeAuthorization, uploadAuthzDocument,
  type AuthorizationInfo, type AuthzDept, type AuthzUser, type PermGroup,
} from '../services/authorization'

const { Text, Title } = Typography
const SOURCE_CN = { delegate: '负责人委托', resolution: '医院决议' }
const STATE_COLOR: Record<string, string> = {
  生效: 'green', 已撤销: 'default', 未开始: 'blue', 已过期: 'orange', 授权人已换人: 'red',
}

function errorText(err: any, fallback = '操作失败') {
  return err?.response?.data?.error || fallback
}

export default function AuthorizationPage() {
  const { user } = useAuth()
  const { message } = App.useApp()
  const [rows, setRows] = useState<AuthorizationInfo[]>([])
  const [catalog, setCatalog] = useState<PermGroup[]>([])
  const [users, setUsers] = useState<AuthzUser[]>([])
  const [depts, setDepts] = useState<AuthzDept[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [uploaded, setUploaded] = useState<{ path: string; name: string } | null>(null)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [filters, setFilters] = useState({ dept_code: '', grantee: '', status: '', source: '' })
  const [form] = Form.useForm()
  const source = Form.useWatch('source', form)
  const isDept = user?.role === 'dept'

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listAuthorizations(filters)
      setRows(res.data.data)
    } catch (err) { message.error(errorText(err, '加载授权台账失败')) }
    finally { setLoading(false) }
  }, [filters, message])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    Promise.all([getAuthzCatalog(), getAuthzUsers(), getAuthzDepts()]).then(([c, u, d]) => {
      setCatalog(c.data.data); setUsers(u.data.data); setDepts(d.data.data)
    }).catch(err => message.error(errorText(err, '加载授权字典失败')))
  }, [message])

  const allKeys = useMemo(() => catalog.flatMap(group => group.items.map(item => item.key)), [catalog])
  const visibleCatalog = useMemo(() => isDept
    ? catalog.map(group => ({ ...group, items: group.items.filter(item => user?.perms.includes(item.key)) })).filter(group => group.items.length)
    : catalog, [catalog, isDept, user?.perms])
  const visibleKeys = useMemo(() => visibleCatalog.flatMap(group => group.items.map(item => item.key)), [visibleCatalog])
  const openCreate = () => {
    form.resetFields()
    form.setFieldsValue({ source: isDept ? 'delegate' : 'resolution' })
    setSelectedKeys([]); setUploaded(null); setFileList([]); setOpen(true)
  }
  const toggleGroup = (group: PermGroup, checked: boolean) => {
    const keys = new Set(selectedKeys)
    group.items.forEach(item => checked ? keys.add(item.key) : keys.delete(item.key))
    setSelectedKeys(Array.from(keys))
  }
  const save = async () => {
    let values: any
    try { values = await form.validateFields() } catch { return }
    if (!selectedKeys.length) { message.error('至少选择一项权限'); return }
    if (!uploaded) { message.error('请先上传签字盖章的凭证 PDF'); return }
    setSaving(true)
    try {
      await createAuthorization({
        ...values, perm_keys: selectedKeys,
        valid_from: values.valid_range[0].format('YYYY-MM-DD'),
        valid_to: values.valid_range[1].format('YYYY-MM-DD'),
        valid_range: undefined, doc_path: uploaded.path, doc_name: uploaded.name,
      })
      message.success('授权已建立'); setOpen(false); await load()
    } catch (err) { message.error(errorText(err)) }
    finally { setSaving(false) }
  }
  const revoke = (row: AuthorizationInfo) => {
    let reason = ''
    Modal.confirm({
      title: `撤销对 ${row.grantee_name || row.grantee_username} 的授权`,
      content: <Input.TextArea autoFocus rows={3} placeholder="请填写撤销原因（必填）" onChange={e => { reason = e.target.value }} />,
      okText: '确认撤销', okButtonProps: { danger: true }, cancelText: '取消',
      onOk: async () => {
        if (!reason.trim()) { message.error('撤销原因不能为空'); return Promise.reject() }
        try { await revokeAuthorization(row.id, reason.trim()); message.success('授权已撤销'); await load() }
        catch (err) { message.error(errorText(err)); return Promise.reject() }
      },
    })
  }

  const columns = [
    { title: '被授权人', render: (_: unknown, r: AuthorizationInfo) => <><div>{r.grantee_name || r.grantee_username}</div><Text type="secondary">{r.grantee_username}</Text></> },
    { title: '科室', dataIndex: 'grantee_dept_code', render: (v: string) => depts.find(d => d.code === v)?.name || v },
    { title: '来源', dataIndex: 'source', render: (v: keyof typeof SOURCE_CN, r: AuthorizationInfo) => <><Tag color={v === 'resolution' ? 'purple' : 'blue'}>{SOURCE_CN[v]}</Tag>{r.doc_no && <div>{r.doc_no}</div>}</> },
    { title: '授权人', dataIndex: 'granter_name' },
    { title: '权限', dataIndex: 'perm_keys', render: (v: string[]) => `${v.length} 项` },
    { title: '有效期', render: (_: unknown, r: AuthorizationInfo) => `${r.valid_from} 至 ${r.valid_to}` },
    { title: '生效状态', dataIndex: 'effective_state', render: (v: string) => <Tag color={STATE_COLOR[v]}>{v}</Tag> },
    { title: '凭证', render: (_: unknown, r: AuthorizationInfo) => <Button type="link" icon={<FilePdfOutlined />} href={authzDocumentUrl(r.id)}>{r.doc_name}</Button> },
    { title: '操作', render: (_: unknown, r: AuthorizationInfo) => r.status === 'active' ? <Button danger size="small" onClick={() => revoke(r)}>撤销</Button> : <Text type="secondary">{r.revoke_reason || '已撤销'}</Text> },
  ]

  return <Card>
    <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} align="start">
      <div><Title level={4} style={{ margin: 0 }}>授权台账</Title><Text type="secondary">授权是否生效按期限和当前科室负责人实时判定。</Text></div>
      <Space><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建授权</Button></Space>
    </Space>
    <Space wrap style={{ marginBottom: 16 }}>
      {!isDept && <Select allowClear placeholder="科室" style={{ width: 180 }} options={depts.map(d => ({ value: d.code, label: d.name }))} onChange={v => setFilters(f => ({ ...f, dept_code: v || '' }))} />}
      <Input.Search allowClear placeholder="被授权人 / 用户名" style={{ width: 220 }} onSearch={v => setFilters(f => ({ ...f, grantee: v }))} />
      <Select allowClear placeholder="生效状态" style={{ width: 150 }} options={Object.keys(STATE_COLOR).map(v => ({ value: v, label: v }))} onChange={v => setFilters(f => ({ ...f, status: v || '' }))} />
      <Select allowClear placeholder="授权来源" style={{ width: 150 }} options={Object.entries(SOURCE_CN).map(([value, label]) => ({ value, label }))} onChange={v => setFilters(f => ({ ...f, source: v || '' }))} />
    </Space>
    <Table rowKey="id" loading={loading} columns={columns} dataSource={rows} scroll={{ x: 1200 }} />

    <Drawer title="新建授权" open={open} width={680} onClose={() => setOpen(false)} extra={<Button type="primary" loading={saving} onClick={() => void save()}>提交授权</Button>} destroyOnHidden>
      <Form form={form} layout="vertical">
        <Form.Item name="source" label="授权来源" rules={[{ required: true }]}>
          <Radio.Group disabled={isDept} options={isDept ? [{ value: 'delegate', label: '科室负责人委托' }] : [{ value: 'resolution', label: '医院决议' }]} />
        </Form.Item>
        <Form.Item name="grantee_username" label="被授权人" rules={[{ required: true, message: '请选择被授权人' }]}>
          <Select showSearch optionFilterProp="label" options={users.map(u => ({ value: u.username, label: `${u.display_name || u.username}（${depts.find(d => d.code === u.dept_code)?.name || u.dept_code}）` }))} />
        </Form.Item>
        {source === 'resolution' && <Form.Item name="doc_no" label="决议文号" rules={[{ required: true, message: '请输入决议文号' }]}><Input /></Form.Item>}
        <Form.Item label="授予权限" required>
          <Space style={{ marginBottom: 8 }}><Button size="small" onClick={() => setSelectedKeys(isDept ? visibleKeys : allKeys)}>全选</Button><Button size="small" onClick={() => setSelectedKeys([])}>清空</Button><Text type="secondary">已选 {selectedKeys.length} 项</Text></Space>
          {visibleCatalog.map(group => {
            const keys = group.items.map(item => item.key)
            const count = keys.filter(key => selectedKeys.includes(key)).length
            return <Card key={group.group} size="small" title={<Checkbox checked={count === keys.length} indeterminate={count > 0 && count < keys.length} onChange={e => toggleGroup(group, e.target.checked)}>{group.group}</Checkbox>} style={{ marginBottom: 8 }}>
              <Checkbox.Group value={selectedKeys.filter(key => keys.includes(key))} onChange={v => {
                const outside = selectedKeys.filter(key => !keys.includes(key))
                setSelectedKeys([...outside, ...(v as string[])])
              }} options={group.items.map(item => ({ value: item.key, label: item.label }))} />
            </Card>
          })}
        </Form.Item>
        <Form.Item name="valid_range" label="授权期限" rules={[{ required: true, message: '请选择开始和结束日期' }]}><DatePicker.RangePicker style={{ width: '100%' }} format="YYYY-MM-DD" /></Form.Item>
        <Form.Item label="凭证 PDF" required extra={source === 'delegate' ? '请上传双方签字并注明时间的申请书。' : '请上传盖章的医院决议。'}>
          <Upload accept=".pdf,application/pdf" maxCount={1} fileList={fileList} beforeUpload={async file => {
            if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) { message.error('只允许上传 PDF'); return Upload.LIST_IGNORE }
            if (file.size > 20 * 1024 * 1024) { message.error('PDF 不能超过 20MB'); return Upload.LIST_IGNORE }
            setFileList([{ uid: file.uid, name: file.name, status: 'uploading' }])
            try { const res = await uploadAuthzDocument(file); setUploaded(res.data); setFileList([{ uid: file.uid, name: file.name, status: 'done' }]); message.success('凭证上传成功') }
            catch (err) { setFileList([]); setUploaded(null); message.error(errorText(err, '上传失败')) }
            return false
          }} onRemove={() => { setUploaded(null); setFileList([]) }}><Button icon={<UploadOutlined />}>选择 PDF</Button></Upload>
        </Form.Item>
      </Form>
    </Drawer>
  </Card>
}
