import { useEffect, useState, useCallback } from 'react'
import {
  Card, Button, Form, Input, Select, Drawer, Space, Popconfirm,
  App, Tag, Typography, Divider, Descriptions, Alert, Modal,
  Tooltip, Upload, List, Tabs, Badge, DatePicker, Segmented,
} from 'antd'
import dayjs from 'dayjs'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type UploadRequestOption = any
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import PendingOwnerTag from '../components/PendingOwnerTag'
import {
  PlusOutlined, DownloadOutlined, EditOutlined, DeleteOutlined,
  FileWordOutlined, CheckCircleOutlined, SendOutlined, RollbackOutlined,
  SaveOutlined, AppstoreOutlined, UploadOutlined, FileOutlined, StopOutlined,
  SearchOutlined, ClockCircleOutlined, CheckSquareOutlined, HourglassOutlined,
  SortAscendingOutlined, SortDescendingOutlined,
} from '@ant-design/icons'
import axios from 'axios'
import {
  getEligibleProjects, getAnnouncements, createAnnouncement, updateAnnouncement,
  deleteAnnouncement, generateAnnouncementWord, announcementWordUrl,
  submitAnnouncement, confirmAnnouncement, revokeAnnouncement, rejectAnnouncement,
  listFiles, deleteFile, downloadFileUrl, previewFileUrl,
  QUALIFICATIONS_DEFAULT,
} from '../services/announcement'
import type { Announcement, AnnProject, AnnAttachment } from '../services/announcement'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'
import {
  getTemplates, createTemplate, updateTemplate, deleteTemplate,
} from '../services/agencyTemplate'
import type { AgencyTemplate } from '../services/agencyTemplate'
import { useAuth } from '../hooks/useAuth'
import { useFocusTarget, flashRow } from '../hooks/useFocusRow'

const { TextArea } = Input
const { Text } = Typography

// 待确认排最左并默认选中——经办人一进来就看到该自己处理的
type AnnTab = 'toconfirm' | 'rejected' | 'draft' | 'published' | 'opened'

const ROUND_OPTIONS = [
  { value: 1, label: '第一次' },
  { value: 2, label: '第二次' },
  { value: 3, label: '第三次' },
  { value: 4, label: '第四次' },
  { value: 5, label: '第五次' },
]

const STATUS_COLOR: Record<string, string> = {
  草稿: 'default',
  待确认: 'orange',
  已确认: 'green',
}

// ── 解析中文日期时间字符串 ───────────────────────────────────────────
function parseDeadline(s: string): Date | null {
  if (!s) return null
  // 兼容全角冒号 '：' 和半角冒号 ':'
  const m = s.match(/(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})[：:](\d{2})/)
  if (m) {
    return new Date(
      parseInt(m[1]),
      parseInt(m[2]) - 1,
      parseInt(m[3]),
      parseInt(m[4]),
      parseInt(m[5]),
    )
  }
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}

function isDeadlinePassed(deadline: string): boolean {
  const d = parseDeadline(deadline)
  if (!d) return false
  return d.getTime() < Date.now()
}

function getCountdown(deadline: string): { text: string; color: string } {
  const d = parseDeadline(deadline)
  if (!d) return { text: '开标时间未填', color: '#aaa' }
  const diff = d.getTime() - Date.now()
  if (diff <= 0) return { text: '已开标', color: '#ff4d4f' }

  const totalMins = Math.floor(diff / 60000)
  const days = Math.floor(totalMins / 1440)
  const hours = Math.floor((totalMins % 1440) / 60)
  const mins = totalMins % 60

  if (days > 3) return { text: `距开标还有 ${days} 天`, color: '#52c41a' }
  if (days > 0) return { text: `距开标还有 ${days} 天 ${hours} 小时`, color: '#fa8c16' }
  if (hours > 0) return { text: `距开标还有 ${hours} 小时 ${mins} 分`, color: '#ff7a00' }
  return { text: `距开标还有 ${mins} 分钟`, color: '#ff4d4f' }
}

function buildDefaultRegNote(start: string, end: string): string {
  if (!start || !end) return ''
  return `${start}-${end}报名时间（上午08时30分至12时00分，下午14时30分至17时00分）。`
}

