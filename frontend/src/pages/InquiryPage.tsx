import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Table, Button, Drawer, Form, Input, Select, Radio,
  Card, Space, Tag, Tabs, App, Typography,
  Modal, InputNumber, DatePicker, Divider, Alert, Checkbox, Tooltip,
} from 'antd'
import type { RadioChangeEvent } from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined,
  SaveOutlined, DownloadOutlined, SendOutlined, MessageOutlined,
  PaperClipOutlined, FolderOpenOutlined, UploadOutlined, QuestionCircleOutlined,
  EyeOutlined, SyncOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import ProjectListToolbar, { useProjectListFilter, type ListFilterAccessors } from '../components/ProjectListToolbar'

// 新建函件时暂存的供应商行（还没有函件 id，先存本地）
type DraftSupplier = { key: number; supplier_name: string; contact_name: string; contact_phone: string; email: string }

// 立项方式 → 函件类型（待办卡片进建函抽屉时预选）
const TYPE_OF_METHOD: Record<string, string> = {
  院内询价: '询价', 院内议价: '议价', 医用耗材紧急采购: '紧急采购',
}

// 「待办」页签里混着两种事项：①还没建函的项目（虚拟卡片）②已建但还没发出的函件。
// 经办人要的是"我还有哪几件事没办"，不是"系统里有哪几封函"。
type TodoProject = { __todo: true; project: Project }
type ListRow = InquiryLetter | TodoProject
const isTodo = (r: ListRow): r is TodoProject => (r as TodoProject).__todo === true

const ROW_ACCESSORS: ListFilterAccessors<ListRow> = {
  searchText: r => isTodo(r)
    ? [r.project.display_name || r.project.name, r.project.number]
    : [r.title, r.project_name, r.project_number],
  createdAt: r => isTodo(r) ? r.project.created_at : r.created_at,
  number: r => isTodo(r) ? (r.project.number || '') : r.project_number,
  method: r => isTodo(r) ? (TYPE_OF_METHOD[r.project.method] || '') : r.type,
}
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import {
  listInquiries, createInquiry, updateInquiry, deleteInquiry,
  downloadWordUrl, previewWordUrl,
  listSuppliers, addSupplier, updateSupplier, deleteSupplier, sendEmailToSupplier,
  sendAllToSuppliers, getReplies,
  listAttachments, uploadAttachment, deleteAttachment, attachFromTemplate,
  attachmentDownloadUrl, attachmentPreviewUrl,
  listTemplates, uploadTemplate, updateTemplate, deleteTemplate, templatePreviewUrl,
  type InquiryLetter, type InquirySupplier, type InquiryAttachment, type InquiryTemplate,
  type RepliesData,
} from '../services/inquiry'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'
import { getProjects, type Project } from '../services/project'
import { useAuth } from '../hooks/useAuth'

const { TextArea } = Input
const { Text } = Typography

// ── 截止日期：从今天起顺延 N 个工作日（跳过周末）──────────────
function addWorkingDays(start: dayjs.Dayjs, days: number): dayjs.Dayjs {
  let d = start
  let added = 0
  while (added < days) {
    d = d.add(1, 'day')
    const wd = d.day()           // 0=周日 6=周六
    if (wd !== 0 && wd !== 6) added++
  }
  return d
}

// ── 状态颜色 ──────────────────────────────────────────────────
const statusColor: Record<string, string> = {
  待办: 'orange',
  进行中: 'blue',
  已完成: 'green',
}

// 第几轮 → 中文序数（第二次/第三次…）
const CN_ORD = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const cnOrd = (n: number) => CN_ORD[n] || String(n)

