/**
 * 顶栏「待办」入口：铃铛图标 + 未读徽标，点开抽屉管理待办。
 * - 手动待办：自建/指派给他人，可完成/重开/编辑/删除
 * - 系统待办（source=system）：按项目阶段自动派给经办人/代理，完成对应事项后自动消除，
 *   不可手动操作，列表里以「系统」标签标识。
 */
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Badge, Button, Drawer, App, Tag, Select, Input, Segmented, Empty,
  Space, Typography, List, Tooltip, DatePicker, Popconfirm, Modal, Form,
} from 'antd'
import {
  BellOutlined, PlusOutlined, CheckOutlined, DeleteOutlined, EditOutlined,
  ReloadOutlined, RollbackOutlined, UserOutlined, RobotOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getInboxSummary, listInboxUsers, listTodos, createTodo, updateTodo, doneTodo,
  reopenTodo, deleteTodo,
  type InboxUser, type Todo,
} from '../services/inbox'

const { TextArea } = Input
const { Paragraph } = Typography

const POLL_MS = 45000
const PRIORITY_COLOR: Record<string, string> = { 普通: 'default', 重要: 'orange', 紧急: 'red' }

// 系统待办事件 → 对应处理页面。点击直达该模块，项目已按阶段筛在该页列表里。
/** 系统待办事件 → 可办理页面。必须与后端 services/system_todos.py 的 _EVENTS 一一对应，
 *  漏一个，那类待办就没有「去处理」按钮，只能靠人自己找菜单。 */
const EVENT_ROUTE: Record<string, string> = {
  // 5.1 采购需求
  demand_confirm:   '/procurement-doc/demand',
  demand_fix:       '/procurement-doc/demand',
  // 5.2 采购文件
  doc_upload:       '/procurement-doc/file',
  doc_confirm:      '/procurement-doc/file',
  doc_fix:          '/procurement-doc/file',
  // 6.1 采购公告
  ann_draft:        '/announcement',
  ann_confirm:      '/announcement',
  ann_fix:          '/announcement',
  // 6.3 更正公告
  corr_confirm:     '/correction',
  corr_fix:         '/correction',
  // 开标
  bid_open:         '/bid',
  bid_fail_confirm: '/bid',
  auth_letter:      '/auth-letter',
  // 8.5 项目评审资料
  review_upload:    '/project-review',
  review_confirm:   '/project-review',
  review_fix:       '/project-review',
  // 9 采购结果
  result_draft:     '/procurement-result',
  result_confirm:   '/procurement-result',
  result_fix:       '/procurement-result',
  result_recheck:   '/procurement-result',
  // 10 合同
  contract:         '/contract',
  contract_draft:   '/contract',
  contract_review:  '/contract',
  contract_fix:     '/contract',
  // 询/议价、紧急采购
  inquiry_letter:   '/inquiry',
  inquiry_review:   '/inquiry-review',
  // 13.4 代理机构考核
  agency_assess:    '/agency-assessment',
}

/** 少数页面用自己的参数名接项目（授权函页读 project_id 直接预填表单），其余统一 focus= 高亮行。 */
const EVENT_PARAM: Record<string, string> = { auth_letter: 'project_id' }

/** 待办对应的可办理页面路径（带项目参数），无则 null。 */
function todoLink(t: Todo): string | null {
  if (t.source === 'system' && t.source_key) {
    const event = t.source_key.split(':')[1] || ''
    const base = EVENT_ROUTE[event]
    if (!base) return null
    if (!t.related_project_id) return base
    return `${base}?${EVENT_PARAM[event] || 'focus'}=${t.related_project_id}`
  }
  return null
}

export default function InboxBell() {
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(0)
  const [users, setUsers] = useState<InboxUser[]>([])

  const loadSummary = useCallback(async () => {
    try { setPending((await getInboxSummary()).data.data.pending_todos) } catch { /* 静默 */ }
  }, [])

  useEffect(() => {
    loadSummary()
    const t = setInterval(loadSummary, POLL_MS)
    return () => clearInterval(t)
  }, [loadSummary])

  useEffect(() => {
    if (open && users.length === 0) {
      listInboxUsers().then(r => setUsers(r.data.data)).catch(() => {})
    }
  }, [open, users.length])

  return (
    <>
      <Tooltip title="待办">
        <Badge count={pending} size="small" offset={[-2, 2]}>
          <Button
            type="text"
            icon={<BellOutlined style={{ fontSize: 18 }} />}
            onClick={() => setOpen(true)}
            style={{ color: '#666', marginRight: 8 }}
          />
        </Badge>
      </Tooltip>

      <Drawer
        title="我的待办"
        placement="right"
        width={460}
        open={open}
        onClose={() => setOpen(false)}
        styles={{ body: { padding: '8px 16px 16px' } }}
      >
        <TodosPanel users={users} active={open} onChanged={loadSummary}
          onClose={() => setOpen(false)} />
      </Drawer>
    </>
  )
}