// ── 中文日期串 ↔ dayjs ──────────────────────────────────────────────
// DatePicker 用 dayjs；存库仍用中文串（"2026年6月1日" / "2026年6月20日15:00"），
// 以兼容 Word 生成与各处「开标时间」抓取正则（要求 年月日时之间无空格）。
function parseCnDate(s?: string): dayjs.Dayjs | null {
  if (!s) return null
  const m = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:(\d{1,2})\s*[：:]\s*(\d{2}))?/)
  if (!m) return null
  const d = dayjs(new Date(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 0, m[5] ? +m[5] : 0))
  return d.isValid() ? d : null
}
function fmtCnDay(d?: dayjs.Dayjs | null): string {
  return d ? d.format('YYYY年M月D日') : ''
}
function fmtCnDateTime(d?: dayjs.Dayjs | null): string {
  return d ? d.format('YYYY年M月D日HH:mm') : ''
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// ─────────────────────────────────────────────────────────────────
// 附件管理（编辑已存在的公告时显示）
// ─────────────────────────────────────────────────────────────────
function AttachmentSection({ annId }: { annId: number }) {
  const { message } = App.useApp()
  const [files, setFiles] = useState<AnnAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })

  const load = useCallback(async () => {
    try {
      const res = await listFiles(annId)
      setFiles(res.data.data)
    } catch { /* ignore */ }
  }, [annId])

  useEffect(() => { load() }, [load])

  const customUpload = async (options: UploadRequestOption) => {
    const { file, onSuccess, onError } = options
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file as Blob)
    try {
      const res = await axios.post(`/api/announcements/${annId}/files`, formData, {
        withCredentials: true,
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      onSuccess?.(res.data)
      message.success('上传成功')
      load()
    } catch (err: any) {
      onError?.(err)
      message.error(err.response?.data?.error || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (fileId: number) => {
    try {
      await deleteFile(annId, fileId)
      message.success('已删除')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '删除失败')
    }
  }

  return (
    <div>
      <Upload
        customRequest={customUpload}
        showUploadList={false}
        accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar"
        disabled={uploading}
      >
        <Button icon={<UploadOutlined />} loading={uploading}>
          点击上传（支持 PDF / Word / Excel / 图片 / 压缩包）
        </Button>
      </Upload>
      {files.length > 0 && (
        <List
          size="small"
          style={{ marginTop: 8 }}
          dataSource={files}
          renderItem={(f) => (
            <List.Item
              actions={[
                ...(isPreviewable(f.original_name) ? [
                  <a key="pv" onClick={() => setPreview({ open: true, url: previewFileUrl(annId, f.id), name: f.original_name })}>
                    预览
                  </a>,
                ] : []),
                <a key="dl" href={downloadFileUrl(annId, f.id)} download={f.original_name}>
                  下载
                </a>,
                <Popconfirm
                  key="del"
                  title="确认删除该附件？"
                  onConfirm={() => handleDelete(f.id)}
                >
                  <Button type="link" danger size="small">删除</Button>
                </Popconfirm>,
              ]}
            >
              <Space>
                <FileOutlined style={{ color: '#1677ff' }} />
                <Text>{f.original_name}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>{formatSize(f.file_size)}</Text>
              </Space>
            </List.Item>
          )}
        />
      )}
      {files.length === 0 && (
        <div style={{ color: '#aaa', fontSize: 12, marginTop: 6 }}>
          暂无附件。生成Word时附件名将自动列于文档末尾。
        </div>
      )}
      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// 代理机构模板管理抽屉
// ─────────────────────────────────────────────────────────────────
interface TemplateMgrProps {
  open: boolean
  agencyCode: string
  onClose: () => void
  onApply: (tpl: AgencyTemplate) => void
}

function TemplateMgrDrawer({ open, agencyCode, onClose, onApply }: TemplateMgrProps) {
  const { message } = App.useApp()
  const [templates, setTemplates] = useState<AgencyTemplate[]>([])
  const [editing, setEditing] = useState<AgencyTemplate | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    if (!agencyCode) return
    try {
      const res = await getTemplates(agencyCode)
      setTemplates(res.data.data)
    } catch {
      message.error('加载模板失败')
    }
  }, [agencyCode])

  useEffect(() => { if (open) load() }, [open, load])

  const openNew = () => {
    setEditing(null)
    form.resetFields()
    setModalOpen(true)
  }
  const openEdit = (tpl: AgencyTemplate) => {
    setEditing(tpl)
    form.setFieldsValue(tpl)
    setModalOpen(true)
  }
  const handleSave = async () => {
    try { await form.validateFields() } catch { return }
    const values = form.getFieldsValue()
    try {
      if (editing) {
        await updateTemplate(editing.id, { ...values, agency_code: agencyCode })
        message.success('模板已更新')
      } else {
        await createTemplate({ ...values, agency_code: agencyCode })
        message.success('模板已创建')
      }
      setModalOpen(false)
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '操作失败')
    }
  }
  const handleDelete = async (id: number) => {
    try {
      await deleteTemplate(id)
      message.success('已删除')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '删除失败')
    }
  }

  return (
    <>
      <Drawer
        title={<><AppstoreOutlined style={{ marginRight: 6 }} />代理机构预设模板</>}
        open={open}
        onClose={onClose}
        width={560}
        extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={openNew}>新增模板</Button>}
      >
        {templates.length === 0
          ? <div style={{ textAlign: 'center', color: '#aaa', padding: 40 }}>暂无模板，点击右上角新增</div>
          : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {templates.map(tpl => (
                <Card key={tpl.id} size="small" title={<Text strong>{tpl.template_name}</Text>}
                  extra={
                    <Space size={4}>
                      <Button size="small" type="primary" ghost onClick={() => { onApply(tpl); onClose() }}>套用</Button>
                      <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(tpl)} />
                      <Popconfirm title="确认删除该模板？" onConfirm={() => handleDelete(tpl.id)}>
                        <Button size="small" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    </Space>
                  }
                >
                  <div style={{ fontSize: 12, color: '#555', lineHeight: 1.8 }}>
                    {tpl.agency_address && <div>📍 {tpl.agency_address}</div>}
                    {tpl.agency_email && <div>📧 {tpl.agency_email}</div>}
                    {tpl.agency_contact && <div>👤 {tpl.agency_contact}  📞 {tpl.agency_contact_phone}</div>}
                    {tpl.agency_reg_phone && <div>📞 报名：{tpl.agency_reg_phone}</div>}
                  </div>
                </Card>
              ))}
            </div>
          )
        }
      </Drawer>
      <Modal title={editing ? '编辑模板' : '新增模板'} open={modalOpen}
        onOk={handleSave} onCancel={() => setModalOpen(false)}
        okText="保存" cancelText="取消" width={480} destroyOnClose
      >
        <Form form={form} layout="vertical" size="middle">
          <Form.Item label="模板名称" name="template_name"
            rules={[{ required: true, message: '请填写模板名称' }]}
            extra="如：总部地址">
            <Input placeholder="模板名称" />
          </Form.Item>
          <Form.Item label="代理机构地址" name="agency_address">
            <Input placeholder="获取文件/递交地点" />
          </Form.Item>
          <Form.Item label="递交响应文件地点" name="delivery_address" extra="留空则与上同">
            <Input placeholder="（与代理机构地址不同时填写）" />
          </Form.Item>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item label="代理机构邮箱" name="agency_email" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item label="报名咨询电话" name="agency_reg_phone" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item label="联系人" name="agency_contact" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item label="联系电话" name="agency_contact_phone" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </div>
        </Form>
      </Modal>
    </>
  )
}

