import { useCallback, useEffect, useState } from 'react'
import {
  App, Button, Card, Drawer, Form, Input, InputNumber, Modal,
  Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Typography,
} from 'antd'
import { CopyOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, HistoryOutlined, PlusOutlined, ReloadOutlined, TeamOutlined } from '@ant-design/icons'
import { listAgencies, type AgencyInfo } from '../services/agency'
import {
  bulkDeptAccounts, createDept, createUser, deleteDept, deleteUser, getUserAudit, listDepts, listRoles,
  listUsers, resetUserPassword, toggleUser, updateDept, updateUser,
  type AdminUser, type AuditInfo, type BulkDeptAccount, type DeptInfo, type RoleInfo,
} from '../services/userAdmin'

const { Text, Title } = Typography
const ACTION_CN: Record<string, string> = {
  create: '新建账号', update: '修改账号', reset_pwd: '重置密码', toggle: '切换状态', delete: '删除账号',
}
const CATEGORY_OPTIONS = ['归口', '需求', '实施', '职能', '监督', '法务'].map(value => ({ value, label: value }))

function errorText(err: any, fallback = '操作失败') {
  return err?.response?.data?.error || fallback
}

export default function UserAdminPage() {
  const { message, modal } = App.useApp()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [roles, setRoles] = useState<RoleInfo[]>([])
  const [depts, setDepts] = useState<DeptInfo[]>([])
  const [agencies, setAgencies] = useState<AgencyInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [filters, setFilters] = useState({ q: '', role: '', active: '' })
  const [userOpen, setUserOpen] = useState(false)
  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [saving, setSaving] = useState(false)
  const [auditOpen, setAuditOpen] = useState(false)
  const [audits, setAudits] = useState<AuditInfo[]>([])
  const [auditUser, setAuditUser] = useState('')
  const [deptOpen, setDeptOpen] = useState(false)
  const [editingDept, setEditingDept] = useState<DeptInfo | null>(null)
  const [userForm] = Form.useForm()
  const [deptForm] = Form.useForm()
  const watchedRole = Form.useWatch('role', userForm)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listUsers({ ...filters, page, size })
      setUsers(res.data.data); setTotal(res.data.total)
    } catch (err) { message.error(errorText(err, '加载账号失败')) }
    finally { setLoading(false) }
  }, [filters, page, size, message])

  const loadDictionaries = useCallback(async () => {
    try {
      const [roleRes, deptRes, agencyRes] = await Promise.all([listRoles(), listDepts(), listAgencies()])
      setRoles(roleRes.data.data); setDepts(deptRes.data.data); setAgencies(agencyRes.data.data)
    } catch (err) { message.error(errorText(err, '加载字典失败')) }
  }, [message])

  useEffect(() => { void loadUsers() }, [loadUsers])
  useEffect(() => { void loadDictionaries() }, [loadDictionaries])

  const openUser = (user?: AdminUser) => {
    setEditing(user || null)
    userForm.resetFields()
    userForm.setFieldsValue(user ? { ...user, active: Boolean(user.active) } : { role: 'officer', active: true })
    setUserOpen(true)
  }

  const showPassword = (password: string) => {
    modal.info({
      title: '一次性密码', width: 460, okText: '我已保存，关闭',
      content: <div><Input value={password} readOnly addonAfter={<CopyOutlined onClick={() => void navigator.clipboard.writeText(password).then(() => message.success('已复制'))} />} /><Text type="danger">关闭后不可再查看，请立即复制并安全交给本人。</Text></div>,
    })
  }

  const saveUser = async () => {
    let values: any
    try { values = await userForm.validateFields() } catch { return }
    setSaving(true)
    try {
      if (editing) {
        const res = await updateUser(editing.id, { ...values, active: values.active ? 1 : 0 })
        message.success('账号已保存')
        if (res.data.warning) message.warning(res.data.warning)
      } else {
        const res = await createUser(values)
        setUserOpen(false); showPassword(res.data.password)
      }
      setUserOpen(false); await Promise.all([loadUsers(), loadDictionaries()])
    } catch (err) { message.error(errorText(err)) }
    finally { setSaving(false) }
  }

  const resetPassword = async (user: AdminUser) => {
    try { const res = await resetUserPassword(user.id); showPassword(res.data.password) }
    catch (err) { message.error(errorText(err)) }
  }

  const showAudit = async (user: AdminUser) => {
    setAuditUser(user.username); setAuditOpen(true); setAudits([])
    try { setAudits((await getUserAudit(user.id)).data.data) }
    catch (err) { message.error(errorText(err, '加载历史失败')) }
  }

  const saveDept = async () => {
    let values: any
    try { values = await deptForm.validateFields() } catch { return }
    try {
      const data = { ...values, active: values.active ? 1 : 0 }
      if (editingDept) await updateDept(editingDept.id, data)
      else await createDept(data)
      message.success('科室已保存'); setDeptOpen(false); await loadDictionaries()
    } catch (err) { message.error(errorText(err)) }
  }

  const accountText = (rows: BulkDeptAccount[]) => rows
    .map(row => `${row.username}\t${row.password || ''}\t${row.role}\t${row.dept_code}`).join('\n')

  const downloadAccounts = (rows: BulkDeptAccount[]) => {
    const quote = (value: string) => `"${value.replace(/"/g, '""')}"`
    const csv = ['用户名,一次性密码,角色,科室编码,科室类型', ...rows.map(row =>
      [row.username, row.password || '', row.role, row.dept_code, row.dept_type].map(quote).join(','))].join('\r\n')
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = '科室账号.csv'; link.click()
    URL.revokeObjectURL(url)
  }

  const showBulkResult = (rows: BulkDeptAccount[]) => modal.info({
    title: `已创建 ${rows.length} 个科室账号`, width: 760, okText: '我已保存，关闭',
    content: <Space direction="vertical" style={{ width: '100%' }}>
      <Text type="danger">明文密码关闭后不可再查看，请立即复制或下载并安全保管。</Text>
      <Space>
        <Button icon={<CopyOutlined />} onClick={() => void navigator.clipboard.writeText(accountText(rows)).then(() => message.success('已复制全部'))}>复制全部</Button>
        <Button icon={<DownloadOutlined />} onClick={() => downloadAccounts(rows)}>下载 CSV</Button>
      </Space>
      <Table size="small" rowKey="dept_code" pagination={{ pageSize: 10 }} dataSource={rows} columns={[
        { title: '用户名', dataIndex: 'username' }, { title: '一次性密码', dataIndex: 'password' },
        { title: '角色', dataIndex: 'role' }, { title: '科室编码', dataIndex: 'dept_code' },
      ]} />
    </Space>,
  })

  const previewBulk = async () => {
    try {
      const rows = (await bulkDeptAccounts(true)).data.pending
      if (!rows.length) { message.info('所有启用科室都已有账号'); return }
      modal.confirm({
        title: `将创建 ${rows.length} 个科室账号`, width: 680, okText: '确认创建',
        content: <Table size="small" rowKey="dept_code" pagination={{ pageSize: 8 }} dataSource={rows} columns={[
          { title: '科室', dataIndex: 'username' }, { title: '类型', dataIndex: 'dept_type' },
          { title: '角色', dataIndex: 'role' }, { title: '编码', dataIndex: 'dept_code' },
        ]} />,
        onOk: async () => {
          const created = (await bulkDeptAccounts(false)).data.created
          await Promise.all([loadUsers(), loadDictionaries()]); showBulkResult(created)
        },
      })
    } catch (err) { message.error(errorText(err, '批量建号失败')) }
  }

  const userColumns = [
    { title: '用户名', dataIndex: 'username' }, { title: '姓名', dataIndex: 'display_name' },
    { title: '角色', dataIndex: 'role', render: (value: string) => <Tag color="blue">{roles.find(r => r.role === value)?.role_cn || value}</Tag> },
    { title: '所属科室 / 代理', render: (_: unknown, user: AdminUser) => user.dept_code ? <Space direction="vertical" size={0}><span>{user.dept?.name || user.dept_code}</span><Text type="secondary">{user.dept?.dept_type || '类型未设置'} · {user.dept?.is_manage_dept ? '归口管理科室' : '需求科室'}</Text></Space> : user.agency_code ? (agencies.find(a => a.code === user.agency_code)?.name || user.agency_code) : '-' },
    { title: '状态', dataIndex: 'active', render: (value: number) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> },
    { title: '操作', width: 390, render: (_: unknown, user: AdminUser) => <Space wrap>
      <Button size="small" icon={<EditOutlined />} onClick={() => openUser(user)}>编辑</Button>
      <Button size="small" icon={<ReloadOutlined />} onClick={() => void resetPassword(user)}>重置密码</Button>
      <Popconfirm title={user.active ? '停用后该账号将不能登录，确认停用？' : '确认重新启用该账号？'} onConfirm={async () => { try { await toggleUser(user.id); message.success('状态已更新'); await loadUsers() } catch (err) { message.error(errorText(err)) } }}><Button size="small" danger={Boolean(user.active)}>{user.active ? '停用' : '启用'}</Button></Popconfirm>
      <Button size="small" icon={<HistoryOutlined />} onClick={() => void showAudit(user)}>历史</Button>
      <Popconfirm title="仅限从未使用过的账号，确认永久删除？" okText="永久删除" okButtonProps={{ danger: true }} onConfirm={async () => { try { await deleteUser(user.id); message.success('账号已删除'); await loadUsers() } catch (err) { message.error(errorText(err)) } }}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>
    </Space> },
  ]

  const deptColumns = [
    { title: '编码', dataIndex: 'code' }, { title: '名称', dataIndex: 'name' },
    { title: '科室类型', dataIndex: 'dept_type', render: (v: string) => v || '-' },
    { title: '负责人', dataIndex: 'head_name', render: (v: string) => v || '-' },
    { title: '别名', dataIndex: 'aliases', render: (v: string[]) => v?.join('、') || '-' },
    { title: '分类', dataIndex: 'category', render: (v: string) => v ? v.split(',').map(x => <Tag key={x}>{x}</Tag>) : '-' },
    { title: '状态', dataIndex: 'active', render: (v: number) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag> },
    { title: '排序', dataIndex: 'sort_no' },
    { title: '操作', render: (_: unknown, dept: DeptInfo) => <Space>
      <Button size="small" icon={<EditOutlined />} onClick={() => { setEditingDept(dept); deptForm.setFieldsValue({ ...dept, aliases: dept.aliases.join(','), active: Boolean(dept.active), category: dept.category ? dept.category.split(',') : [] }); setDeptOpen(true) }}>编辑</Button>
      <Popconfirm title="确认删除该科室？有账号绑定时系统会拒绝。" onConfirm={async () => { try { await deleteDept(dept.id); message.success('科室已删除'); await loadDictionaries() } catch (err) { message.error(errorText(err)) } }}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>
    </Space> },
  ]

  return <Card>
    <Title level={4} style={{ marginTop: 0 }}>用户管理</Title>
    <Tabs items={[
      { key: 'users', label: '登录账号', children: <>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input.Search allowClear placeholder="用户名 / 姓名" style={{ width: 240 }} onSearch={q => { setPage(1); setFilters(v => ({ ...v, q })) }} />
          <Select allowClear placeholder="角色" style={{ width: 180 }} options={roles.map(r => ({ value: r.role, label: `${r.role_cn}（${r.count}）` }))} onChange={role => { setPage(1); setFilters(v => ({ ...v, role: role || '' })) }} />
          <Select allowClear placeholder="状态" style={{ width: 120 }} options={[{ value: '1', label: '启用' }, { value: '0', label: '停用' }]} onChange={active => { setPage(1); setFilters(v => ({ ...v, active: active || '' })) }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openUser()}>新建账号</Button>
          <Button icon={<TeamOutlined />} onClick={() => void previewBulk()}>批量建科室账号</Button>
        </Space>
        <Table rowKey="id" loading={loading} columns={userColumns} dataSource={users} scroll={{ x: 1100 }} pagination={{ current: page, pageSize: size, total, showSizeChanger: true, onChange: (p, s) => { setPage(p); setSize(s) } }} />
      </> },
      { key: 'depts', label: '科室字典', children: <>
        <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 16 }} onClick={() => { setEditingDept(null); deptForm.resetFields(); deptForm.setFieldsValue({ active: true, sort_no: 0, category: [] }); setDeptOpen(true) }}>新增科室</Button>
        <Table rowKey="id" columns={deptColumns} dataSource={depts} pagination={false} />
      </> },
    ]} />

    <Drawer title={editing ? `编辑账号：${editing.username}` : '新建账号'} open={userOpen} width={480} onClose={() => setUserOpen(false)} extra={<Button type="primary" loading={saving} onClick={() => void saveUser()}>保存</Button>} destroyOnHidden>
      <Form form={userForm} layout="vertical">
        {!editing && <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}><Input /></Form.Item>}
        <Form.Item name="display_name" label="姓名" extra="姓名会被项目、推送和待办按字符串引用，修改前请确认。" rules={[{ required: true, message: '请输入姓名' }]}><Input /></Form.Item>
        <Form.Item name="role" label="角色" rules={[{ required: true }]}><Select options={roles.map(r => ({ value: r.role, label: r.role_cn }))} /></Form.Item>
        {['dept', 'dept_manage', 'dept_demand'].includes(watchedRole) && <Form.Item name="dept_code" label="所属科室" rules={[{ required: true, message: '请选择科室' }]}><Select showSearch optionFilterProp="label" options={depts.filter(d => d.active).map(d => ({ value: d.code, label: `${d.name}（${d.code}）` }))} /></Form.Item>}
        {watchedRole === 'agency' && <Form.Item name="agency_code" label="所属代理机构" rules={[{ required: true, message: '请选择代理机构' }]}><Select showSearch optionFilterProp="label" options={agencies.filter(a => a.active).map(a => ({ value: a.code, label: a.name }))} /></Form.Item>}
        {!editing && <Form.Item name="password" label="初始密码" extra="不填则自动生成 12 位随机密码，只展示一次。"><Input.Password /></Form.Item>}
        {editing && <Form.Item name="active" label="启用状态" valuePropName="checked"><Switch /></Form.Item>}
      </Form>
    </Drawer>

    <Drawer title={`${auditUser} 的变更历史`} open={auditOpen} width={600} onClose={() => setAuditOpen(false)}>
      <Table rowKey="id" pagination={false} dataSource={audits} columns={[
        { title: '时间', dataIndex: 'created_at', width: 160 }, { title: '操作人', render: (_: unknown, row: AuditInfo) => row.actor_name || row.actor },
        { title: '动作', dataIndex: 'action', render: (v: string) => ACTION_CN[v] || v },
        { title: '变化', dataIndex: 'detail', render: (v: Record<string, unknown>) => <Text code>{JSON.stringify(v)}</Text> },
      ]} />
    </Drawer>

    <Modal title={editingDept ? '编辑科室' : '新增科室'} open={deptOpen} onCancel={() => setDeptOpen(false)} onOk={() => void saveDept()} okText="保存">
      <Form form={deptForm} layout="vertical">
        <Form.Item name="code" label="编码" rules={[{ required: true }, { pattern: /^[A-Z]+$/, message: '只能使用大写字母' }]}><Input placeholder="如 CWK" /></Form.Item>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="aliases" label="别名" extra="多个别名用逗号分隔"><Input /></Form.Item>
        <Form.Item name="category" label="分类"><Select mode="multiple" options={CATEGORY_OPTIONS} /></Form.Item>
        <Form.Item name="dept_type" label="科室类型"><Select allowClear options={[{ value: '行后', label: '行后' }, { value: '临床医技', label: '临床医技' }]} /></Form.Item>
        <Form.Item name="head_name" label="科室主要负责人"><Input /></Form.Item>
        <Form.Item name="sort_no" label="排序"><InputNumber style={{ width: '100%' }} /></Form.Item>
        <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        <Form.Item name="active" label="启用状态" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Modal>
  </Card>
}
