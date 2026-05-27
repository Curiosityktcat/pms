import { useEffect, useState, useCallback } from 'react'
import {
  Card, Table, Button, Form, Input, Select, Drawer, Space, Popconfirm,
  App, Tag, Typography, Divider, Descriptions, Alert, Modal,
  Tooltip, Upload, List,
} from 'antd'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type UploadRequestOption = any
import type { ColumnsType } from 'antd/es/table'
import {
  PlusOutlined, DownloadOutlined, EditOutlined, DeleteOutlined,
  FileWordOutlined, CheckCircleOutlined, SendOutlined, RollbackOutlined,
  SaveOutlined, AppstoreOutlined, UploadOutlined, FileOutlined,
} from '@ant-design/icons'
import axios from 'axios'
import {
  getEligibleProjects, getAnnouncements, createAnnouncement, updateAnnouncement,
  deleteAnnouncement, generateAnnouncementWord,
  submitAnnouncement, confirmAnnouncement, revokeAnnouncement,
  listFiles, deleteFile, downloadFileUrl,
  QUALIFICATIONS_DEFAULT,
} from '../services/announcement'
import type { Announcement, AnnProject, AnnAttachment } from '../services/announcement'
import {
  getTemplates, createTemplate, updateTemplate, deleteTemplate,
} from '../services/agencyTemplate'
import type { AgencyTemplate } from '../services/agencyTemplate'
import { useAuth } from '../hooks/useAuth'

const { TextArea } = Input
const { Text } = Typography

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