// ─────────────────────────────────────────────────────────────────
// 主页面
// ─────────────────────────────────────────────────────────────────
export default function AnnouncementPage() {
  const { message } = App.useApp()
  const { user } = useAuth()
  const [list, setList] = useState<Announcement[]>([])
  const [projects, setProjects] = useState<AnnProject[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [tplDrawerOpen, setTplDrawerOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [tableLoading, setTableLoading] = useState(false)
  const [form] = Form.useForm()
  const [selectedProject, setSelectedProject] = useState<AnnProject | null>(null)

  // 搜索/筛选/标签
  const [tab, setTab] = useState<AnnTab>('toconfirm')
  const [search, setSearch] = useState('')
  const [filterAgency, setFilterAgency] = useState<string | undefined>()
  const [filterYearAnn, setFilterYearAnn] = useState<string | undefined>()
  const [sortByAnn, setSortByAnn] = useState<'created' | 'number'>('created')
  const [sortAscAnn, setSortAscAnn] = useState(false)   // 默认倒序（新的/编号大的在前）
  // 点项目名在线预览生成的公告 Word
  const [docPreview, setDocPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })
  // 新建时先攒着附件，保存时一并上传；驳回弹窗
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [rejectRow, setRejectRow] = useState<Announcement | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const isAgency = user?.role === 'agency'
  const canConfirm = ['officer', 'assistant', 'leader'].includes(user?.role || '')

  const load = async () => {
    setTableLoading(true)
    try {
      const [annRes, projRes] = await Promise.all([
        getAnnouncements('procurement'),
        getEligibleProjects(),
      ])
      setList(annRes.data.data)
      setProjects(projRes.data.data)
    } catch {
      message.error('加载数据失败')
    } finally {
      setTableLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // 报名时间变化时自动生成备注（仅当备注为空）
  const regStart = Form.useWatch('reg_start', form) as dayjs.Dayjs | undefined
  const regEnd = Form.useWatch('reg_end', form) as dayjs.Dayjs | undefined
  const regNote: string = Form.useWatch('reg_note', form) ?? ''
  useEffect(() => {
    if (!regNote && regStart && regEnd) {
      form.setFieldValue('reg_note', buildDefaultRegNote(fmtCnDay(regStart), fmtCnDay(regEnd)))
    }
  }, [regStart, regEnd])

  // ── 按标签分组 ────────────────────────────────────────────────
  const toConfirmList = list.filter(a => a.status === '待确认')
  const rejectedList = list.filter(a => a.status === '已驳回')
  const draftList = list.filter(a => a.status === '草稿')
  const publishedList = list.filter(a => a.status === '已确认' && !isDeadlinePassed(a.response_deadline))
  const openedList = list.filter(a => a.status === '已确认' && isDeadlinePassed(a.response_deadline))

  // ── 搜索/筛选 ─────────────────────────────────────────────────
  const agencyOptions = Array.from(
    new Set(list.map(a => a.agency_name).filter(Boolean))
  ).sort().map(a => ({ value: a, label: a }))

  const yearOptionsAnn = Array.from(new Set(list.map(a =>
    (a.project_number || '').match(/^(20\d{2})/)?.[1] || (a.created_at || '').slice(0, 4),
  ).filter(Boolean))).sort().reverse()

  const applyFilter = (data: Announcement[]) => {
    const q = search.trim().toLowerCase()
    const out = data.filter(a => {
      const matchSearch = !q ||
        (a.project_name || '').toLowerCase().includes(q) ||
        (a.project_number || '').toLowerCase().includes(q)
      const matchAgency = !filterAgency || a.agency_name === filterAgency
      const y = (a.project_number || '').match(/^(20\d{2})/)?.[1] || (a.created_at || '').slice(0, 4)
      const matchYear = !filterYearAnn || y === filterYearAnn
      return matchSearch && matchAgency && matchYear
    })
    return out.sort((a, b) => {
      const r = sortByAnn === 'number'
        ? (a.project_number || '').localeCompare(b.project_number || '')
        : (a.created_at || '').localeCompare(b.created_at || '')
      return sortAscAnn ? r : -r
    })
  }

  const filteredToConfirm = applyFilter(toConfirmList)
  const filteredRejected = applyFilter(rejectedList)
  const filteredDraft = applyFilter(draftList)
  const filteredPublished = applyFilter(publishedList)
  const filteredOpened = applyFilter(openedList)

  const currentData = tab === 'toconfirm' ? filteredToConfirm
    : tab === 'rejected' ? filteredRejected
    : tab === 'draft' ? filteredDraft
    : tab === 'published' ? filteredPublished
    : filteredOpened

  // ── 表单操作 ──────────────────────────────────────────────────
  const openNew = () => {
    setEditId(null)
    setSelectedProject(null)
    form.resetFields()
    form.setFieldsValue({
      round_number: 1,
      ann_type: 'procurement',
      qualifications: QUALIFICATIONS_DEFAULT,
    })
    setDrawerOpen(true)
  }

  // 待办「去处理」跳转：已发该项目公告→高亮其行；否则打开新建并预选该项目
  useFocusTarget(!loading && projects.length > 0, (id) => {
    const ann = list.find(a => a.project_id === id && a.ann_type === 'procurement')
    if (ann) {
      flashRow(ann.id)
    } else {
      openNew()
      form.setFieldsValue({ project_id: id })
      setSelectedProject(projects.find(x => x.id === id) || null)
    }
  })

  const openEdit = (ann: Announcement) => {
    setEditId(ann.id)
    const proj = projects.find(p => p.id === ann.project_id) || null
    setSelectedProject(proj)
    form.setFieldsValue({
      project_id: ann.project_id,
      ann_type: ann.ann_type,
      round_number: ann.round_number,
      project_intro: ann.project_intro,
      qualifications: ann.qualifications || QUALIFICATIONS_DEFAULT,
      special_req: ann.special_req,
      reg_start: parseCnDate(ann.reg_start),
      reg_end: parseCnDate(ann.reg_end),
      reg_note: ann.reg_note,
      response_deadline: parseCnDate(ann.response_deadline),
      agency_address: ann.agency_address,
      delivery_address: ann.delivery_address,
      agency_email: ann.agency_email,
      agency_reg_phone: ann.agency_reg_phone,
      agency_contact: ann.agency_contact,
      agency_contact_phone: ann.agency_contact_phone,
    })
    setDrawerOpen(true)
  }

  const applyTemplate = (tpl: AgencyTemplate) => {
    form.setFieldsValue({
      agency_address: tpl.agency_address,
      delivery_address: tpl.delivery_address,
      agency_email: tpl.agency_email,
      agency_reg_phone: tpl.agency_reg_phone,
      agency_contact: tpl.agency_contact,
      agency_contact_phone: tpl.agency_contact_phone,
    })
    message.success(`已套用模板「${tpl.template_name}」`)
  }

  // 新建时暂存的附件：保存后自动上传，省掉"先存草稿才能传附件"那一步
  const uploadPendingAnn = async (annId: number) => {
    let ok = 0
    for (const f of pendingFiles) {
      const fd = new FormData()
      fd.append('file', f)
      try {
        await axios.post(`/api/announcements/${annId}/files`, fd, {
          withCredentials: true,
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        ok += 1
      } catch { message.error(`附件「${f.name}」上传失败`) }
    }
    return ok
  }

  /** 一步完成：保存（新建则创建）→ 传附件 →（可选）提交确认。 */
  const handleSave = async (thenSubmit = false) => {
    try { await form.validateFields() } catch { return }
    const values = form.getFieldsValue()
    // 日历控件返回 dayjs，统一转回中文串存库（无空格，确保各处开标时间可正确抓取）
    const payload = {
      ...values,
      reg_start: fmtCnDay(values.reg_start),
      reg_end: fmtCnDay(values.reg_end),
      response_deadline: fmtCnDateTime(values.response_deadline),
    }
    setLoading(true)
    try {
      let annId: number
      if (editId) {
        await updateAnnouncement(editId, payload)
        annId = editId
      } else {
        const res = await createAnnouncement(payload)
        annId = res.data.data.id
      }
      const uploaded = pendingFiles.length ? await uploadPendingAnn(annId) : 0
      setPendingFiles([])
      if (thenSubmit) {
        await submitAnnouncement(annId)
        message.success(`已提交确认${uploaded ? `（含 ${uploaded} 个附件）` : ''}，等待采购人确认发布`)
      } else {
        message.success(`已保存${uploaded ? `，附件 ${uploaded} 个已上传` : ''}`)
      }
      setDrawerOpen(false)
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  const handleReject = async () => {
    if (!rejectRow) return
    if (!rejectReason.trim()) { message.warning('请填写驳回原因'); return }
    try {
      await rejectAnnouncement(rejectRow.id, rejectReason.trim())
      message.success('已驳回')
      setRejectRow(null); setRejectReason('')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '驳回失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteAnnouncement(id)
      message.success('已删除')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '删除失败')
    }
  }

  const handleSubmit = async (id: number) => {
    try {
      await submitAnnouncement(id)
      message.success('已提交，等待经办人确认发布')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '提交失败')
    }
  }

  const handleConfirm = async (id: number) => {
    try {
      await confirmAnnouncement(id)
      message.success('公告已确认发布，将在登录页面公开展示')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '确认失败')
    }
  }

  const handleRevoke = async (id: number) => {
    try {
      await revokeAnnouncement(id)
      message.success('已撤回，恢复为草稿')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '撤回失败')
    }
  }

  const handleGenerate = async (ann: Announcement) => {
    try {
      const res = await generateAnnouncementWord(ann.id)
      const suffix = ann.round_number > 1 ? `（第${'一二三四五'[ann.round_number - 1]}次）` : ''
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `采购公告_${ann.project_number}${suffix}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('采购公告已生成，正在下载')
    } catch (err: any) {
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text()
        try { message.error(JSON.parse(text).error || '生成失败') } catch { message.error('生成失败') }
      } else {
        message.error(err.response?.data?.error || '生成失败')
      }
    }
  }

  // ── 列定义（待挂网） ──────────────────────────────────────────
  const roundTag = (v: number) => v > 1
    ? <Tag color="orange" style={{ marginInlineEnd: 0 }}>第{'一二三四五'[v - 1]}次</Tag>
    : <Tag color="blue" style={{ marginInlineEnd: 0 }}>第一次</Tag>

  const annToCard = (record: Announcement): RecordCardData => {
    const isOpened = tab === 'opened'
    const isPublished = tab === 'published'
    const fields: { label: string; value: React.ReactNode }[] = [
      { label: '当前处理人', value: <PendingOwnerTag p={record.pending} compact /> },
      { label: '代理', value: record.agency_name },
      { label: '开标', value: record.response_deadline },
    ]
    if (isPublished) {
      const { text, color } = getCountdown(record.response_deadline)
      fields.push({ label: '倒计时', value: <span style={{ color, fontWeight: 500 }}><ClockCircleOutlined style={{ marginRight: 4 }} />{text}</span> })
      fields.push({ label: '确认人', value: record.confirmed_by })
    } else if (isOpened) {
      fields.push({ label: '确认人', value: record.confirmed_by })
    } else {
      fields.push({ label: '编制人', value: record.created_by })
    }
    if (record.status === '已驳回' && record.reject_reason) {
      fields.push({
        label: `驳回原因${(record.reject_count || 0) > 1 ? `（第${record.reject_count}次）` : ''}`,
        value: <Text type="danger">{record.reject_reason}</Text>,
      })
    }
    const editable = ['toconfirm', 'rejected', 'draft'].includes(tab)
    return {
      key: record.id,
      accent: isOpened ? '#9aa0a6'
        : record.status === '已确认' ? '#34a853'
        : record.status === '待确认' ? '#f9ab00'
        : record.status === '已驳回' ? '#d93025' : '#1a73e8',
      title: record.project_name,
      onTitleClick: () => setDocPreview({ open: true, url: announcementWordUrl(record.id), name: `${record.project_name}-公告.docx` }),
      subtitle: record.project_number,
      statusText: isOpened ? '已开标' : record.status,
      statusColor: isOpened ? 'default' : STATUS_COLOR[record.status] || 'default',
      tags: roundTag(record.round_number),
      fields,
      actions: (
        <>
          <Button size="small" type="primary" ghost icon={<DownloadOutlined />} onClick={() => handleGenerate(record)}>Word</Button>
          {editable && (
            <>
              <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
              {isAgency && ['草稿', '已驳回'].includes(record.status) && (
                <Popconfirm title="提交后由采购人确认发布，确认提交？" onConfirm={() => handleSubmit(record.id)}>
                  <Button size="small" icon={<SendOutlined />} type="primary" ghost>
                    {record.status === '已驳回' ? '修改后重新提交' : '提交'}
                  </Button>
                </Popconfirm>
              )}
              {canConfirm && record.status === '草稿' && (
                <Popconfirm title="直接发布后将在登录页面公开挂网，同时自动同步开标时间到项目，确认发布？" onConfirm={() => handleConfirm(record.id)}>
                  <Button size="small" icon={<CheckCircleOutlined />} type="primary">直接发布</Button>
                </Popconfirm>
              )}
              {canConfirm && record.status === '待确认' && (
                <>
                  <Popconfirm title="确认发布后将在登录页面公开挂网，同时自动同步开标时间到项目，确认？" onConfirm={() => handleConfirm(record.id)}>
                    <Button size="small" icon={<CheckCircleOutlined />} type="primary">确认发布</Button>
                  </Popconfirm>
                  <Button size="small" danger icon={<StopOutlined />}
                    onClick={() => { setRejectRow(record); setRejectReason('') }}>驳回</Button>
                </>
              )}
              <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </>
          )}
          {tab === 'published' && canConfirm && (
            <>
              <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
              <Tooltip title="撤回发布，恢复为草稿">
                <Popconfirm title="撤回后公告将从挂网页面撤下，确认撤回？" onConfirm={() => handleRevoke(record.id)}>
                  <Button size="small" icon={<RollbackOutlined />} danger>撤回</Button>
                </Popconfirm>
              </Tooltip>
            </>
          )}
        </>
      ),
    }
  }

  const currentAgencyCode = isAgency
    ? user?.agency_code || ''
    : selectedProject?.agency_code || ''

  return (
    <Card>
      {/* ── 顶部标题 + 操作 ──────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50' }}>
          <FileWordOutlined style={{ marginRight: 8, color: '#1677ff' }} />采购公告
        </div>
        <Space>
          {isAgency && (
            <Button icon={<AppstoreOutlined />} onClick={() => setTplDrawerOpen(true)}>
              预设模板
            </Button>
          )}
          <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>
            新建采购公告
          </Button>
        </Space>
      </div>

      {/* ── 搜索/筛选栏 ──────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索项目名称或编号"
          allowClear
          style={{ width: 240 }}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <Select
          placeholder="筛选代理机构"
          allowClear
          style={{ width: 180 }}
          value={filterAgency}
          onChange={setFilterAgency}
          options={agencyOptions}
        />
        <Select
          placeholder="年度"
          allowClear
          style={{ width: 100 }}
          value={filterYearAnn}
          onChange={setFilterYearAnn}
          options={yearOptionsAnn.map(y => ({ value: y, label: `${y}年` }))}
        />
        <Segmented
          value={sortByAnn}
          onChange={v => setSortByAnn(v as 'created' | 'number')}
          options={[
            { value: 'created', label: '按新增时间' },
            { value: 'number', label: '按项目编号' },
          ]}
        />
        <Button
          icon={sortAscAnn ? <SortAscendingOutlined /> : <SortDescendingOutlined />}
          onClick={() => setSortAscAnn(v => !v)}
        >
          {sortAscAnn ? '正序' : '倒序'}
        </Button>
        <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>
          {`当前 ${currentData.length} 条`}
        </Text>
      </div>

      {/* ── 三栏标签页 ──────────────────────────────────────────── */}
      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as AnnTab)}
        items={[
          {
            key: 'toconfirm',
            label: (
              <span>
                <HourglassOutlined style={{ marginRight: 4 }} />
                待确认
                {toConfirmList.length > 0 && (
                  <Badge count={toConfirmList.length} size="small"
                    style={{ marginLeft: 6, backgroundColor: '#faad14' }} />
                )}
              </span>
            ),
          },
          {
            key: 'rejected',
            label: (
              <span>
                <StopOutlined style={{ marginRight: 4 }} />
                已驳回
                {rejectedList.length > 0 && (
                  <Badge count={rejectedList.length} size="small"
                    style={{ marginLeft: 6, backgroundColor: '#d93025' }} />
                )}
              </span>
            ),
          },
          {
            key: 'draft',
            label: (
              <span>
                <SaveOutlined style={{ marginRight: 4 }} />
                草稿
                {draftList.length > 0 && (
                  <Badge count={draftList.length} size="small"
                    style={{ marginLeft: 6, backgroundColor: '#9aa0a6' }} />
                )}
              </span>
            ),
          },
          {
            key: 'published',
            label: (
              <span>
                <ClockCircleOutlined style={{ marginRight: 4 }} />
                挂网进行中
                {publishedList.length > 0 && (
                  <Badge count={publishedList.length} size="small"
                    style={{ marginLeft: 6, backgroundColor: '#52c41a' }} />
                )}
              </span>
            ),
          },
          {
            key: 'opened',
            label: (
              <span>
                <CheckSquareOutlined style={{ marginRight: 4 }} />
                已开标
                {openedList.length > 0 && (
                  <Badge count={openedList.length} size="small"
                    style={{ marginLeft: 6, backgroundColor: '#aaa' }} />
                )}
              </span>
            ),
          },
        ]}
      />

      {/* ── 说明提示 ─────────────────────────────────────────────── */}
      {tab === 'toconfirm' && (
        <Alert
          type="warning" showIcon
          message={isAgency
            ? '已提交给采购人、等待确认发布的公告。若被驳回会移到「已驳回」页签并附上原因。'
            : '待确认：代理机构已提交、等你拍板的公告。可「确认发布」挂网，也可「驳回」并写明要改什么。'}
          style={{ marginBottom: 12 }}
        />
      )}
      {tab === 'rejected' && (
        <Alert
          type="error" showIcon
          message="已驳回：采购人打回修改的公告，卡片上直接显示驳回原因。代理机构改完点「修改后重新提交」即可再次送审，全过程记入审批过程记录并随项目归档。"
          style={{ marginBottom: 12 }}
        />
      )}
      {tab === 'draft' && (
        <Alert
          type="info" showIcon
          message="草稿：尚未提交的公告。新建时可直接选附件，点「保存并提交确认」一步完成编制、传附件、送审。"
          style={{ marginBottom: 12 }}
        />
      )}
      {tab === 'published' && (
        <Alert
          type="success" showIcon
          message="挂网进行中：已公开发布，供应商可在登录页面查看。表格中实时显示距开标剩余时间。"
          style={{ marginBottom: 12 }}
        />
      )}
      {tab === 'opened' && (
        <Alert
          type="info" showIcon
          message="已开标：响应截止时间已过的公告，可下载Word存档备查。"
          style={{ marginBottom: 12 }}
        />
      )}

      <RecordCards dataSource={currentData} loading={tableLoading} emptyText="暂无数据" toCard={annToCard} />

      {/* ── 新建/编辑 Drawer ──────────────────────────────────────── */}
      <Drawer
        title={editId ? '编辑采购公告' : '新建采购公告'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={700}
        footer={
          <Space>
            <Button type="primary" icon={<SendOutlined />} loading={loading}
              onClick={() => handleSave(true)}>
              保存并提交确认
            </Button>
            <Button icon={<SaveOutlined />} loading={loading} onClick={() => handleSave(false)}>
              仅保存{editId ? '' : '草稿'}
            </Button>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical" size="middle">
          {/* 关联项目 */}
          <Form.Item label="关联项目" name="project_id"
            rules={[{ required: true, message: '请选择项目' }]}>
            <Select showSearch placeholder="搜索项目名称或编号" disabled={!!editId}
              filterOption={(input, opt) =>
                (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())}
              onChange={(id: number) => {
                const p = projects.find(x => x.id === id) || null
                setSelectedProject(p)
              }}
              options={projects.map(p => ({ value: p.id, label: `${p.number}  ${p.name}` }))}
            />
          </Form.Item>

          {selectedProject && (
            <Descriptions size="small" bordered column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="项目编号"><Text code>{selectedProject.number}</Text></Descriptions.Item>
              <Descriptions.Item label="代理机构">{selectedProject.agency_name}</Descriptions.Item>
            </Descriptions>
          )}

          <Form.Item label="开标次数" name="round_number" style={{ width: 180 }}>
            <Select options={ROUND_OPTIONS} />
          </Form.Item>

          <Divider plain>招标内容</Divider>

          <Form.Item label="招标项目简介" name="project_intro"
            rules={[{ required: true, message: '请填写招标项目简介' }]}
            extra="对应公告 1.3 节正文">
            <TextArea rows={4} placeholder="如：本项目拟采购XX耗材，用于临床科室日常使用，采购数量详见竞选文件。" />
          </Form.Item>

          <Form.Item
            label="一般资格要求（预设6条，可直接修改）"
            name="qualifications"
            extra="对应公告 1.5 节一至六条；每行一条，按行填入Word文档"
          >
            <TextArea
              rows={7}
              placeholder={QUALIFICATIONS_DEFAULT}
              style={{ fontFamily: 'inherit', fontSize: 13 }}
            />
          </Form.Item>

          <Form.Item
            label="特殊资格要求（选填）"
            name="special_req"
            extra="对应公告 1.5 节「二、特殊资格要求」；每行一条，自动编号（一）（二）…，留空则填「无。」"
          >
            <TextArea rows={2} placeholder="如有特殊资质要求每行一条填写，否则留空" />
          </Form.Item>

          <Divider plain>时间安排</Divider>

          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item label="报名开始日期" name="reg_start"
              rules={[{ required: true, message: '请选择报名开始日期' }]} style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} format="YYYY年M月D日" placeholder="选择报名开始日期" />
            </Form.Item>
            <Form.Item label="报名截止日期" name="reg_end"
              rules={[{ required: true, message: '请选择报名截止日期' }]} style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} format="YYYY年M月D日" placeholder="选择报名截止日期" />
            </Form.Item>
          </div>

          <Form.Item label="报名时间备注" name="reg_note"
            extra="根据报名起止时间自动生成，可直接修改；对应公告「注：」行">
            <TextArea rows={2}
              placeholder="如：2026年6月1日-2026年6月10日报名时间（上午08时30分至12时00分，下午14时30分至17时00分）。" />
          </Form.Item>

          <Form.Item label="响应文件截止时间（开标时间）" name="response_deadline"
            rules={[{ required: true, message: '请选择开标日期时间' }]}
            extra="日历选择，精确到分钟，如：2026年6月20日15:00；此时间用于判断挂网进行中/已开标及开标倒计时">
            <DatePicker
              showTime={{ format: 'HH:mm' }}
              format="YYYY年M月D日HH:mm"
              style={{ width: 280 }}
              placeholder="选择开标日期时间"
            />
          </Form.Item>

          <Divider plain>
            代理机构信息
            {selectedProject?.agency_code && (
              <Button size="small" type="link" icon={<AppstoreOutlined />}
                style={{ marginLeft: 8 }} onClick={() => setTplDrawerOpen(true)}>
                从模板套用
              </Button>
            )}
          </Divider>

          <Form.Item label="代理机构地址（获取文件/递交文件地点）" name="agency_address"
            rules={[{ required: true, message: '请填写' }]}>
            <Input placeholder="如：内江市市中区XX路XX号" />
          </Form.Item>
          <Form.Item label="递交响应文件地点（如与上述不同则填写）" name="delivery_address"
            extra="留空则自动使用代理机构地址">
            <Input placeholder="留空则与代理机构地址相同" />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item label="代理机构邮箱" name="agency_email"
              rules={[{ required: true, message: '请填写' }]} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item label="报名咨询电话" name="agency_reg_phone"
              rules={[{ required: true, message: '请填写' }]} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item label="代理联系人" name="agency_contact"
              rules={[{ required: true, message: '请填写' }]} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item label="代理联系电话" name="agency_contact_phone"
              rules={[{ required: true, message: '请填写' }]} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </div>

          {/* 附件上传（仅编辑已存在的公告时显示） */}
          {editId && (
            <>
              <Divider plain>采购文件附件</Divider>
              <Form.Item
                label="上传附件"
                extra="上传采购需求、报名表等文件；生成Word时附件名自动列于文档末尾"
              >
                <AttachmentSection annId={editId} />
              </Form.Item>
            </>
          )}
          {!editId && (
            <>
              <Divider plain>采购文件附件</Divider>
              <Form.Item
                label="选择附件"
                extra="现在选、保存时自动上传——不必先存草稿再回来传。生成 Word 时附件名自动列于文档末尾"
              >
                <Upload
                  multiple showUploadList={false}
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar"
                  beforeUpload={(file) => {
                    setPendingFiles(prev => [...prev, file as unknown as File])
                    return false
                  }}
                >
                  <Button icon={<UploadOutlined />}>选择附件</Button>
                </Upload>
                {pendingFiles.length > 0 && (
                  <List
                    size="small" style={{ marginTop: 8 }}
                    dataSource={pendingFiles}
                    renderItem={(f, i) => (
                      <List.Item actions={[
                        <Button key="rm" type="link" size="small" danger
                          onClick={() => setPendingFiles(prev => prev.filter((_, j) => j !== i))}>移除</Button>,
                      ]}>
                        <FileOutlined style={{ marginRight: 6 }} />{f.name}
                        <Text type="secondary" style={{ marginLeft: 8 }}>{formatSize(f.size)}</Text>
                      </List.Item>
                    )}
                  />
                )}
              </Form.Item>
            </>
          )}
        </Form>
      </Drawer>

      {/* ── 驳回弹窗 ─────────────────────────────────────────────── */}
      <Modal
        open={!!rejectRow}
        title={`驳回采购公告 — ${rejectRow?.project_name || ''}`}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        onOk={handleReject}
        onCancel={() => { setRejectRow(null); setRejectReason('') }}
      >
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message="驳回后公告退回代理机构修改，改完重新提交需再次确认。同一份公告可反复驳回，每次的原因都会记入审批过程记录，归档时随项目一并留存。" />
        <Input.TextArea
          rows={4} maxLength={500} showCount
          placeholder="请写明需要修改的具体内容，例如：资格要求第六项与采购文件不一致；报名截止时间少于法定天数"
          value={rejectReason}
          onChange={e => setRejectReason(e.target.value)}
        />
      </Modal>

      {/* ── 代理机构模板管理 Drawer ────────────────────────────────── */}
      <TemplateMgrDrawer
        open={tplDrawerOpen}
        agencyCode={currentAgencyCode}
        onClose={() => setTplDrawerOpen(false)}
        onApply={applyTemplate}
      />

      {/* 点项目名：在线预览生成的公告 Word */}
      <FilePreviewModal
        open={docPreview.open}
        url={docPreview.url}
        filename={docPreview.name}
        onClose={() => setDocPreview((p) => ({ ...p, open: false }))}
      />
    </Card>
  )
}