// ── 格式化金额 ────────────────────────────────────────────────
function fmtAmount(v: number | null): string {
  if (v == null) return '—'
  return `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
}

// ── 供应商管理子组件 ──────────────────────────────────────────
interface SupplierPanelProps {
  inquiryId: number | null
  letterStatus: string
  letterType: string
  onSupplierChange: () => void
}

function SupplierPanel({ inquiryId, letterStatus, letterType, onSupplierChange }: SupplierPanelProps) {
  const { message, modal } = App.useApp()
  const { user } = useAuth()
  const [suppliers, setSuppliers] = useState<InquirySupplier[]>([])
  const [addForm] = Form.useForm()
  const [addVisible, setAddVisible] = useState(false)
  const [addLoading, setAddLoading] = useState(false)
  const [sendingId, setSendingId] = useState<number | null>(null)
  const [replyModal, setReplyModal] = useState(false)
  const [replyTarget, setReplyTarget] = useState<InquirySupplier | null>(null)
  const [replyForm] = Form.useForm()
  const [replySaving, setReplySaving] = useState(false)
  // 邮箱回复跟踪
  const [reps, setReps] = useState<RepliesData | null>(null)
  const [repLoading, setRepLoading] = useState(false)
  const loadReplies = useCallback(async () => {
    if (!inquiryId) { message.warning('请先保存函件'); return }
    setRepLoading(true)
    try {
      const res = await getReplies(inquiryId)
      setReps(res.data.data)
      message.success(`已拉取：${res.data.data.replied}/${res.data.data.sent} 家回复`)
    } catch (e: unknown) {
      const m = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '拉取回复失败')
    } finally { setRepLoading(false) }
  }, [inquiryId, message])
  const repMap = new Map((reps?.suppliers || []).map(s => [s.id, s]))

  const load = useCallback(async () => {
    if (!inquiryId) { setSuppliers([]); return }
    try {
      const res = await listSuppliers(inquiryId)
      setSuppliers(res.data.data || [])
    } catch { /* ignore */ }
  }, [inquiryId])

  useEffect(() => { load() }, [load])

  const handleAdd = async () => {
    if (!inquiryId) { message.warning('请先保存函件后再添加供应商'); return }
    let values: Record<string, unknown>
    try { values = await addForm.validateFields() } catch { return }
    setAddLoading(true)
    try {
      await addSupplier(inquiryId, values as Partial<InquirySupplier>)
      message.success('已添加')
      addForm.resetFields()
      setAddVisible(false)
      load()
      onSupplierChange()
    } catch { message.error('添加失败') }
    finally { setAddLoading(false) }
  }

  const handleDelete = (sup: InquirySupplier) => {
    modal.confirm({
      title: '删除供应商',
      content: `确认删除「${sup.supplier_name || sup.email || '该供应商'}」？`,
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteSupplier(inquiryId!, sup.id)
          message.success('已删除')
          load()
          onSupplierChange()
        } catch (err: unknown) {
          const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
          message.error(errMsg || '删除失败')
        }
      },
    })
  }

  const emailCount = suppliers.filter(s => s.email && s.email.trim()).length
  const xunjiaBlocked = letterType === '询价' && emailCount < 3

  const handleSend = async (sup: InquirySupplier) => {
    if (!sup.email) {
      message.error('请先填写该供应商的邮箱地址')
      return
    }
    if (xunjiaBlocked) {
      message.error(`询价函要求至少 3 家供应商填写邮箱地址，当前仅 ${emailCount} 家，请先补充`)
      return
    }
    setSendingId(sup.id)
    try {
      const res = await sendEmailToSupplier(inquiryId!, sup.id)
      message.success(res.data.message || '邮件已发送')
      load()
      onSupplierChange()
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '发送失败，请检查邮件配置')
    } finally {
      setSendingId(null)
    }
  }

  const openReply = (sup: InquirySupplier) => {
    setReplyTarget(sup)
    replyForm.setFieldsValue({
      quote_amount: sup.quote_amount,
      quote_date: sup.quote_date,
      quote_note: sup.quote_note,
      is_selected: sup.is_selected,
    })
    setReplyModal(true)
  }

  const handleSaveReply = async () => {
    if (!replyTarget || !inquiryId) return
    let values: Record<string, unknown>
    try { values = await replyForm.validateFields() } catch { return }
    setReplySaving(true)
    try {
      await updateSupplier(inquiryId, replyTarget.id, values as Partial<InquirySupplier>)
      message.success('已记录')
      setReplyModal(false)
      load()
      onSupplierChange()
    } catch { message.error('保存失败') }
    finally { setReplySaving(false) }
  }

  const cols: ColumnsType<InquirySupplier> = [
    {
      title: '供应商名称', dataIndex: 'supplier_name', width: 160, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">待回函确认</Text>,
    },
    { title: '联系人',    dataIndex: 'contact_name',  width: 80  },
    { title: '电话',      dataIndex: 'contact_phone', width: 120 },
    {
      title: '邮箱', dataIndex: 'email', ellipsis: true,
      render: (v: string) => v || <Text type="secondary">未填写</Text>,
    },
    {
      title: '发送状态', key: 'sent', width: 160,
      render: (_: unknown, r: InquirySupplier) => r.sent_at ? (
        <Space direction="vertical" size={0}>
          <Tag color="success">已发送</Tag>
          <Text type="secondary" style={{ fontSize: 11 }}>{r.sent_at.replace('T', ' ').slice(0, 16)}</Text>
        </Space>
      ) : <Tag>未发送</Tag>,
    },
    {
      title: '邮箱回复', key: 'reply', width: 130,
      render: (_: unknown, r: InquirySupplier) => {
        const rp = repMap.get(r.id)
        if (!reps) return <Text type="secondary">—</Text>
        if (!rp?.replied) return <Tag>未回复</Tag>
        return (
          <Tooltip title={`${rp.reply_subject || ''}（${rp.reply_from || ''} ${(rp.reply_date || '').slice(0, 25)}）`}>
            <Tag color={rp.reply_confident ? 'success' : 'warning'}>
              {rp.reply_confident ? '已回复' : '已回复(待确认)'}
            </Tag>
          </Tooltip>
        )
      },
    },
    {
      title: '报价金额', key: 'quote', width: 120,
      render: (_: unknown, r: InquirySupplier) => r.quote_amount != null
        ? <span style={{ color: '#1677ff', fontWeight: 500 }}>{fmtAmount(r.quote_amount)}</span>
        : <Text type="secondary">待回复</Text>,
    },
    {
      title: '操作', key: 'actions', width: 200,
      render: (_: unknown, r: InquirySupplier) => (
        <Space size={4} wrap>
          {!r.sent_at && (
            <>
              <Button
                size="small" type="primary" icon={<SendOutlined />}
                loading={sendingId === r.id}
                disabled={!r.email || xunjiaBlocked}
                title={xunjiaBlocked ? `询价需3家邮箱，当前${emailCount}家` : (!r.email ? '请填写邮箱' : '')}
                onClick={() => handleSend(r)}
              >
                发送邮件
              </Button>
              <Button
                size="small" danger icon={<DeleteOutlined />}
                onClick={() => handleDelete(r)}
              />
            </>
          )}
          {r.sent_at && (
            <Button
              size="small" icon={<MessageOutlined />}
              onClick={() => openReply(r)}
            >
              记录回复
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      {/* 询价强制3家提示 */}
      {letterType === '询价' && (
        xunjiaBlocked ? (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 8 }}
            message={`询价函要求至少 3 家供应商填写邮箱，当前 ${emailCount} 家（共 ${suppliers.length} 家）`}
            description="请为所有供应商填写邮箱地址，填满 3 家后方可发送邮件"
          />
        ) : (
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 8 }}
            message={`询价条件已满足：${emailCount} 家供应商已填写邮箱`}
          />
        )
      )}

      {/* 邮箱回复跟踪 */}
      {inquiryId && (
        <div style={{ marginBottom: 8 }}>
          <Space wrap>
            <Button size="small" icon={<SyncOutlined />} loading={repLoading}
              onClick={loadReplies}>拉取邮箱回复</Button>
            {reps && (
              <Text>已回复 <strong style={{ color: '#52c41a' }}>{reps.replied}</strong> / {reps.sent} 家</Text>
            )}
          </Space>
          {reps && (
            <Alert type="info" showIcon style={{ marginTop: 6 }}
              message={<span style={{ fontSize: 12 }}>
                供应商回复主题应为：<strong>{reps.reply_format}</strong>
                {reps.unmatched.length > 0 && (
                  <>　|　<span style={{ color: '#fa8c16' }}>
                    另有 {reps.unmatched.length} 封含本项目名但未匹配到供应商的回复（待人工归类）：
                    {reps.unmatched.map((u, i) => (
                      <div key={i} style={{ marginLeft: 8 }}>· {u.subject.slice(0, 50)}（{u.from}）</div>
                    ))}
                  </span></>
                )}
              </span>} />
          )}
        </div>
      )}

      {/* 供应商列表 */}
      <Table
        rowKey="id"
        dataSource={suppliers}
        columns={cols}
        size="small"
        pagination={false}
        scroll={{ x: 1000 }}
        style={{ marginBottom: 8 }}
        locale={{ emptyText: '暂无供应商，请点击下方「添加供应商」' }}
      />

      {/* 添加供应商按钮 */}
      {letterStatus === '待办' || letterStatus === '进行中' ? (
        <div style={{ marginTop: 8 }}>
          {!addVisible ? (
            <Button icon={<PlusOutlined />} size="small" onClick={() => setAddVisible(true)}>
              添加供应商
            </Button>
          ) : (
            <Card size="small" style={{ marginTop: 8 }}>
              <Form form={addForm} layout="inline" size="small">
                <Form.Item name="email" rules={[
                  { required: true, message: '请输入邮箱' },
                  { type: 'email', message: '请输入有效邮箱' },
                ]}>
                  <Input placeholder="邮箱地址（必填）" style={{ width: 220 }} />
                </Form.Item>
                <Form.Item name="supplier_name">
                  <Input placeholder="供应商名称（回函后补填）" style={{ width: 180 }} />
                </Form.Item>
                <Form.Item name="contact_name">
                  <Input placeholder="联系人" style={{ width: 100 }} />
                </Form.Item>
                <Form.Item name="contact_phone">
                  <Input placeholder="联系电话" style={{ width: 130 }} />
                </Form.Item>
                <Form.Item>
                  <Space>
                    <Button type="primary" loading={addLoading} onClick={handleAdd}>确认添加</Button>
                    <Button onClick={() => { setAddVisible(false); addForm.resetFields() }}>取消</Button>
                  </Space>
                </Form.Item>
              </Form>
            </Card>
          )}
        </div>
      ) : null}

      {/* 记录回复 Modal */}
      <Modal
        title={`记录回复 — ${replyTarget?.supplier_name || replyTarget?.email || ''}`}
        open={replyModal}
        onCancel={() => setReplyModal(false)}
        onOk={handleSaveReply}
        confirmLoading={replySaving}
        okText="保存"
        destroyOnClose
      >
        <Form form={replyForm} layout="vertical">
          <Form.Item name="quote_amount" label="报价金额（元）">
            <InputNumber<number>
              style={{ width: '100%' }} min={0} precision={2} step={1000} prefix="¥"
              formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={v => parseFloat((v ?? '').replace(/,/g, '')) || 0}
              placeholder="输入报价金额"
            />
          </Form.Item>
          <Form.Item name="quote_date" label="报价日期">
            <Input placeholder="如：2026-06-01" />
          </Form.Item>
          <Form.Item name="quote_note" label="回复备注">
            <TextArea rows={3} placeholder="供应商回复的备注信息" />
          </Form.Item>
          <Form.Item name="is_selected" label="是否成交">
            <Radio.Group>
              <Radio value={0}>否</Radio>
              <Radio value={1}>是（成交）</Radio>
            </Radio.Group>
          </Form.Item>
        </Form>
      </Modal>

      {/* 抑制 user 未使用 warning */}
      <span style={{ display: 'none' }}>{user?.display_name}</span>
    </div>
  )
}

// ── 附件管理子组件（含模板库）──────────────────────────────────────
interface AttachmentPanelProps {
  inquiryId: number | null
  /** 草稿模式：函件还没建出来（新建抽屉），附件与模板勾选先存在父组件里，保存时一并提交。
   *  给了这个就走草稿模式；不给就是老的编辑模式（直接读写函件的附件）。 */
  draft?: {
    files: File[]
    onFilesChange: (f: File[]) => void
    tmplIds: number[]
    onTmplIdsChange: (ids: number[]) => void
  }
}

function AttachmentPanel({ inquiryId, draft }: AttachmentPanelProps) {
  const { message, modal } = App.useApp()
  const [attachments, setAttachments] = useState<InquiryAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 模板库 modal 状态
  const [tmplModalOpen, setTmplModalOpen] = useState(false)
  const [templates, setTemplates] = useState<InquiryTemplate[]>([])
  const [_tmplLoading, setTmplLoading] = useState(false)
  const [_selTmplIds, _setSelTmplIds] = useState<number[]>([])
  // 草稿模式下勾选状态存在父组件（保存时要用），编辑模式下用本地 state
  const selectedTmplIds = draft ? draft.tmplIds : _selTmplIds
  const setSelectedTmplIds = (upd: number[] | ((p: number[]) => number[])) => {
    const next = typeof upd === 'function' ? (upd as (p: number[]) => number[])(selectedTmplIds) : upd
    if (draft) draft.onTmplIdsChange(next)
    else _setSelTmplIds(next)
  }
  const [addingTmpl, setAddingTmpl] = useState(false)
  // 上传模板
  const tmplFileInputRef = useRef<HTMLInputElement>(null)
  const [tmplUploading, setTmplUploading] = useState(false)
  const [tmplDesc, setTmplDesc] = useState('')
  const [tmplDescEditId, setTmplDescEditId] = useState<number | null>(null)
  const [tmplDescVal, setTmplDescVal] = useState('')

  const load = useCallback(async () => {
    if (!inquiryId) { setAttachments([]); return }
    try {
      const res = await listAttachments(inquiryId)
      setAttachments(res.data.data || [])
    } catch { /* ignore */ }
  }, [inquiryId])

  useEffect(() => { load() }, [load])
  // 草稿模式：进来就拉一次模板库，好在卡片上显示已勾模板的文件名
  useEffect(() => { if (draft) loadTemplates() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const loadTemplates = async () => {
    setTmplLoading(true)
    try {
      const res = await listTemplates()
      setTemplates(res.data.data || [])
    } catch { /* ignore */ }
    finally { setTmplLoading(false) }
  }

  const openTmplModal = () => {
    if (!draft) setSelectedTmplIds([])   // 草稿模式保留已勾的，免得重开弹窗白勾一次
    setTmplDesc('')
    loadTemplates()
    setTmplModalOpen(true)
  }

  // ── 本函件附件上传 ────────────────────────────────────────────
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (draft) {                       // 草稿模式：函件还没建，先存本地，保存时一并上传
      draft.onFilesChange([...draft.files, file])
      message.success(`「${file.name}」已加入，保存函件时一起上传`)
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }
    if (!inquiryId) return
    setUploading(true)
    try {
      await uploadAttachment(inquiryId, file)
      message.success(`「${file.name}」已上传`)
      load()
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '上传失败')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDeleteAtt = (att: InquiryAttachment) => {
    modal.confirm({
      title: '删除附件',
      content: `确认删除「${att.filename}」？该附件将从后续邮件中移除。`,
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteAttachment(inquiryId!, att.id)
          message.success('已删除')
          load()
        } catch { message.error('删除失败') }
      },
    })
  }

  // ── 模板库上传 ────────────────────────────────────────────────
  const handleTmplFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setTmplUploading(true)
    try {
      await uploadTemplate(file, tmplDesc)
      message.success(`「${file.name}」已加入模板库`)
      setTmplDesc('')
      loadTemplates()
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '上传失败')
    } finally {
      setTmplUploading(false)
      if (tmplFileInputRef.current) tmplFileInputRef.current.value = ''
    }
  }

  const handleDeleteTmpl = (tmpl: InquiryTemplate) => {
    modal.confirm({
      title: '删除模板',
      content: `确认从模板库中删除「${tmpl.filename}」？已添加到函件的副本不受影响。`,
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteTemplate(tmpl.id)
          message.success('已删除')
          loadTemplates()
        } catch { message.error('删除失败') }
      },
    })
  }

  const handleSaveTmplDesc = async (tmpl: InquiryTemplate) => {
    try {
      await updateTemplate(tmpl.id, tmplDescVal)
      message.success('已保存')
      setTmplDescEditId(null)
      loadTemplates()
    } catch { message.error('保存失败') }
  }

  // ── 从模板库添加到本函件 ──────────────────────────────────────
  const handleAddFromTemplate = async () => {
    if (selectedTmplIds.length === 0) { message.warning('请先勾选模板'); return }
    setAddingTmpl(true)
    try {
      const res = await attachFromTemplate(inquiryId!, selectedTmplIds)
      message.success(res.data.message)
      setTmplModalOpen(false)
      load()
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '操作失败')
    } finally { setAddingTmpl(false) }
  }

  // 草稿模式下"已附加"的就是本地暂存的文件
  const draftList = draft ? draft.files : []

  return (
    <div>
      {draft && draftList.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {draftList.map((f, i) => (
            <div key={`${f.name}-${i}`} style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
              border: '1px solid #f0f0f0', borderRadius: 6, marginBottom: 6,
            }}>
              <PaperClipOutlined style={{ color: '#1677ff', flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 13 }}>{f.name}</span>
              <Tag color="orange" style={{ marginInlineEnd: 0 }}>待保存</Tag>
              <Button size="small" type="text" danger icon={<DeleteOutlined />}
                onClick={() => draft.onFilesChange(draft.files.filter((_, x) => x !== i))} />
            </div>
          ))}
        </div>
      )}
      {draft && draft.tmplIds.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {templates.filter(t => draft.tmplIds.includes(t.id)).map(t => (
            <Tag key={t.id} color="purple" closable style={{ marginBottom: 4 }}
              onClose={() => draft.onTmplIdsChange(draft.tmplIds.filter(x => x !== t.id))}>
              {t.filename}（模板·待保存）
            </Tag>
          ))}
          {templates.length === 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              已选 {draft.tmplIds.length} 个模板，保存函件时一起添加
            </Text>
          )}
        </div>
      )}

      {/* 已附加文件列表 */}
      {draft ? (
        draftList.length === 0 && draft.tmplIds.length === 0 ? (
          <div style={{ color: '#bbb', fontSize: 12, marginBottom: 8 }}>
            暂无附件，发邮件时仅附带 Word 函件正文
          </div>
        ) : null
      ) : attachments.length === 0 ? (
        <div style={{ color: '#bbb', fontSize: 12, marginBottom: 8 }}>
          暂无附件，发邮件时仅附带 Word 函件正文
        </div>
      ) : (
        <div style={{ marginBottom: 8 }}>
          {attachments.map(att => (
            <div
              key={att.id}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '5px 8px', background: '#f6f8ff',
                borderRadius: 4, marginBottom: 4, border: '1px solid #e8eeff',
              }}
            >
              <PaperClipOutlined style={{ color: '#1677ff', flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 13 }}>{att.filename}</span>
              <Text type="secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                {att.uploaded_by.replace('（模板库）', '')}
                {att.uploaded_by.includes('模板库') && (
                  <Tag style={{ marginLeft: 4, fontSize: 10 }} color="purple">模板</Tag>
                )}
              </Text>
              {isPreviewable(att.filename) && (
                <Button
                  size="small" type="text" icon={<EyeOutlined />}
                  onClick={() => setPreview({ open: true, url: attachmentPreviewUrl(inquiryId!, att.id), name: att.filename })}
                />
              )}
              <Button
                size="small" type="text" icon={<DownloadOutlined />}
                href={attachmentDownloadUrl(inquiryId!, att.id)}
              />
              <Button
                size="small" type="text" danger icon={<DeleteOutlined />}
                onClick={() => handleDeleteAtt(att)}
              />
            </div>
          ))}
        </div>
      )}
      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />

      {/* 操作按钮 */}
      <Space size={8}>
        <input
          ref={fileInputRef}
          type="file"
          style={{ display: 'none' }}
          accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.zip,.rar"
          onChange={handleFileChange}
        />
        <Button
          icon={<UploadOutlined />}
          size="small"
          loading={uploading}
          disabled={!inquiryId}
          onClick={() => fileInputRef.current?.click()}
        >
          上传文件
        </Button>
        <Button
          icon={<FolderOpenOutlined />}
          size="small"
          disabled={!inquiryId}
          onClick={openTmplModal}
        >
          从模板库选择
        </Button>
        <Tooltip title="支持 pdf/doc/docx/xls/xlsx/jpg/png/zip；发邮件时 Word 正文+所有附件一起发送">
          <QuestionCircleOutlined style={{ color: '#aaa', fontSize: 13 }} />
        </Tooltip>
      </Space>

      {/* 模板库 Modal */}
      <Modal
        title={
          <Space>
            <FolderOpenOutlined />
            <span>询价附件模板库</span>
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              统一管理可复用的附件模板，一次上传多次使用
            </Text>
          </Space>
        }
        open={tmplModalOpen}
        onCancel={() => setTmplModalOpen(false)}
        width={640}
        footer={
          inquiryId ? (
            <Space>
              <Button onClick={() => setTmplModalOpen(false)}>关闭</Button>
              <Button
                type="primary"
                loading={addingTmpl}
                disabled={selectedTmplIds.length === 0}
                onClick={handleAddFromTemplate}
              >
                添加所选（{selectedTmplIds.length}）到本函件
              </Button>
            </Space>
          ) : draft ? (
            <Space>
              <Button onClick={() => setTmplModalOpen(false)}>关闭</Button>
              <Button type="primary" onClick={() => setTmplModalOpen(false)}>
                选好了（{selectedTmplIds.length}）· 保存函件时一起添加
              </Button>
            </Space>
          ) : (
            <Button onClick={() => setTmplModalOpen(false)}>关闭</Button>
          )
        }
        destroyOnClose
      >
        {/* 上传新模板区域 */}
        <Card
          size="small"
          style={{ marginBottom: 12, background: '#fafafa' }}
          title={<span style={{ fontSize: 13 }}>上传新模板</span>}
        >
          <Space direction="vertical" style={{ width: '100%' }} size={6}>
            <Input
              size="small"
              placeholder="模板说明（选填，如：资质要求、技术参数表）"
              value={tmplDesc}
              onChange={e => setTmplDesc(e.target.value)}
              style={{ width: '100%' }}
            />
            <input
              ref={tmplFileInputRef}
              type="file"
              style={{ display: 'none' }}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.zip,.rar"
              onChange={handleTmplFileChange}
            />
            <Button
              icon={<UploadOutlined />}
              size="small"
              loading={tmplUploading}
              onClick={() => tmplFileInputRef.current?.click()}
            >
              选择文件并上传到模板库
            </Button>
          </Space>
        </Card>

        {/* 模板列表 */}
        {templates.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#aaa', padding: '24px 0', fontSize: 13 }}>
            模板库为空，请先上传模板文件
          </div>
        ) : (
          <div>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>
              {inquiryId
                ? '勾选要添加到本函件的模板，然后点击「添加所选」'
                : draft
                  ? '勾选要用的模板，保存函件时会自动添加进去'
                  : '（以下为模板库概览）'}
            </div>
            {templates.map(tmpl => (
              <div
                key={tmpl.id}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '7px 10px',
                  background: selectedTmplIds.includes(tmpl.id) ? '#eff6ff' : '#fff',
                  border: `1px solid ${selectedTmplIds.includes(tmpl.id) ? '#bbd4ff' : '#f0f0f0'}`,
                  borderRadius: 6, marginBottom: 6,
                  cursor: (inquiryId || draft) ? 'pointer' : 'default',
                  transition: 'background .15s',
                }}
                onClick={() => {
                  if (!inquiryId && !draft) return
                  setSelectedTmplIds(prev =>
                    prev.includes(tmpl.id) ? prev.filter(i => i !== tmpl.id) : [...prev, tmpl.id]
                  )
                }}
              >
                {(inquiryId || draft) && (
                  <Checkbox
                    checked={selectedTmplIds.includes(tmpl.id)}
                    style={{ marginTop: 2 }}
                    onClick={e => e.stopPropagation()}
                    onChange={() => {
                      setSelectedTmplIds(prev =>
                        prev.includes(tmpl.id) ? prev.filter(i => i !== tmpl.id) : [...prev, tmpl.id]
                      )
                    }}
                  />
                )}
                <PaperClipOutlined style={{ color: '#1677ff', marginTop: 2, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{tmpl.filename}</div>
                  {tmplDescEditId === tmpl.id ? (
                    <Space size={4} style={{ marginTop: 4 }} onClick={e => e.stopPropagation()}>
                      <Input
                        size="small"
                        value={tmplDescVal}
                        onChange={e => setTmplDescVal(e.target.value)}
                        style={{ width: 260 }}
                        autoFocus
                        onPressEnter={() => handleSaveTmplDesc(tmpl)}
                      />
                      <Button size="small" type="primary" onClick={() => handleSaveTmplDesc(tmpl)}>保存</Button>
                      <Button size="small" onClick={() => setTmplDescEditId(null)}>取消</Button>
                    </Space>
                  ) : (
                    <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>
                      {tmpl.description || <span style={{ color: '#ccc' }}>无说明</span>}
                      <Button
                        type="link" size="small" style={{ padding: '0 4px', fontSize: 11 }}
                        onClick={e => {
                          e.stopPropagation()
                          setTmplDescEditId(tmpl.id)
                          setTmplDescVal(tmpl.description)
                        }}
                      >
                        编辑说明
                      </Button>
                    </div>
                  )}
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {tmpl.uploaded_at.slice(0, 16)} · {tmpl.uploaded_by}
                  </Text>
                </div>
                <Button
                  size="small" type="text" icon={<EyeOutlined />}
                  style={{ flexShrink: 0 }}
                  onClick={e => {
                    e.stopPropagation()
                    setPreview({ open: true, url: templatePreviewUrl(tmpl.id), name: tmpl.filename })
                  }}
                />
                <Button
                  size="small" type="text" danger icon={<DeleteOutlined />}
                  style={{ flexShrink: 0 }}
                  onClick={e => { e.stopPropagation(); handleDeleteTmpl(tmpl) }}
                />
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// 主页面
// ─────────────────────────────────────────────────────────────────

export default function InquiryPage() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [letters, setLetters] = useState<InquiryLetter[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [tabStatus, setTabStatus] = useState<'待办' | '进行中' | '已完成'>('待办')

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editId, setEditId]         = useState<number | null>(null)
  // 新建态的暂存：这两块原本要等函件 id 才能操作，现在先存本地，保存时一并提交
  const [draftSuppliers, setDraftSuppliers] = useState<DraftSupplier[]>([])
  const [draftFiles, setDraftFiles]         = useState<File[]>([])
  const [draftTmplIds, setDraftTmplIds]     = useState<number[]>([])   // 新建时勾的模板
  const [saving, setSaving]         = useState(false)
  const [form] = Form.useForm()
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [wordPreview, setWordPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })
  const [sendingAllId, setSendingAllId] = useState<number | null>(null)

  // ── 数据加载 ──────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listInquiries()
      setLetters(res.data.data || [])
    } catch { message.error('加载失败') }
    finally { setLoading(false) }
  }, [message])

  useEffect(() => {
    load()
    getProjects().then(r => setProjects(r.data.data || []))
  }, [load])

  const projectMap = Object.fromEntries(projects.map(p => [p.id, p]))
  const tabLetters = letters.filter(l => l.status === tabStatus)

  // 可立询/议价函的项目：方式∈院内询价/议价/紧急采购，且未处于进行中的采购轮次
  // （无轮次=尚未开始 或 本轮已废标=待开下一轮 才可；已进轮次未废标的排除）
  const eligibleProjects = projects.filter(p =>
    (['院内询价', '院内议价', '医用耗材紧急采购'].includes(p.method) &&
      ((p.current_round ?? 0) === 0 || p.current_stage === 'round_failed')) ||
    p.id === selectedProject?.id,   // 编辑时保留当前记录的项目，避免下拉里消失
  )

  // 待建函的项目＝可立函 且 名下没有未完成的函件（含废标后待开下一轮的情况）
  const todoProjects: TodoProject[] = projects
    .filter(p =>
      ['院内询价', '院内议价', '医用耗材紧急采购'].includes(p.method) &&
      // 已归档/已定标的是办完的历史项目（多为历史导入、本就没有函件），不是待办
      p.status === '立项' &&
      ((p.current_round ?? 0) === 0 || p.current_stage === 'round_failed') &&
      !letters.some(l => l.project_id === p.id && l.status !== '已完成'))
    .map(p => ({ __todo: true as const, project: p }))

  const tabRows: ListRow[] = tabStatus === '待办'
    ? [...todoProjects, ...tabLetters]
    : tabLetters
  const listFilter = useProjectListFilter(tabRows, ROW_ACCESSORS)
  const filtered   = listFilter.filtered

  // ── 打开新建 ──────────────────────────────────────────────────
  const openCreate = (preset?: Project) => {
    setEditId(null)
    setSelectedProject(null)
    setDraftSuppliers([])
    setDraftFiles([])
    setDraftTmplIds([])
    form.resetFields()
    form.setFieldsValue({ type: preset ? (TYPE_OF_METHOD[preset.method] || '询价') : '询价' })
    setDrawerOpen(true)
    // 从待办卡片进来：项目已经定了，直接预选并把标题/细则/截止日期一起带出（同手选流程）
    if (preset) {
      form.setFieldsValue({ project_id: preset.id })
      setTimeout(() => handleProjectChange(preset.id), 0)
    }
  }

  // ── 打开编辑 ──────────────────────────────────────────────────
  const openEdit = (record: InquiryLetter) => {
    setEditId(record.id)
    const proj = projectMap[record.project_id] || null
    setSelectedProject(proj)
    form.resetFields()
    form.setFieldsValue({
      project_id:   record.project_id,
      type:         record.type,
      title:        record.title,
      detail:       record.detail,
      requirements: record.requirements,
      deadline:     record.deadline ? dayjs(record.deadline) : null,
      notes:        record.notes,
    })
    setDrawerOpen(true)
  }

  // ── 项目选择 ──────────────────────────────────────────────────
  const handleProjectChange = (pid: number) => {
    const proj = projectMap[pid] || null
    setSelectedProject(proj)
    if (!proj) return
    const letterType = form.getFieldValue('type') || '询价'
    const currentTitle = form.getFieldValue('title')
    if (!currentTitle) {
      form.setFieldsValue({ title: `${proj.display_name || proj.name}${letterType}邀请函` })
    }
    // 项目细则和限价：默认取立项内容，未填时带出
    if (!form.getFieldValue('detail') && proj.content) {
      form.setFieldsValue({ detail: proj.content })
    }
    // 截止日期：未选时自动填为 5 个工作日后
    if (!form.getFieldValue('deadline')) {
      form.setFieldsValue({ deadline: addWorkingDays(dayjs(), 5) })
    }
  }

  const handleTypeChange = (e: RadioChangeEvent) => {
    const letterType = e.target.value as string
    const proj = selectedProject
    const currentTitle = form.getFieldValue('title')
    if (proj && !currentTitle) {
      form.setFieldsValue({ title: `${proj.name}${letterType}邀请函` })
    }
  }

  // ── 保存（存为待办件）──────────────────────────────────────────
  const handleSave = async () => {
    let values: Record<string, unknown>
    try { values = await form.validateFields() } catch { return }

    // 处理 DatePicker 值
    if (values.deadline && typeof values.deadline === 'object' && 'format' in (values.deadline as object)) {
      values.deadline = (values.deadline as { format: (f: string) => string }).format('YYYY-MM-DD')
    }

    setSaving(true)
    try {
      if (editId) {
        await updateInquiry(editId, values as Partial<InquiryLetter>)
        message.success('保存成功')
      } else {
        const res = await createInquiry({ ...values, created_by: user?.display_name } as Partial<InquiryLetter>)
        const newId = res.data.data.id
        // 一步到位：把新建时录的供应商与附件补提交上去（失败只提示、不回滚函件本身）
        const rows = draftSuppliers.filter(d => (d.supplier_name || '').trim())
        let okSup = 0, okFile = 0
        for (const d of rows) {
          try {
            await addSupplier(newId, {
              supplier_name: d.supplier_name.trim(),
              contact_name: d.contact_name.trim(),
              contact_phone: d.contact_phone.trim(),
              email: d.email.trim(),
            })
            okSup += 1
          } catch { /* 单条失败不影响其余 */ }
        }
        for (const f of draftFiles) {
          try { await uploadAttachment(newId, f); okFile += 1 } catch { /* 同上 */ }
        }
        // 模板库勾选的，建函后一次挂上（后端会复制成本函件的附件副本）
        let okTmpl = 0
        if (draftTmplIds.length) {
          try { await attachFromTemplate(newId, draftTmplIds); okTmpl = draftTmplIds.length } catch { /* 同上 */ }
        }
        const miss = (rows.length - okSup) + (draftFiles.length - okFile)
          + (draftTmplIds.length - okTmpl)
        message[miss ? 'warning' : 'success'](
          `已建函${okSup ? `，供应商 ${okSup} 家` : ''}${okFile ? `，附件 ${okFile} 个` : ''}` +
          `${okTmpl ? `，模板 ${okTmpl} 个` : ''}` +
          (miss ? `（有 ${miss} 项没提交上去，请在下方检查）` : ''))
        // 留在抽屉里转为编辑态：可以接着一键发送，不用再去列表里翻这封函
        setEditId(newId)
        setDraftSuppliers([])
        setDraftFiles([])
        setDraftTmplIds([])
        await load()
        setSaving(false)
        return
      }
      setDrawerOpen(false)
      load()
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '保存失败')
    } finally { setSaving(false) }
  }

  // ── 删除 ──────────────────────────────────────────────────────
  const handleDelete = (record: InquiryLetter) => {
    modal.confirm({
      title: '删除确认',
      content: `确认删除「${record.title}」？`,
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteInquiry(record.id)
          message.success('已删除')
          load()
        } catch (err: unknown) {
          const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
          message.error(errMsg || '删除失败')
        }
      },
    })
  }

  // ── 截止日期是否已过（过了才能进入 8.1 询议价评审）────────────
  const deadlinePassed = (record: InquiryLetter) =>
    !!record.deadline && dayjs().format('YYYY-MM-DD') >= record.deadline

  // ── 下载 Word ────────────────────────────────────────────────
  const handleDownloadWord = (record: InquiryLetter) => {
    window.open(downloadWordUrl(record.id), '_blank')
  }

  // ── 一键发送（操作栏，发给所有已填邮箱且未发送的供应商）─────────
  const handleSendAll = (record: InquiryLetter) => {
    const pending = record.supplier_count - record.sent_count
    modal.confirm({
      title: '一键发送邮件',
      content: record.type === '询价'
        ? `将把《${record.title || record.type + '邀请函'}》正文及附件发送给所有已填邮箱且未发送的供应商（待发约 ${pending} 家）。询价函要求至少 3 家填写邮箱，确认发送？`
        : `将把《${record.title || record.type + '邀请函'}》正文及附件发送给所有已填邮箱且未发送的供应商（待发约 ${pending} 家），确认发送？`,
      okText: '确认发送',
      onOk: async () => {
        setSendingAllId(record.id)
        try {
          const res = await sendAllToSuppliers(record.id)
          const { sent = [], failed = [] } = res.data
          if (failed.length > 0) {
            message.warning(res.data.message || `成功 ${sent.length} 家，失败 ${failed.length} 家`)
          } else {
            message.success(res.data.message || `已发送 ${sent.length} 家`)
          }
          load()
        } catch (err: unknown) {
          const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
          message.error(errMsg || '发送失败，请检查供应商邮箱与邮件配置')
        } finally {
          setSendingAllId(null)
        }
      },
    })
  }

  // ── 表格列 ───────────────────────────────────────────────────
  const ACCENT_BY_STATUS: Record<string, string> = { 已完成: '#34a853', 进行中: '#1a73e8', 待办: '#f9ab00' }
  const letterToCard = (r: InquiryLetter): RecordCardData => ({
    key: r.id,
    accent: ACCENT_BY_STATUS[r.status] || '#1a73e8',
    title: r.title || `${r.type}邀请函`,
    onTitleClick: () => setWordPreview({ open: true, url: previewWordUrl(r.id), name: `${r.title || r.type + '邀请函'}.docx` }),
    subtitle: r.project_name || '—',
    statusText: r.status,
    statusColor: statusColor[r.status] || 'default',
    tags: (
      <Space size={4}>
        <Tag color={r.type === '询价' ? 'blue' : r.type === '紧急采购' ? 'red' : 'orange'} style={{ marginInlineEnd: 0 }}>
          {r.type}
        </Tag>
        {r.round > 1 && (
          <Tag color="purple" style={{ marginInlineEnd: 0 }}>第{cnOrd(r.round)}次</Tag>
        )}
      </Space>
    ),
    fields: [
      { label: '截止', value: r.deadline },
      { label: '供应商', value: `${r.supplier_count} 家${r.sent_count > 0 ? ` · 已发${r.sent_count}` : ''}` },
      { label: '创建', value: r.created_at ? r.created_at.replace('T', ' ').slice(0, 16) : '' },
    ],
    actions: (
      <>
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>
          {r.status === '已完成' ? '查看' : '编辑'}
        </Button>
        <Button size="small" icon={<EyeOutlined />}
          onClick={() => setWordPreview({ open: true, url: previewWordUrl(r.id), name: `${r.title || r.type + '邀请函'}.docx` })}>
          预览
        </Button>
        <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownloadWord(r)}>Word</Button>
        {r.status !== '已完成' && (() => {
          const allSent = r.supplier_count > 0 && r.sent_count >= r.supplier_count
          const noSup = r.supplier_count === 0
          const disabled = noSup || allSent
          const tip = noSup
            ? '请先在「编辑」中添加供应商并填写邮箱'
            : allSent ? '所有供应商均已发送' : '把函件正文+附件群发给所有已填邮箱且未发送的供应商'
          return (
            <Tooltip title={tip}>
              <Button size="small" type="primary" icon={<SendOutlined />}
                loading={sendingAllId === r.id} disabled={disabled} onClick={() => handleSendAll(r)}>
                一键发送
              </Button>
            </Tooltip>
          )
        })()}
        {r.status === '进行中' && (
          <Tooltip title={deadlinePassed(r)
            ? '截止日期已过，可开始资格性/符合性审查并出评定标报告'
            : `递交截止日期 ${r.deadline || '未填写'} 未到，截止后方可评审`}>
            <Button size="small" type="primary" ghost icon={<CheckCircleOutlined />}
              disabled={!deadlinePassed(r)} onClick={() => navigate(`/inquiry-review?inquiry=${r.id}`)}>
              评审
            </Button>
          </Tooltip>
        )}
        {r.status === '已完成' && (
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => navigate(`/inquiry-review?inquiry=${r.id}`)}>
            评审记录
          </Button>
        )}
        {r.status === '待办' && (
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)} />
        )}
      </>
    ),
  })

  // 待建函项目的卡片：一眼看出"这个项目还没发函"，按钮直接进建函抽屉
  const todoToCard = (t: TodoProject): RecordCardData => {
    const p = t.project
    const type = TYPE_OF_METHOD[p.method] || '询价'
    return {
      key: `todo-${p.id}`,
      accent: '#f9ab00',
      title: p.display_name || p.name,
      subtitle: p.number || '—',
      statusText: '待建函',
      statusColor: 'orange',
      tags: (
        <Space size={4}>
          <Tag color={type === '询价' ? 'blue' : type === '紧急采购' ? 'red' : 'orange'}
            style={{ marginInlineEnd: 0 }}>{type}</Tag>
          <Tag style={{ marginInlineEnd: 0 }}>{p.method}</Tag>
        </Space>
      ),
      fields: [
        { label: '立项', value: p.created_at ? p.created_at.replace('T', ' ').slice(0, 16) : '' },
        { label: '金额', value: p.amount ? `${p.amount} 元` : '按单价据实结算' },
        { label: '经办人', value: p.officer || '' },
      ],
      actions: (
        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => openCreate(p)}>
          建{type}函
        </Button>
      ),
    }
  }

  const rowToCard = (r: ListRow): RecordCardData =>
    isTodo(r) ? todoToCard(r) : letterToCard(r)

  // 统计各状态数量（待办＝待建函的项目 + 已建但没发出的函件）
  const countOf = (s: string) =>
    letters.filter(l => l.status === s).length + (s === '待办' ? todoProjects.length : 0)

  return (
    <Card
      title={<span style={{ fontWeight: 700, fontSize: 16 }}>询/议价函、紧急采购管理</span>}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreate()}>
          新建函件
        </Button>
      }
    >
      <Tabs
        activeKey={tabStatus}
        onChange={k => setTabStatus(k as '待办' | '进行中' | '已完成')}
        items={[
          { key: '待办',  label: <span>待办 <Tag color="orange">{countOf('待办')}</Tag></span> },
          { key: '进行中', label: <span>进行中 <Tag color="blue">{countOf('进行中')}</Tag></span> },
          { key: '已完成', label: <span>已完成 <Tag color="green">{countOf('已完成')}</Tag></span> },
        ]}
      />

      <div style={{ marginBottom: 12 }}>
        <ProjectListToolbar f={listFilter} placeholder="搜索函件标题 / 项目名称 / 编号" />
      </div>
      <RecordCards dataSource={filtered} loading={loading}
        emptyText={tabStatus === '待办' ? '没有待办事项（立了项还没建函的项目会自动出现在这里）' : '暂无函件'}
        toCard={rowToCard} />

      {/* ══ 新建/编辑 Drawer ═══════════════════════════════════════ */}
      <Drawer
        title={editId ? '编辑函件' : '新建函件'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={700}
        destroyOnClose
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button
              icon={<EyeOutlined />}
              onClick={() => {
                if (!editId) return
                const r = letters.find(l => l.id === editId)!
                setWordPreview({ open: true, url: previewWordUrl(editId), name: `${r.title || r.type + '邀请函'}.docx` })
              }}
              disabled={!editId}
            >
              预览
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => editId && handleDownloadWord(letters.find(l => l.id === editId)!)}
              disabled={!editId}
            >
              下载 Word
            </Button>
            <Button
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
              type="primary"
              disabled={editId != null && letters.find(l => l.id === editId)?.status === '已完成'}
            >
              保存
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">

          {/* ── 基本信息 ── */}
          <Card title="基本信息" size="small" style={{ marginBottom: 16 }}>
            <Form.Item
              name="project_id"
              label="所属项目"
              rules={[{ required: true, message: '请选择项目' }]}
            >
              <Select
                showSearch
                placeholder="请选择项目（支持搜索）"
                onChange={handleProjectChange}
                filterOption={(input, option) =>
                  (option?.label as string ?? '').toLowerCase().includes(input.toLowerCase())
                }
                options={eligibleProjects.map(p => ({
                  value: p.id,
                  label: `${p.number ? p.number + ' — ' : ''}${p.display_name || p.name}`,
                }))}
              />
            </Form.Item>

            <Form.Item name="type" label="函件类型">
              <Radio.Group onChange={handleTypeChange}>
                <Radio value="询价">
                  询价
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>（3家及以上供应商）</Text>
                </Radio>
                <Radio value="议价">
                  议价
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>（1-2家供应商）</Text>
                </Radio>
                <Radio value="紧急采购">
                  紧急采购
                  <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>（1家及以上，按院内议价）</Text>
                </Radio>
              </Radio.Group>
            </Form.Item>

            <Form.Item label="项目编号">
              <Input
                value={selectedProject?.number || ''}
                readOnly
                disabled
                placeholder="选择项目后自动带出"
              />
              <div style={{ marginTop: 2, color: '#aaa', fontSize: 11 }}>
                取自立项编号，自动填入邀请函，无需手填
              </div>
            </Form.Item>

            <Form.Item name="title" label="函件标题">
              <Input placeholder="如：[项目名称]询价邀请函" />
            </Form.Item>

            <Form.Item
              name="deadline"
              label="截止回复日期"
              extra="选择项目后自动填为 5 个工作日后，可按需修改"
            >
              <DatePicker
                style={{ width: '100%' }}
                placeholder="请选择截止日期"
                format="YYYY-MM-DD"
              />
            </Form.Item>
          </Card>

          {/* ── 邀请函正文（公告体例） ── */}
          <Card title="邀请函正文" size="small" style={{ marginBottom: 16 }}>
            <Form.Item
              name="detail"
              label="项目细则和限价"
              extra="默认取立项的采购内容与限价，可手动编辑"
            >
              <TextArea
                rows={6}
                placeholder="如：包1：××，最高单价限价××元；包2：……"
                style={{ fontFamily: '微软雅黑, sans-serif', fontSize: 13 }}
              />
            </Form.Item>
            <Form.Item
              name="requirements"
              label="相关要求"
              extra="技术要求、商务要求、资质要求等，由经办人填写"
            >
              <TextArea
                rows={5}
                placeholder="请填写技术要求、商务要求、所需资质等"
                style={{ fontFamily: '微软雅黑, sans-serif', fontSize: 13 }}
              />
            </Form.Item>
            <div style={{ color: '#aaa', fontSize: 11 }}>
              项目名称、项目编号、收件邮箱、联系人、落款日期由系统按样板自动生成
            </div>
          </Card>

          {/* ── 附件（仅编辑模式） ── */}
          {editId && (
            <Card
              title={
                <Space>
                  <PaperClipOutlined />
                  <span>邮件附件</span>
                  <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                    发邮件时自动带上，所有收件人共享同一批附件
                  </Text>
                </Space>
              }
              size="small"
              style={{ marginBottom: 16 }}
            >
              <AttachmentPanel inquiryId={editId} />
            </Card>
          )}

          {/* ── 备注 ── */}
          <Card title="备注" size="small" style={{ marginBottom: 16 }}>
            <Form.Item name="notes" noStyle>
              <TextArea rows={3} placeholder="其他备注信息" />
            </Form.Item>
          </Card>

          {/* ── 供应商管理（仅编辑模式） ── */}
          {editId && (
            <Card
              title={
                <Space>
                  <span>供应商管理</span>
                  {(() => {
                    const letter = letters.find(l => l.id === editId)
                    const supCount = letter?.supplier_count ?? 0
                    const sentCount = letter?.sent_count ?? 0
                    return (
                      <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                        共 {supCount} 家，已发送 {sentCount} 家
                      </Text>
                    )
                  })()}
                </Space>
              }
              size="small"
              style={{ marginBottom: 16 }}
            >
              {/* 供应商数量提示 */}
              {(() => {
                const type = form.getFieldValue('type') || '询价'
                if (type === '询价') {
                  return (
                    <div style={{ marginBottom: 8, color: '#fa8c16', fontSize: 12 }}>
                      询价函需至少 3 家供应商
                    </div>
                  )
                }
                if (type === '紧急采购') {
                  return (
                    <div style={{ marginBottom: 8, color: '#cf1322', fontSize: 12 }}>
                      紧急采购按院内议价办理，1 家及以上供应商即可
                    </div>
                  )
                }
                return (
                  <div style={{ marginBottom: 8, color: '#1677ff', fontSize: 12 }}>
                    议价函适用于 1-2 家供应商
                  </div>
                )
              })()}

              <SupplierPanel
                inquiryId={editId}
                letterStatus={letters.find(l => l.id === editId)?.status || '待办'}
                letterType={form.getFieldValue('type') || '询价'}
                onSupplierChange={load}
              />

              {/* 前往评审入口（截止日期后） */}
              {(() => {
                const letter = letters.find(l => l.id === editId)
                if (!letter) return null
                if (letter.status !== '进行中') return null
                const passed = deadlinePassed(letter)
                return (
                  <div style={{ textAlign: 'center', marginTop: 12 }}>
                    <Divider />
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      disabled={!passed}
                      onClick={() => navigate(`/inquiry-review?inquiry=${letter.id}`)}
                    >
                      前往评审
                    </Button>
                    <div style={{ color: '#aaa', fontSize: 12, marginTop: 4 }}>
                      {passed
                        ? '截止日期已过，可进入 8.1 询议价评审：审查供应商资料并出评定标报告'
                        : `递交截止日期 ${letter.deadline || '未填写'} 过后可进入评审`}
                    </div>
                  </div>
                )
              })()}
            </Card>
          )}

          {/* ── 新建态：供应商 + 附件（暂存，保存时一并提交）── */}
          {!editId && (
            <>
              <Card
                title={
                  <Space>
                    <span>供应商</span>
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                      现在填好，保存时一起建；也可以先留空、建完再补
                    </Text>
                  </Space>
                }
                size="small"
                style={{ marginBottom: 16 }}
                extra={
                  <Button size="small" icon={<PlusOutlined />}
                    onClick={() => setDraftSuppliers(rows => [...rows, {
                      key: Date.now() + rows.length,
                      supplier_name: '', contact_name: '', contact_phone: '', email: '',
                    }])}>
                    添加供应商
                  </Button>
                }
              >
                {draftSuppliers.length === 0 ? (
                  <div style={{ color: '#aaa', fontSize: 12 }}>
                    还没添加供应商。询价需 3 家及以上，议价 1-2 家，紧急采购 1 家及以上。
                  </div>
                ) : (
                  <Space direction="vertical" style={{ width: '100%' }} size={8}>
                    {draftSuppliers.map((d, idx) => (
                      <Space.Compact key={d.key} style={{ width: '100%' }}>
                        <Input style={{ width: '32%' }} placeholder="供应商名称"
                          value={d.supplier_name}
                          onChange={e => setDraftSuppliers(rows =>
                            rows.map((r, i) => i === idx ? { ...r, supplier_name: e.target.value } : r))} />
                        <Input style={{ width: '16%' }} placeholder="联系人"
                          value={d.contact_name}
                          onChange={e => setDraftSuppliers(rows =>
                            rows.map((r, i) => i === idx ? { ...r, contact_name: e.target.value } : r))} />
                        <Input style={{ width: '20%' }} placeholder="电话"
                          value={d.contact_phone}
                          onChange={e => setDraftSuppliers(rows =>
                            rows.map((r, i) => i === idx ? { ...r, contact_phone: e.target.value } : r))} />
                        <Input style={{ width: '26%' }} placeholder="邮箱（发邀请函用）"
                          value={d.email}
                          onChange={e => setDraftSuppliers(rows =>
                            rows.map((r, i) => i === idx ? { ...r, email: e.target.value } : r))} />
                        <Button danger icon={<DeleteOutlined />}
                          onClick={() => setDraftSuppliers(rows => rows.filter((_, i) => i !== idx))} />
                      </Space.Compact>
                    ))}
                  </Space>
                )}
              </Card>

              <Card
                title={
                  <Space>
                    <PaperClipOutlined />
                    <span>邮件附件</span>
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                      发邀请函时自动带上
                    </Text>
                  </Space>
                }
                size="small"
                style={{ marginBottom: 16 }}
              >
                {/* 与编辑态同一个面板：上传/预览/删除模板、改说明、勾选，能力完全一致 */}
                <AttachmentPanel
                  inquiryId={null}
                  draft={{
                    files: draftFiles,
                    onFilesChange: setDraftFiles,
                    tmplIds: draftTmplIds,
                    onTmplIdsChange: setDraftTmplIds,
                  }}
                />
              </Card>

              <div style={{ textAlign: 'center', color: '#aaa', fontSize: 12, paddingBottom: 8 }}>
                保存后本抽屉会转为编辑态，可直接一键发送邀请函
              </div>
            </>
          )}
        </Form>
      </Drawer>

      {/* 询/议价函在线预览 */}
      <FilePreviewModal
        open={wordPreview.open}
        url={wordPreview.url}
        filename={wordPreview.name}
        onClose={() => setWordPreview(p => ({ ...p, open: false }))}
      />
    </Card>
  )
}