function buildDefaultRegNote(start: string, end: string): string {
  if (!start || !end) return ''
  return `${start}-${end}报名时间（上午08时30分至12时00分，下午14时30分至17时00分）。`
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
  const regStart: string = Form.useWatch('reg_start', form) ?? ''
  const regEnd: string = Form.useWatch('reg_end', form) ?? ''
  const regNote: string = Form.useWatch('reg_note', form) ?? ''
  useEffect(() => {
    if (!regNote && regStart && regEnd) {
      form.setFieldValue('reg_note', buildDefaultRegNote(regStart, regEnd))
    }
  }, [regStart, regEnd])

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
      reg_start: ann.reg_start,
      reg_end: ann.reg_end,
      reg_note: ann.reg_note,
      response_deadline: ann.response_deadline,
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

  const handleSave = async () => {
    try { await form.validateFields() } catch { return }
    const values = form.getFieldsValue()
    setLoading(true)
    try {
      if (editId) {
        await updateAnnouncement(editId, values)
        message.success('已保存')
      } else {
        await createAnnouncement(values)
        message.success('已创建草稿')
      }
      setDrawerOpen(false)
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '操作失败')
    } finally {
      setLoading(false)
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
      message.success('已提交，等待经办人确认')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '提交失败')
    }
  }

  const handleConfirm = async (id: number) => {
    try {
      await confirmAnnouncement(id)
      message.success('公告已确认')
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

  const columns: ColumnsType<Announcement> = [
    { title: '项目编号', dataIndex: 'project_number', width: 200, render: (v) => <Text code>{v}</Text> },
    { title: '项目名称', dataIndex: 'project_name', ellipsis: true },
    { title: '代理机构', dataIndex: 'agency_name', width: 150, ellipsis: true },
    {
      title: '开标次数', dataIndex: 'round_number', width: 90,
      render: (v) => v > 1 ? <Tag color="orange">第{'一二三四五'[v - 1]}次</Tag> : <Tag color="blue">第一次</Tag>,
    },
    { title: '报名截止', dataIndex: 'reg_end', width: 120 },
    { title: '响应截止', dataIndex: 'response_deadline', width: 160 },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v) => <Tag color={STATUS_COLOR[v] || 'default'}>{v}</Tag>,
    },
    { title: '编制人', dataIndex: 'created_by', width: 90, render: (v) => v || '—' },
    {
      title: '操作', width: 240,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button size="small" icon={<DownloadOutlined />} type="primary" onClick={() => handleGenerate(record)}>
            Word
          </Button>
          {(record.status !== '已确认' || canConfirm) && (
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          )}
          {isAgency && record.status === '草稿' && (
            <Popconfirm title="确认提交给经办人确认？" onConfirm={() => handleSubmit(record.id)}>
              <Button size="small" icon={<SendOutlined />}>提交</Button>
            </Popconfirm>
          )}
          {canConfirm && record.status === '待确认' && (
            <Popconfirm title="确认通过该公告？" onConfirm={() => handleConfirm(record.id)}>
              <Button size="small" icon={<CheckCircleOutlined />} type="primary" ghost>确认</Button>
            </Popconfirm>
          )}
          {canConfirm && record.status === '已确认' && (
            <Tooltip title="撤回确认，恢复为草稿">
              <Popconfirm title="撤回确认，恢复为草稿？" onConfirm={() => handleRevoke(record.id)}>
                <Button size="small" icon={<RollbackOutlined />}>撤回</Button>
              </Popconfirm>
            </Tooltip>
          )}
          {record.status !== '已确认' && (
            <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const currentAgencyCode = isAgency
    ? user?.agency_code || ''
    : selectedProject?.agency_code || ''

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
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

      <Alert
        type="info" showIcon
        message={isAgency
          ? '代理机构可编制公告，提交后由经办人确认。'
          : '仅显示已正式立项且走代理机构的项目。生成后请盖章发布至医院官网及四川招投标网。'}
        style={{ marginBottom: 16 }}
      />

      <Table rowKey="id" columns={columns} dataSource={list}
        loading={tableLoading} size="small" pagination={{ pageSize: 15 }} />

      {/* ── 新建/编辑 Drawer ─────────────────────────── */}
      <Drawer
        title={editId ? '编辑采购公告' : '新建采购公告'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={700}
        footer={
          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={loading} onClick={handleSave}>
              保存草稿
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

          {/* 一般资格要求：与特殊要求相同形式，预设6条 */}
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
            label="特殊要求（第七项，选填）"
            name="special_req"
            extra="如有特殊资质要求，填写在此处（对应公告1.5节第七条）"
          >
            <TextArea rows={2} placeholder="如需要则填写，否则留空" />
          </Form.Item>

          <Divider plain>时间安排</Divider>

          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item label="报名开始日期" name="reg_start"
              rules={[{ required: true, message: '请填写' }]} style={{ flex: 1 }}>
              <Input placeholder="如：2026年6月1日" />
            </Form.Item>
            <Form.Item label="报名截止日期" name="reg_end"
              rules={[{ required: true, message: '请填写' }]} style={{ flex: 1 }}>
              <Input placeholder="如：2026年6月10日" />
            </Form.Item>
          </div>

          <Form.Item label="报名时间备注" name="reg_note"
            extra="根据报名起止时间自动生成，可直接修改；对应公告「注：」行">
            <TextArea rows={2}
              placeholder="如：2026年6月1日-2026年6月10日报名时间（上午08时30分至12时00分，下午14时30分至17时00分）。" />
          </Form.Item>

          <Form.Item label="响应文件截止时间" name="response_deadline"
            rules={[{ required: true, message: '请填写' }]}
            extra="精确到小时分钟，如：2026年6月20日15:00">
            <Input placeholder="如：2026年6月20日15:00" style={{ maxWidth: 280 }} />
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
            <Alert type="info" showIcon style={{ marginTop: 8 }}
              message="保存草稿后，在「编辑」中可上传采购需求、报名表等附件文件。" />
          )}
        </Form>
      </Drawer>

      {/* ── 代理机构模板管理 Drawer ──────────────────── */}
      <TemplateMgrDrawer
        open={tplDrawerOpen}
        agencyCode={currentAgencyCode}
        onClose={() => setTplDrawerOpen(false)}
        onApply={applyTemplate}
      />
    </Card>
  )
}