function TodosPanel({ users, active, onChanged, onClose }: {
  users: InboxUser[]; active: boolean; onChanged: () => void; onClose: () => void
}) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const go = (link: string) => { onClose(); navigate(link) }
  const [filter, setFilter] = useState<'待办' | '已完成' | 'all'>('待办')
  const [rows, setRows] = useState<Todo[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Todo | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listTodos(filter)
      setRows(res.data.data)
    } catch { message.error('加载待办失败') } finally { setLoading(false) }
  }, [filter, message])

  useEffect(() => { if (active) load() }, [active, load])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ priority: '普通', owner: '__me__' })
    setModalOpen(true)
  }
  const openEdit = (t: Todo) => {
    setEditing(t)
    form.setFieldsValue({
      title: t.title, content: t.content, priority: t.priority,
      due_date: t.due_date ? dayjs(t.due_date) : null, owner: t.owner,
    })
    setModalOpen(true)
  }

  const submit = async () => {
    let v: any
    try { v = await form.validateFields() } catch { return }
    const payload: any = {
      title: v.title, content: v.content || '', priority: v.priority,
      due_date: v.due_date ? v.due_date.format('YYYY-MM-DD') : '',
    }
    try {
      if (editing) {
        await updateTodo(editing.id, payload)
        message.success('已更新')
      } else {
        payload.owner = v.owner === '__me__' ? undefined : v.owner
        await createTodo(payload)
        message.success('已创建')
      }
      setModalOpen(false)
      load(); onChanged()
    } catch (e: any) {
      message.error(e.response?.data?.error || '保存失败')
    }
  }

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); message.success(ok); load(); onChanged() }
    catch (e: any) { message.error(e.response?.data?.error || '操作失败') }
  }

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <Segmented
          size="small"
          value={filter}
          onChange={v => setFilter(v as typeof filter)}
          options={[{ label: '待办', value: '待办' }, { label: '已完成', value: '已完成' }, { label: '全部', value: 'all' }]}
        />
        <Space size={4}>
          <Button size="small" icon={<ReloadOutlined />} onClick={load} />
          <Button size="small" type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建</Button>
        </Space>
      </div>

      <List
        loading={loading}
        dataSource={rows}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待办" /> }}
        renderItem={t => {
          const sys = t.source === 'system'
          const link = todoLink(t)
          const canGo = !!link && t.status === '待办'
          const goBtn = canGo
            ? <Tooltip title="前往对应页面办理" key="go">
                <Button size="small" type="link" icon={<ArrowRightOutlined />}
                  onClick={() => go(link!)}>去处理</Button>
              </Tooltip>
            : null
          const actions = sys
            ? (goBtn ? [goBtn] : [])
            : [
                ...(goBtn ? [goBtn] : []),
                t.status === '待办'
                  ? <Tooltip title="标记完成" key="d"><Button size="small" type="text" icon={<CheckOutlined style={{ color: '#52c41a' }} />} onClick={() => act(() => doneTodo(t.id), '已完成')} /></Tooltip>
                  : <Tooltip title="重新打开" key="r"><Button size="small" type="text" icon={<RollbackOutlined />} onClick={() => act(() => reopenTodo(t.id), '已重开')} /></Tooltip>,
                <Button key="e" size="small" type="text" icon={<EditOutlined />} onClick={() => openEdit(t)} />,
                <Popconfirm key="x" title="删除该待办？" onConfirm={() => act(() => deleteTodo(t.id), '已删除')}>
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]
          return (
            <List.Item style={{ padding: '10px 0', alignItems: 'flex-start' }} actions={actions}>
              <List.Item.Meta
                title={
                  <Space size={6} wrap>
                    <Tag color={PRIORITY_COLOR[t.priority]} style={{ marginInlineEnd: 0 }}>{t.priority}</Tag>
                    {sys && <Tag icon={<RobotOutlined />} color="cyan" style={{ marginInlineEnd: 0 }}>系统</Tag>}
                    {canGo
                      ? <a onClick={() => go(link!)}>{t.title}</a>
                      : <span style={{ textDecoration: t.status === '已完成' ? 'line-through' : 'none', color: t.status === '已完成' ? '#aaa' : undefined }}>{t.title}</span>}
                    {t.status === '已完成' && <Tag color="green">已完成</Tag>}
                  </Space>
                }
                description={
                  <div style={{ fontSize: 12 }}>
                    {t.content && <Paragraph style={{ margin: '2px 0', fontSize: 12 }} ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}>{t.content}</Paragraph>}
                    <Space size={10} wrap style={{ color: '#999' }}>
                      {t.due_date && <span>截止 {t.due_date}</span>}
                      <span><UserOutlined /> {t.owner_name}</span>
                      {!sys && t.created_by !== t.owner && <span>由 {t.created_by_name} 指派</span>}
                      {t.related_project_name && <span>项目：{t.related_project_name}</span>}
                    </Space>
                    {sys && t.status === '待办' && (
                      <div style={{ color: '#bbb', marginTop: 2 }}>点「去处理」前往办理，完成后自动消除</div>
                    )}
                  </div>
                }
              />
            </List.Item>
          )
        }}
      />

      <Modal
        title={editing ? '编辑待办' : '新建待办'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={submit}
        okText="保存"
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请填写标题' }]}>
            <Input placeholder="待办事项" maxLength={100} />
          </Form.Item>
          <Form.Item name="content" label="说明">
            <TextArea rows={3} placeholder="详细说明（选填）" />
          </Form.Item>
          <Space style={{ width: '100%' }} size={12}>
            <Form.Item name="priority" label="优先级" style={{ flex: 1, minWidth: 120 }}>
              <Select options={['普通', '重要', '紧急'].map(p => ({ value: p, label: p }))} />
            </Form.Item>
            <Form.Item name="due_date" label="截止日期" style={{ flex: 1, minWidth: 140 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          {!editing && (
            <Form.Item name="owner" label="指派给" tooltip="默认给自己，也可指派给其他同事/代理">
              <Select
                showSearch optionFilterProp="label"
                options={[
                  { value: '__me__', label: '我自己' },
                  ...users.map(u => ({ value: u.username, label: u.display_name })),
                ]}
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  )
}
