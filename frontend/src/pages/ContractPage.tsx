import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Table, Button, Drawer, Form, Input, Select, Radio, InputNumber,
  Card, Space, Tag, Tabs, App, Typography, Row, Col, Upload, Tooltip,
  Modal, Image, Divider,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined,
  RollbackOutlined, SaveOutlined, UploadOutlined, DownloadOutlined,
  EyeOutlined, FilePdfOutlined, FileWordOutlined, FileExcelOutlined,
  FileImageOutlined, FileOutlined, PaperClipOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  listContracts, createContract, updateContract, deleteContract,
  submitContract, revokeContract, contractFileUrl, uploadContractFile,
  listAttachments, uploadAttachment, deleteAttachment,
  attachmentDownloadUrl, attachmentPreviewUrl, isPreviewable, isImage,
  type Contract, type ContractAttachment,
} from '../services/contract'
import { getProjects, type Project } from '../services/project'

const { Text } = Typography
const { TextArea } = Input

// ── 文件大小格式化 ──────────────────────────────────────────────────
function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// ── 金额格式化 ────────────────────────────────────────────────────
function fmtAmount(amount: number | null, amountIsText: number, amountText: string): string {
  if (amountIsText === 1) return amountText || '—'
  if (amount == null) return '—'
  return `¥${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
}

// ── 文件类型图标 ──────────────────────────────────────────────────
function FileTypeIcon({ mime }: { mime: string }) {
  if (mime.startsWith('image/')) return <FileImageOutlined style={{ color: '#fa8c16', fontSize: 16 }} />
  if (mime === 'application/pdf') return <FilePdfOutlined style={{ color: '#ff4d4f', fontSize: 16 }} />
  if (mime.includes('word')) return <FileWordOutlined style={{ color: '#1677ff', fontSize: 16 }} />
  if (mime.includes('excel') || mime.includes('spreadsheet')) return <FileExcelOutlined style={{ color: '#52c41a', fontSize: 16 }} />
  return <FileOutlined style={{ color: '#888', fontSize: 16 }} />
}

// ── 附件列表组件 ──────────────────────────────────────────────────
interface AttachmentsProps {
  contractId: number | null
  stage: '草案' | '上传'
  onCountChange?: (count: number) => void
}

function AttachmentPanel({ contractId, stage, onCountChange }: AttachmentsProps) {
  const { message, modal } = App.useApp()
  const [atts, setAtts] = useState<ContractAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [previewVisible, setPreviewVisible] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewTitle, setPreviewTitle] = useState('')
  const [previewIsImage, setPreviewIsImage] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    if (!contractId) { setAtts([]); return }
    try {
      const res = await listAttachments(contractId)
      const stageAtts = res.data.data.filter(a => a.stage === stage)
      setAtts(stageAtts)
      onCountChange?.(stageAtts.length)
    } catch {
      // ignore
    }
  }, [contractId, stage, onCountChange])

  useEffect(() => { load() }, [load])

  const handleUpload = async (file: File) => {
    if (!contractId) { message.error('请先保存合同后再上传附件'); return }
    setUploading(true)
    try {
      await uploadAttachment(contractId, file, stage)
      message.success('上传成功')
      load()
    } catch {
      message.error('上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = (att: ContractAttachment) => {
    modal.confirm({
      title: '删除附件',
      content: `确认删除「${att.original_name}」？`,
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteAttachment(contractId!, att.id)
          message.success('已删除')
          load()
        } catch { message.error('删除失败') }
      },
    })
  }

  const handlePreview = (att: ContractAttachment) => {
    const url = attachmentPreviewUrl(contractId!, att.id)
    setPreviewUrl(url)
    setPreviewTitle(att.original_name)
    setPreviewIsImage(isImage(att.mime_type))
    setPreviewVisible(true)
  }

  const stageAtts = atts // 已在 load 中过滤

  return (
    <div>
      {/* 附件列表 */}
      {stageAtts.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {stageAtts.map(att => (
            <div key={att.id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '6px 10px', borderRadius: 6, marginBottom: 4,
              background: '#fafafa', border: '1px solid #f0f0f0',
              transition: 'background .15s',
            }}
              onMouseEnter={e => (e.currentTarget.style.background = '#f0f7ff')}
              onMouseLeave={e => (e.currentTarget.style.background = '#fafafa')}
            >
              <Space size={8} style={{ flex: 1, minWidth: 0 }}>
                <FileTypeIcon mime={att.mime_type} />
                <Tooltip title={att.original_name}>
                  <span style={{ fontSize: 13, color: '#333', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                    {att.original_name}
                  </span>
                </Tooltip>
                <Text type="secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                  {fmtSize(att.file_size)}
                </Text>
              </Space>
              <Space size={4}>
                {isPreviewable(att.mime_type) && (
                  <Button size="small" type="link" icon={<EyeOutlined />} onClick={() => handlePreview(att)} style={{ padding: '0 4px' }}>
                    预览
                  </Button>
                )}
                <Button size="small" type="link" icon={<DownloadOutlined />}
                  href={attachmentDownloadUrl(contractId!, att.id)} download={att.original_name}
                  style={{ padding: '0 4px' }}>
                  下载
                </Button>
                <Button size="small" type="link" danger icon={<DeleteOutlined />}
                  onClick={() => handleDelete(att)} style={{ padding: '0 4px' }} />
              </Space>
            </div>
          ))}
        </div>
      )}

      {/* 上传区 */}
      <Upload
        accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.gif"
        showUploadList={false}
        multiple
        beforeUpload={(file) => { handleUpload(file); return false }}
      >
        <Button icon={<PaperClipOutlined />} loading={uploading} size="small">
          {uploading ? '上传中...' : '添加附件'}
        </Button>
      </Upload>
      <div style={{ color: '#aaa', fontSize: 11, marginTop: 4 }}>
        支持 PDF、Word、Excel、图片；PDF 和图片支持在线预览
      </div>

      {/* 图片预览 Modal */}
      {previewIsImage ? (
        <Image
          style={{ display: 'none' }}
          preview={{
            visible: previewVisible,
            src: previewUrl,
            onVisibleChange: setPreviewVisible,
          }}
        />
      ) : (
        <Modal
          open={previewVisible}
          title={previewTitle}
          footer={
            <Button type="primary" onClick={() => setPreviewVisible(false)}>关闭</Button>
          }
          onCancel={() => setPreviewVisible(false)}
          width="80%"
          style={{ top: 20 }}
          styles={{ body: { padding: 0, height: '75vh' } }}
        >
          <iframe
            src={previewUrl}
            style={{ width: '100%', height: '100%', border: 'none' }}
            title={previewTitle}
          />
        </Modal>
      )}
      {/* 隐藏 input 用于触发文件选择 */}
      <input ref={fileInputRef} type="file" style={{ display: 'none' }} />
    </div>
  )
}

// ── 默认表单值 ────────────────────────────────────────────────────
const defaultDraftValues = {
  project_id: undefined as number | undefined,
  package_no: '1',
  contract_number: '',
  contract_name: '',
  supplier_name: '',
  supplier_address: '',
  supplier_contact: '',
  supplier_legal_rep: '',
  amount_is_text: 0,
  amount: undefined as number | undefined,
  amount_text: '',
  notes: '',
}

const defaultUploadValues = {
  sign_date: '',
  service_start: '',
  service_end: '',
  notes: '',
}

export default function ContractPage() {
  const { message, modal } = App.useApp()
  const [contracts, setContracts] = useState<Contract[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [tabStatus, setTabStatus] = useState<'合同草案' | '合同上传'>('合同草案')

  // ── 草案 Drawer ────────────────────────────────────────────────
  const [draftOpen, setDraftOpen] = useState(false)
  const [draftId, setDraftId] = useState<number | null>(null)
  const [draftSaving, setDraftSaving] = useState(false)
  const [draftForm] = Form.useForm()
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [amountIsText, setAmountIsText] = useState(0)
  const [amountWarning, setAmountWarning] = useState('')

  // ── 上传 Drawer ────────────────────────────────────────────────
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadId, setUploadId] = useState<number | null>(null)
  const [uploadSaving, setUploadSaving] = useState(false)
  const [uploadForm] = Form.useForm()
  const [uploadContract, setUploadContract] = useState<Contract | null>(null)

  // ── 主合同文件上传 ────────────────────────────────────────────
  const [mainUploading, setMainUploading] = useState(false)

  // ── 数据加载 ──────────────────────────────────────────────────
  const loadContracts = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listContracts()
      setContracts(res.data.data || [])
    } catch { message.error('加载合同列表失败') }
    finally { setLoading(false) }
  }, [message])

  useEffect(() => {
    loadContracts()
    getProjects().then(r => setProjects(r.data.data || []))
  }, [loadContracts])

  const filtered = contracts.filter(c => c.status === tabStatus)
  const projectMap = Object.fromEntries(projects.map(p => [p.id, p]))

  // ── 打开草案 Drawer ───────────────────────────────────────────
  const openDraftCreate = () => {
    setDraftId(null)
    setSelectedProject(null)
    setAmountIsText(0)
    setAmountWarning('')
    draftForm.resetFields()
    draftForm.setFieldsValue({ ...defaultDraftValues })
    setDraftOpen(true)
  }

  const openDraftEdit = (record: Contract) => {
    setDraftId(record.id)
    const proj = projectMap[record.project_id] || null
    setSelectedProject(proj)
    setAmountIsText(record.amount_is_text)
    setAmountWarning('')
    draftForm.resetFields()
    draftForm.setFieldsValue({
      project_id: record.project_id,
      package_no: record.package_no,
      contract_number: record.contract_number,
      contract_name: record.contract_name,
      supplier_name: record.supplier_name,
      supplier_address: record.supplier_address,
      supplier_contact: record.supplier_contact,
      supplier_legal_rep: record.supplier_legal_rep,
      amount_is_text: record.amount_is_text,
      amount: record.amount ?? undefined,
      amount_text: record.amount_text,
      notes: record.notes,
    })
    setDraftOpen(true)
  }

  // ── 打开上传 Drawer ───────────────────────────────────────────
  const openUploadEdit = (record: Contract) => {
    setUploadId(record.id)
    setUploadContract(record)
    uploadForm.resetFields()
    uploadForm.setFieldsValue({
      sign_date: record.sign_date,
      service_start: record.service_start,
      service_end: record.service_end,
      notes: record.notes,
    })
    setUploadOpen(true)
  }

  // ── 项目选择自动填充 ──────────────────────────────────────────
  const handleProjectChange = (pid: number) => {
    const proj = projectMap[pid] || null
    setSelectedProject(proj)
    if (!proj) return
    const pkgNo = draftForm.getFieldValue('package_no') || '1'
    draftForm.setFieldsValue({
      contract_name: proj.name,
      contract_number: `${proj.number}-${pkgNo}-HT`,
    })
    setAmountWarning('')
  }

  const handlePackageNoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const pkgNo = e.target.value || '1'
    if (selectedProject) {
      draftForm.setFieldsValue({ contract_number: `${selectedProject.number}-${pkgNo}-HT` })
    }
  }

  const handleAmountChange = (val: number | null) => {
    if (!selectedProject?.amount) { setAmountWarning(''); return }
    if (val != null && val > selectedProject.amount) {
      setAmountWarning(`超出项目预算 ¥${selectedProject.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
    } else {
      setAmountWarning('')
    }
  }

  // ── 保存草案 ──────────────────────────────────────────────────
  const handleSaveDraft = async () => {
    let values: Record<string, unknown>
    try { values = await draftForm.validateFields() } catch { return }
    setDraftSaving(true)
    try {
      if (draftId) {
        await updateContract(draftId, values as Partial<Contract>)
        message.success('保存成功')
      } else {
        await createContract(values as Partial<Contract>)
        message.success('新建成功')
      }
      setDraftOpen(false)
      loadContracts()
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || '保存失败')
    } finally { setDraftSaving(false) }
  }

  // ── 草案提交为合同上传 ────────────────────────────────────────
  const handleSubmitDraft = (record: Contract) => {
    modal.confirm({
      title: '提交为合同上传',
      content: `确认将「${record.contract_name}」提交为合同上传状态？`,
      onOk: async () => {
        try {
          await submitContract(record.id)
          message.success('已提交为合同上传')
          loadContracts()
          setDraftOpen(false)
        } catch (err: unknown) {
          const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
          message.error(errMsg || '操作失败')
        }
      },
    })
  }

  // ── 保存上传信息 ──────────────────────────────────────────────
  const handleSaveUpload = async () => {
    let values: Record<string, unknown>
    try { values = await uploadForm.validateFields() } catch { return }
    if (!uploadId) return
    setUploadSaving(true)
    try {
      await updateContract(uploadId, values as Partial<Contract>)
      message.success('保存成功')
      setUploadOpen(false)
      loadContracts()
    } catch { message.error('保存失败') }
    finally { setUploadSaving(false) }
  }

  // ── 撤回 ─────────────────────────────────────────────────────
  const handleRevoke = (record: Contract) => {
    modal.confirm({
      title: '撤回为合同草案',
      content: `确认撤回「${record.contract_name}」？`,
      onOk: async () => {
        try {
          await revokeContract(record.id)
          message.success('已撤回为合同草案')
          loadContracts()
          setUploadOpen(false)
        } catch { message.error('操作失败') }
      },
    })
  }

  // ── 删除 ─────────────────────────────────────────────────────
  const handleDelete = (record: Contract) => {
    modal.confirm({
      title: '删除确认',
      content: `确定删除合同「${record.contract_name}」？此操作不可撤销。`,
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteContract(record.id)
          message.success('已删除')
          loadContracts()
        } catch { message.error('删除失败') }
      },
    })
  }

  // ── 主合同文件上传 ────────────────────────────────────────────
  const handleMainFileUpload = async (file: File, record: Contract) => {
    setMainUploading(true)
    try {
      await uploadContractFile(record.id, file)
      message.success('合同文件上传成功')
      loadContracts()
    } catch { message.error('上传失败') }
    finally { setMainUploading(false) }
  }

  // ── 草案列表列 ────────────────────────────────────────────────
  const draftColumns: ColumnsType<Contract> = [
    {
      title: '合同编号', dataIndex: 'contract_number', width: 185,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v || '—'}</Text>,
    },
    { title: '合同名称', dataIndex: 'contract_name', ellipsis: true },
    {
      title: '项目编号', dataIndex: 'project_number', width: 130,
      render: (v: string) => v || '—',
    },
    {
      title: '包号', dataIndex: 'package_no', width: 55, align: 'center' as const,
    },
    {
      title: '成交供应商', dataIndex: 'supplier_name', width: 140, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: '合同金额', key: 'amount', width: 150,
      render: (_: unknown, r: Contract) => fmtAmount(r.amount, r.amount_is_text, r.amount_text),
    },
    {
      title: '创建时间', dataIndex: 'created_at', width: 120,
      render: (v: string) => v ? v.replace('T', ' ').slice(0, 16) : '—',
    },
    {
      title: '操作', key: 'actions', width: 210,
      render: (_: unknown, r: Contract) => (
        <Space size={4} wrap>
          <Button size="small" icon={<EditOutlined />} onClick={() => openDraftEdit(r)}>编辑</Button>
          <Button size="small" type="primary" icon={<CheckCircleOutlined />}
            onClick={() => handleSubmitDraft(r)}>提交上传</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
        </Space>
      ),
    },
  ]

  // ── 上传列表列 ────────────────────────────────────────────────
  const uploadColumns: ColumnsType<Contract> = [
    {
      title: '合同编号', dataIndex: 'contract_number', width: 185,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v || '—'}</Text>,
    },
    { title: '合同名称', dataIndex: 'contract_name', ellipsis: true },
    {
      title: '项目编号', dataIndex: 'project_number', width: 130,
      render: (v: string) => v || '—',
    },
    {
      title: '成交供应商', dataIndex: 'supplier_name', width: 140, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: '合同金额', key: 'amount', width: 150,
      render: (_: unknown, r: Contract) => fmtAmount(r.amount, r.amount_is_text, r.amount_text),
    },
    {
      title: '签订时间', dataIndex: 'sign_date', width: 115,
      render: (v: string) => v || <Text type="secondary">待填写</Text>,
    },
    {
      title: '服务期限', key: 'service', width: 200,
      render: (_: unknown, r: Contract) => {
        if (r.project_category !== '服务') return <Text type="secondary">—</Text>
        if (!r.service_start && !r.service_end) return <Text type="secondary">待填写</Text>
        return <span style={{ fontSize: 12 }}>{r.service_start} 至 {r.service_end}</span>
      },
    },
    {
      title: '合同文件', key: 'file', width: 130,
      render: (_: unknown, r: Contract) => r.file_name ? (
        <Tooltip title={r.file_name}>
          <Button size="small" type="link" icon={<DownloadOutlined />}
            onClick={() => window.open(contractFileUrl(r.id), '_blank')} style={{ padding: 0 }}>
            下载
          </Button>
        </Tooltip>
      ) : <Text type="secondary" style={{ fontSize: 12 }}>待上传</Text>,
    },
    {
      title: '操作', key: 'actions', width: 250,
      render: (_: unknown, r: Contract) => (
        <Space size={4} wrap>
          <Button size="small" icon={<EditOutlined />} onClick={() => openUploadEdit(r)}>编辑信息</Button>
          <Upload accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png" showUploadList={false}
            beforeUpload={file => { handleMainFileUpload(file, r); return false }}>
            <Button size="small" icon={<UploadOutlined />} loading={mainUploading}>
              {r.file_name ? '重新上传' : '上传合同'}
            </Button>
          </Upload>
          <Button size="small" icon={<RollbackOutlined />} onClick={() => handleRevoke(r)}>撤回</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title={<span style={{ fontWeight: 700, fontSize: 16 }}>合同管理</span>}
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={openDraftCreate}>新建合同</Button>}
    >
      <Tabs activeKey={tabStatus} onChange={k => setTabStatus(k as '合同草案' | '合同上传')}
        items={[
          { key: '合同草案', label: <span>合同草案 <Tag color="blue">{contracts.filter(c => c.status === '合同草案').length}</Tag></span> },
          { key: '合同上传', label: <span>合同上传 <Tag color="green">{contracts.filter(c => c.status === '合同上传').length}</Tag></span> },
        ]}
      />
      <Table rowKey="id" dataSource={filtered}
        columns={tabStatus === '合同草案' ? draftColumns : uploadColumns}
        loading={loading} size="small"
        pagination={{ pageSize: 15, showTotal: t => `共 ${t} 条` }}
        scroll={{ x: tabStatus === '合同草案' ? 1050 : 1350 }}
      />

      {/* ══ 草案 Drawer ══════════════════════════════════════════════ */}
      <Drawer
        title={draftId ? '编辑合同草案' : '新建合同草案'}
        open={draftOpen}
        onClose={() => setDraftOpen(false)}
        width={880}
        destroyOnClose
        extra={
          <Space>
            <Button onClick={() => setDraftOpen(false)}>取消</Button>
            <Button icon={<SaveOutlined />} loading={draftSaving} onClick={handleSaveDraft} type="primary">
              保存草案
            </Button>
          </Space>
        }
      >
        <Form form={draftForm} layout="vertical" initialValues={defaultDraftValues}>

          {/* ── 合同信息 ── */}
          <Card title="合同信息" size="small" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={24}>
                <Form.Item name="project_id" label="绑定项目" rules={[{ required: true, message: '请选择项目' }]}>
                  <Select showSearch placeholder="请选择项目（支持搜索）" onChange={handleProjectChange}
                    filterOption={(input, option) => (option?.label as string ?? '').toLowerCase().includes(input.toLowerCase())}
                    options={projects.map(p => ({ value: p.id, label: `${p.number ? p.number + ' — ' : ''}${p.name}` }))}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={5}>
                <Form.Item name="package_no" label="包号">
                  <Input placeholder="1" onChange={handlePackageNoChange} />
                </Form.Item>
              </Col>
              <Col span={19}>
                <Form.Item name="contract_number" label="合同编号"
                  extra={<span style={{ fontSize: 11, color: '#aaa' }}>格式：项目编号-包号-HT，可手动修改</span>}>
                  <Input placeholder="自动生成" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="contract_name" label="合同名称" rules={[{ required: true, message: '请填写合同名称' }]}>
              <Input placeholder="默认使用项目名称" />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="supplier_name" label="成交供应商名称" rules={[{ required: true, message: '请填写供应商名称' }]}>
                  <Input placeholder="成交供应商全称" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="supplier_legal_rep" label="法定代表人">
                  <Input placeholder="法人姓名" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="supplier_address" label="供应商地址">
                  <Input placeholder="注册地址" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="supplier_contact" label="联系方式">
                  <Input placeholder="电话/传真" />
                </Form.Item>
              </Col>
            </Row>

            {/* 合同金额 */}
            <Form.Item name="amount_is_text" label="合同金额">
              <Radio.Group onChange={e => setAmountIsText(e.target.value)}>
                <Radio value={0}>数字金额</Radio>
                <Radio value={1}>文字金额（按单价/据实结算等）</Radio>
              </Radio.Group>
            </Form.Item>
            {amountIsText === 0 ? (
              <Form.Item name="amount"
                label={selectedProject?.amount != null
                  ? <span>金额（元） <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>项目预算：¥{selectedProject.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</Text></span>
                  : '金额（元）'}
                validateStatus={amountWarning ? 'warning' : ''}
                help={amountWarning ? <span style={{ color: '#fa8c16' }}>{amountWarning}</span> : undefined}
              >
                <InputNumber<number>
                  style={{ width: '60%' }} min={0} precision={2} step={1000} prefix="¥"
                  formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={v => parseFloat((v ?? '').replace(/,/g, '')) || 0}
                  onChange={handleAmountChange} placeholder="请输入合同金额"
                />
              </Form.Item>
            ) : (
              <Form.Item name="amount_text" label="金额说明">
                <Input placeholder="如：按招标单价结算，实际数量据实结算" />
              </Form.Item>
            )}

            <Form.Item name="notes" label="备注">
              <TextArea rows={2} placeholder="其他备注信息" />
            </Form.Item>
          </Card>

          {/* ── 草案附件 ── */}
          <Card
            title={<Space><PaperClipOutlined />草案附件</Space>}
            size="small"
            style={{ marginBottom: 16 }}
          >
            {draftId ? (
              <AttachmentPanel contractId={draftId} stage="草案" />
            ) : (
              <Text type="secondary" style={{ fontSize: 13 }}>
                💡 保存合同草案后，可在此上传相关附件（草稿合同、意向书等）
              </Text>
            )}
          </Card>

          {/* ── 提交提示 ── */}
          {draftId && (
            <div style={{ textAlign: 'center', paddingBottom: 8 }}>
              <Button
                type="primary" ghost icon={<CheckCircleOutlined />}
                onClick={() => {
                  const record = contracts.find(c => c.id === draftId)
                  if (record) handleSubmitDraft(record)
                }}
              >
                提交为合同上传
              </Button>
              <div style={{ color: '#aaa', fontSize: 12, marginTop: 6 }}>
                提交后可在「合同上传」页填写签订时间、上传正式合同文件
              </div>
            </div>
          )}
        </Form>
      </Drawer>

      {/* ══ 合同上传 Drawer ══════════════════════════════════════════ */}
      <Drawer
        title={
          <Space>
            <span>合同上传</span>
            {uploadContract && <Text code style={{ fontSize: 12 }}>{uploadContract.contract_number}</Text>}
          </Space>
        }
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        width={880}
        destroyOnClose
        extra={
          <Space>
            <Button onClick={() => setUploadOpen(false)}>取消</Button>
            <Button icon={<RollbackOutlined />}
              onClick={() => uploadContract && handleRevoke(uploadContract)}>
              撤回为草案
            </Button>
            <Button type="primary" icon={<SaveOutlined />}
              loading={uploadSaving} onClick={handleSaveUpload}>
              保存
            </Button>
          </Space>
        }
      >
        {uploadContract && (
          <>
            {/* 合同基本信息（只读展示） */}
            <div style={{
              background: '#f6f8fc', borderRadius: 8, padding: '12px 16px',
              marginBottom: 16, border: '1px solid #e8eef5'
            }}>
              <Row gutter={[16, 4]}>
                <Col span={12}><Text type="secondary">合同名称：</Text><Text strong>{uploadContract.contract_name}</Text></Col>
                <Col span={12}><Text type="secondary">成交供应商：</Text><Text>{uploadContract.supplier_name || '—'}</Text></Col>
                <Col span={12}><Text type="secondary">合同金额：</Text><Text>{fmtAmount(uploadContract.amount, uploadContract.amount_is_text, uploadContract.amount_text)}</Text></Col>
                <Col span={12}><Text type="secondary">项目编号：</Text><Text code style={{ fontSize: 12 }}>{uploadContract.project_number}</Text></Col>
              </Row>
            </div>

            <Form form={uploadForm} layout="vertical" initialValues={defaultUploadValues}>

              {/* ── 签订信息 ── */}
              <Card title="签订信息" size="small" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="sign_date" label="合同签订时间" rules={[{ required: true, message: '请填写签订时间' }]}>
                      <Input placeholder="如：2026年5月30日" />
                    </Form.Item>
                  </Col>
                </Row>
                {uploadContract.project_category === '服务' && (
                  <>
                    <Divider style={{ margin: '4px 0 12px' }} />
                    <div style={{ marginBottom: 8, color: '#666', fontSize: 13 }}>服务期限</div>
                    <Row gutter={16}>
                      <Col span={12}>
                        <Form.Item name="service_start" label="开始日期">
                          <Input placeholder="如：2026年6月1日" />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name="service_end" label="结束日期">
                          <Input placeholder="如：2027年5月31日" />
                        </Form.Item>
                      </Col>
                    </Row>
                  </>
                )}
                <Form.Item name="notes" label="备注">
                  <TextArea rows={2} placeholder="其他备注" />
                </Form.Item>
              </Card>

              {/* ── 正式合同文件 ── */}
              <Card title="正式合同文件" size="small" style={{ marginBottom: 16 }}>
                {uploadContract.file_name ? (
                  <Space>
                    <FilePdfOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />
                    <span style={{ fontSize: 13 }}>{uploadContract.file_name}</span>
                    <Button size="small" type="link" icon={<DownloadOutlined />}
                      onClick={() => window.open(contractFileUrl(uploadContract.id), '_blank')}>下载</Button>
                    <Upload accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png" showUploadList={false}
                      beforeUpload={file => { handleMainFileUpload(file, uploadContract); return false }}>
                      <Button size="small" icon={<UploadOutlined />} loading={mainUploading}>重新上传</Button>
                    </Upload>
                  </Space>
                ) : (
                  <Space direction="vertical" size={4}>
                    <Upload accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png" showUploadList={false}
                      beforeUpload={file => { handleMainFileUpload(file, uploadContract); return false }}>
                      <Button icon={<UploadOutlined />} loading={mainUploading}>上传正式合同文件</Button>
                    </Upload>
                    <Text type="secondary" style={{ fontSize: 12 }}>支持 PDF、Word、Excel、图片</Text>
                  </Space>
                )}
              </Card>

              {/* ── 合同上传附件 ── */}
              <Card title={<Space><PaperClipOutlined />合同上传附件</Space>} size="small">
                <AttachmentPanel contractId={uploadId} stage="上传" />
              </Card>
            </Form>
          </>
        )}
      </Drawer>
    </Card>
  )
}
