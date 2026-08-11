import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  Button, Drawer, Form, Input, Select, Radio, InputNumber,
  Card, Space, Tag, Tabs, App, Typography, Row, Col, Upload, Tooltip,
  Divider, Modal, Descriptions, Alert,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined,
  RollbackOutlined, SaveOutlined, UploadOutlined, DownloadOutlined,
  EyeOutlined, FilePdfOutlined, FileWordOutlined, FileExcelOutlined,
  FileImageOutlined, FileOutlined, PaperClipOutlined, StopOutlined,
} from '@ant-design/icons'
import RecordCards from '../components/RecordCards'
import PendingOwnerTag from '../components/PendingOwnerTag'
import HermesPanel, { type HermesField } from '../components/HermesPanel'
import ProjectListToolbar, { useProjectListFilter, type ListFilterAccessors } from '../components/ProjectListToolbar'
import {
  listContracts, createContract, updateContract, deleteContract,
  submitContract, revokeContract, rejectContract,
  contractFileUrl, contractFilePreviewUrl, uploadContractFile,
  listAttachments, uploadAttachment, deleteAttachment,
  attachmentDownloadUrl, attachmentPreviewUrl,
  type Contract, type ContractAttachment,
} from '../services/contract'
import { getProjects, type Project } from '../services/project'
import { useAuth } from '../hooks/useAuth'
import { useFocusTarget, flashRow } from '../hooks/useFocusRow'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'

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
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })
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
    setPreview({ open: true, url: attachmentPreviewUrl(contractId!, att.id), name: att.original_name })
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
                {isPreviewable(att.original_name) && (
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
        支持 PDF、Word、Excel、图片；均可在线预览
      </div>

      {/* 在线预览（PDF/图片/Word/Excel/文本） */}
      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />
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
  const { user } = useAuth()
  // 确认合同（草案→合同上传）/撤回由采购人方完成，代理机构只能上传合同草案
  const canConfirm = ['officer', 'assistant', 'leader'].includes(user?.role || '')
  const isAgency = user?.role === 'agency'
  const [contracts, setContracts] = useState<Contract[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [tabStatus, setTabStatus] = useState<'合同草案' | '审核完成' | '合同上传'>('合同草案')
  // 驳回弹窗（审核完成 → 打回合同草案）
  const [rejectRow, setRejectRow] = useState<Contract | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  // 点合同名/合同文件：在线预览盖章合同
  const [docPreview, setDocPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })
  // 合同详情只读弹窗：审核完成/合同上传后仍可点项目名查看草案录入的全部内容
  const [detailC, setDetailC] = useState<Contract | null>(null)
  const [detailAtts, setDetailAtts] = useState<ContractAttachment[]>([])
  // rd-web 合同审签字段（标签须与 rd-web 表单一致，供 Hermes 自动填报）。
  // 经办人/归口科室自动取项目；合同编码按规则；甲方为本院固定值。
  const contractFields = useMemo<HermesField[]>(() => {
    if (!detailC) return []
    const proj = projects.find(p => p.id === detailC.project_id)
    const pkgLabel = `${detailC.project_name || ''}　包${detailC.package_no || '1'}`
    return [
      { label: '合同名称', value: detailC.contract_name || '', long: true },
      { label: '合同编码', value: detailC.contract_number || '' },
      { label: '项目名称及包号', value: pkgLabel, long: true },
      { label: '归口管理科室', value: proj?.manage_dept || '' },
      { label: '合同金额', value: detailC.amount_is_text ? (detailC.amount_text || '') : (detailC.amount != null ? `${detailC.amount}元` : '') },
      { label: '合同甲方', value: '内江市第一人民医院', readOnly: true },
      { label: '甲方法定代表人', value: '谢晓阳', readOnly: true },
      { label: '甲方联系电话', value: '0832-2256120', readOnly: true },
      { label: '甲方地址', value: '四川省内江市市中区沱中路41号、汉安大道西段1866号', readOnly: true },
      { label: '合同乙方', value: detailC.supplier_name || '' },
      { label: '乙方法定代表人', value: detailC.supplier_legal_rep || '' },
      { label: '乙方联系电话', value: detailC.supplier_contact || '' },
      { label: '乙方地址', value: detailC.supplier_address || '', long: true },
      { label: '合同类别', value: '采购部合同', readOnly: true },
      { label: '经办人', value: proj?.officer || '' },
    ]
  }, [detailC, projects])
  useEffect(() => {
    if (!detailC) { setDetailAtts([]); return }
    listAttachments(detailC.id).then(r => setDetailAtts(r.data.data || [])).catch(() => setDetailAtts([]))
  }, [detailC])

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

  const projectMap = Object.fromEntries(projects.map(p => [p.id, p]))
  const tabContracts = useMemo(
    () => contracts.filter(c => c.status === tabStatus), [contracts, tabStatus])
  // 合同模块：搜索多一个「供应商」；采购方式取所属项目
  const contractAccessors = useMemo<ListFilterAccessors<Contract>>(() => ({
    searchText: c => [c.contract_name, c.contract_number, c.project_name,
                      c.supplier_name, projectMap[c.project_id]?.number],
    createdAt: c => c.created_at,
    number: c => projectMap[c.project_id]?.number || c.contract_number,
    method: c => projectMap[c.project_id]?.method,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [projects])
  const listFilter = useProjectListFilter(tabContracts, contractAccessors)
  const filtered = listFilter.filtered

  // 可签合同的项目：存在「已中标未签约」的包（pending_contract>0）。
  // 全量 projects 仍用于表格项目名映射；编辑既有合同时把已绑定项目补进下拉。
  const watchedPid = Form.useWatch('project_id', draftForm)
  const contractOptions = projects.filter(p => (p.pending_contract ?? 0) > 0)
  if (watchedPid && !contractOptions.some(p => p.id === watchedPid)) {
    const bound = projectMap[watchedPid]
    if (bound) contractOptions.unshift(bound)
  }

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
  // 合同编码规则：单包 = 项目编号-HT；多包 = 项目编号-包N-HT（采购部约定）
  const deriveContractNo = (proj: Project, pkgNo: string) =>
    (proj.package_count ?? 1) <= 1 ? `${proj.number}-HT` : `${proj.number}-包${pkgNo}-HT`

  const handleProjectChange = (pid: number) => {
    const proj = projectMap[pid] || null
    setSelectedProject(proj)
    if (!proj) return
    const pkgNo = draftForm.getFieldValue('package_no') || '1'
    draftForm.setFieldsValue({
      contract_name: proj.name,
      contract_number: deriveContractNo(proj, pkgNo),
    })
    setAmountWarning('')
  }

  const handlePackageNoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const pkgNo = e.target.value || '1'
    if (selectedProject) {
      draftForm.setFieldsValue({ contract_number: deriveContractNo(selectedProject, pkgNo) })
    }
  }

  // 待办「去处理」跳转：已有合同→切到其状态页签并高亮；否则打开新建草案并预选项目
  useFocusTarget(!loading && projects.length > 0, (id) => {
    const existing = contracts.find(c => c.project_id === id)
    if (existing) {
      setTabStatus(existing.status as '合同草案' | '审核完成' | '合同上传')
      flashRow(existing.id)
    } else {
      openDraftCreate()
      draftForm.setFieldsValue({ project_id: id })
      handleProjectChange(id)
    }
  })

  const handleAmountChange = (val: number | null) => {
    if (!selectedProject?.amount) { setAmountWarning(''); return }
    if (val != null && val > selectedProject.amount) {
      setAmountWarning(`超出项目预算 ¥${selectedProject.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
    } else {
      setAmountWarning('')
    }
  }

  // ── 保存草案 / 保存并提交审核 ─────────────────────────────────
  // thenSubmit=true：填好必填项后一步「自动保存 + 提交审核」，避免代理漏掉单独提交
  const handleSaveDraft = async (thenSubmit = false) => {
    let values: Record<string, unknown>
    try { values = await draftForm.validateFields() } catch { return }
    setDraftSaving(true)
    try {
      let cid = draftId
      if (draftId) {
        await updateContract(draftId, values as Partial<Contract>)
      } else {
        const res = await createContract(values as Partial<Contract>)
        cid = (res.data as { data?: { id?: number } })?.data?.id ?? null
      }
      if (thenSubmit && cid) {
        await submitContract(cid)
        message.success('已保存并提交审核，合同草案 → 审核完成')
      } else {
        message.success(draftId ? '保存成功' : '新建成功')
      }
      setDraftOpen(false)
      loadContracts()
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(errMsg || (thenSubmit ? '提交失败' : '保存失败'))
    } finally { setDraftSaving(false) }
  }

  // ── 草案提交审核（合同草案 → 审核完成）─────────────────────────
  const handleSubmitDraft = (record: Contract) => {
    modal.confirm({
      title: '提交审核',
      content: `确认将「${record.contract_name}」提交审核？提交后由经办人审核，合同草案 → 审核完成。`,
      onOk: async () => {
        try {
          await submitContract(record.id)
          message.success('已提交，合同草案 → 审核完成')
          loadContracts()
          setDraftOpen(false)
        } catch (err: unknown) {
          const errMsg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
          message.error(errMsg || '操作失败')
        }
      },
    })
  }

  // ── 完成归档（审核完成 → 合同上传）：上传盖章合同后确认 ─────────
  const handleFinalize = (record: Contract) => {
    modal.confirm({
      title: '完成归档',
      content: `确认「${record.contract_name}」盖章合同已上传，完成归档？归档后状态变为「合同上传」。`,
      onOk: async () => {
        try {
          await submitContract(record.id)
          message.success('已完成归档')
          loadContracts()
          setUploadOpen(false)
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

  // ── 撤回（逆向回退一步：合同上传→审核完成→合同草案）──────────
  const handleRevoke = (record: Contract) => {
    const target = record.status === '合同上传' ? '审核完成' : '合同草案'
    modal.confirm({
      title: '撤回',
      content: `确认撤回「${record.contract_name}」？将回退至「${target}」。`,
      onOk: async () => {
        try {
          await revokeContract(record.id)
          message.success(`已撤回至${target}`)
          loadContracts()
          setUploadOpen(false)
        } catch { message.error('操作失败') }
      },
    })
  }

  // ── 驳回：退回合同草案，必须写明原因（记入审批过程记录）──────
  const handleReject = async () => {
    if (!rejectRow) return
    if (!rejectReason.trim()) { message.warning('请填写驳回原因'); return }
    try {
      const res = await rejectContract(rejectRow.id, rejectReason.trim())
      message.success(res.data.message || '已驳回')
      setRejectRow(null); setRejectReason('')
      loadContracts()
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '驳回失败')
    }
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

  // ── 合同 → 卡片数据 ──────────────────────────────────────────
  const ACCENT: Record<string, string> = { 合同草案: '#1a73e8', 审核完成: '#f9ab00', 合同上传: '#34a853' }
  const STATUS_COLOR: Record<string, string> = { 合同草案: 'blue', 审核完成: 'gold', 合同上传: 'green' }
  const contractToCard = (r: Contract) => {
    const isDraft = tabStatus === '合同草案'
    const fields = isDraft
      ? [
          { label: '项目编号', value: r.project_number },
          { label: '包号', value: r.package_no },
          { label: '成交供应商', value: r.supplier_name },
          { label: '合同金额', value: fmtAmount(r.amount, r.amount_is_text, r.amount_text) },
          { label: '创建时间', value: r.created_at ? r.created_at.replace('T', ' ').slice(0, 16) : '' },
        ]
      : [
          { label: '项目编号', value: r.project_number },
          { label: '成交供应商', value: r.supplier_name },
          { label: '合同金额', value: fmtAmount(r.amount, r.amount_is_text, r.amount_text) },
          { label: '签订时间', value: r.sign_date || '待填写' },
          {
            label: '合同文件',
            value: r.file_name ? (
              <Tooltip title={r.file_name}>
                <a onClick={() => setDocPreview({ open: true, url: contractFilePreviewUrl(r.id), name: r.file_name })}>查看</a>
              </Tooltip>
            ) : '待上传',
          },
        ]
    fields.unshift({ label: '当前处理人', value: <PendingOwnerTag p={r.pending} compact /> })
    // 推送审签的结果要看得见——否则推完不知道有没有成、到哪一步了
    fields.push({
      label: '审签推送',
      value: r.rdweb_serial_no
        ? (
          <Space size={4} wrap>
            <Tag color="green" icon={<CheckCircleOutlined />} style={{ marginInlineEnd: 0 }}>
              已推送
            </Tag>
            <Typography.Text copyable={{ text: r.rdweb_serial_no }} style={{ fontSize: 12 }}>
              流水号 {r.rdweb_serial_no}
            </Typography.Text>
            {r.rdweb_submitted_at && (
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                {r.rdweb_submitted_at.replace('T', ' ').slice(0, 16)}
              </Typography.Text>
            )}
          </Space>
        )
        : <Typography.Text type="secondary" style={{ fontSize: 12 }}>未推送</Typography.Text>,
    })
    if (r.reject_reason && r.status === '合同草案') {
      fields.push({
        label: `驳回原因${(r.reject_count || 0) > 1 ? `（第${r.reject_count}次）` : ''}`,
        value: <Typography.Text type="danger">{r.reject_reason}</Typography.Text>,
      })
    }
    const actions = isDraft ? (
      <>
        <Button size="small" icon={<EditOutlined />} onClick={() => openDraftEdit(r)}>编辑</Button>
        {/* 草案由代理机构拟并提交，经办人也可代提交 */}
        {(canConfirm || isAgency) && (
          <Button size="small" type="primary" ghost icon={<CheckCircleOutlined />} onClick={() => handleSubmitDraft(r)}>
            {r.reject_reason ? '修改后重新提交' : '提交审核'}
          </Button>
        )}
        <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
      </>
    ) : (
      <>
        <Button size="small" icon={<EditOutlined />} onClick={() => openUploadEdit(r)}>编辑信息</Button>
        <Upload accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png" showUploadList={false}
          beforeUpload={file => { handleMainFileUpload(file, r); return false }}>
          <Button size="small" icon={<UploadOutlined />} loading={mainUploading}>
            {r.file_name ? '重新上传盖章合同' : '上传盖章合同'}
          </Button>
        </Upload>
        {canConfirm && r.status === '审核完成' && (
          <>
            <Button size="small" type="primary" ghost icon={<CheckCircleOutlined />} onClick={() => handleFinalize(r)}>完成归档</Button>
            <Tooltip title="合同内容有问题，退回合同草案并写明要改什么">
              <Button size="small" danger ghost icon={<StopOutlined />}
                onClick={() => { setRejectRow(r); setRejectReason('') }}>驳回</Button>
            </Tooltip>
          </>
        )}
        {canConfirm && (
          <Button size="small" icon={<RollbackOutlined />} onClick={() => handleRevoke(r)}>撤回</Button>
        )}
        <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
      </>
    )
    return {
      key: r.id,
      accent: ACCENT[r.status] || '#1a73e8',
      title: (
        <a style={{ color: '#202124', fontWeight: 600 }} onClick={() => setDetailC(r)}>
          {r.contract_name}
        </a>
      ),
      subtitle: r.contract_number || '—',
      statusText: r.status,
      statusColor: STATUS_COLOR[r.status],
      tags: (
        <>
          <Tag bordered={false}>包 {r.package_no}</Tag>
          {r.project_category && <Tag bordered={false} color="geekblue">{r.project_category}</Tag>}
        </>
      ),
      fields,
      meta: r.created_at ? `创建于 ${r.created_at.replace('T', ' ').slice(0, 16)}` : undefined,
      actions,
    }
  }

  return (
    <Card
      title={<span style={{ fontWeight: 700, fontSize: 16 }}>合同管理</span>}
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={openDraftCreate}>新建合同</Button>}
    >
      <Tabs activeKey={tabStatus} onChange={k => setTabStatus(k as '合同草案' | '审核完成' | '合同上传')}
        items={[
          { key: '合同草案', label: <span>合同草案 <Tag color="blue">{contracts.filter(c => c.status === '合同草案').length}</Tag></span> },
          { key: '审核完成', label: <span>审核完成 <Tag color="gold">{contracts.filter(c => c.status === '审核完成').length}</Tag></span> },
          { key: '合同上传', label: <span>合同上传（归档）<Tag color="green">{contracts.filter(c => c.status === '合同上传').length}</Tag></span> },
        ]}
      />
      <div style={{ marginBottom: 12 }}>
        <ProjectListToolbar f={listFilter}
          placeholder="搜索合同 / 项目名称 / 编号 / 供应商" />
      </div>
      <RecordCards
        dataSource={filtered}
        loading={loading}
        emptyText="暂无合同"
        toCard={contractToCard}
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
            <Button icon={<SaveOutlined />} loading={draftSaving} onClick={() => handleSaveDraft(false)}>
              保存草案
            </Button>
            <Button icon={<CheckCircleOutlined />} loading={draftSaving} onClick={() => handleSaveDraft(true)} type="primary">
              保存并提交审核
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
                    options={contractOptions.map(p => ({ value: p.id, label: `${p.number ? p.number + ' — ' : ''}${p.name}` }))}
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
                  extra={<span style={{ fontSize: 11, color: '#aaa' }}>单包＝项目编号-HT；多包＝项目编号-包N-HT，可手动修改</span>}>
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
                {/* rd-web 合同审签单要求「乙方法定代表人」必填，空着推送会卡在提交页
                    不动且看不出原因，所以在录入这一步就挡住 */}
                <Form.Item name="supplier_legal_rep" label="法定代表人"
                  rules={[{ required: true, message: '必填：rd-web 审签单要求乙方法定代表人' }]}>
                  <Input placeholder="法人姓名（rd-web 审签必填）" />
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
                {/* 同上：rd-web 要求「乙方联系电话」必填 */}
                <Form.Item name="supplier_contact" label="联系方式"
                  rules={[{ required: true, message: '必填：rd-web 审签单要求乙方联系电话' }]}>
                  <Input placeholder="电话/传真（rd-web 审签必填）" />
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

          {/* ── 提交提示（确认合同由经办人完成，代理机构不显示） ── */}
          {draftId && canConfirm && (
            <div style={{ textAlign: 'center', paddingBottom: 8 }}>
              <Button
                type="primary" ghost icon={<CheckCircleOutlined />}
                onClick={() => {
                  const record = contracts.find(c => c.id === draftId)
                  if (record) handleSubmitDraft(record)
                }}
              >
                提交审核
              </Button>
              <div style={{ color: '#aaa', fontSize: 12, marginTop: 6 }}>
                提交后进入「审核完成」，再上传盖章合同并完成归档
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
            {canConfirm && (
              <Button icon={<RollbackOutlined />}
                onClick={() => uploadContract && handleRevoke(uploadContract)}>
                撤回为草案
              </Button>
            )}
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

      {/* 点合同名/合同文件：在线预览盖章合同 */}
      <FilePreviewModal
        open={docPreview.open}
        url={docPreview.url}
        filename={docPreview.name}
        onClose={() => setDocPreview((p) => ({ ...p, open: false }))}
      />

      {/* 合同详情（只读）：审核完成/合同上传后点项目名查看草案录入的全部内容 */}
      <Modal
        title={`合同详情 — ${detailC?.contract_name || ''}`}
        open={!!detailC}
        onCancel={() => setDetailC(null)}
        width={680}
        footer={
          <Space>
            {detailC?.file_name && (
              <Button icon={<EyeOutlined />} onClick={() => detailC && setDocPreview({ open: true, url: contractFilePreviewUrl(detailC.id), name: detailC.file_name })}>
                预览盖章合同
              </Button>
            )}
            <Button type="primary" onClick={() => setDetailC(null)}>关闭</Button>
          </Space>
        }
      >
        {detailC && (
          <Descriptions column={2} bordered size="small" labelStyle={{ width: 110 }}>
            <Descriptions.Item label="合同编号" span={2}><Text code>{detailC.contract_number || '—'}</Text></Descriptions.Item>
            <Descriptions.Item label="项目编号">{detailC.project_number || '—'}</Descriptions.Item>
            <Descriptions.Item label="包号">{detailC.package_no || '—'}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={STATUS_COLOR[detailC.status]}>{detailC.status}</Tag></Descriptions.Item>
            <Descriptions.Item label="合同金额">{fmtAmount(detailC.amount, detailC.amount_is_text, detailC.amount_text)}</Descriptions.Item>
            <Descriptions.Item label="成交供应商" span={2}>{detailC.supplier_name || '—'}</Descriptions.Item>
            <Descriptions.Item label="法定代表人">{detailC.supplier_legal_rep || '—'}</Descriptions.Item>
            <Descriptions.Item label="联系方式">{detailC.supplier_contact || '—'}</Descriptions.Item>
            <Descriptions.Item label="供应商地址" span={2}>{detailC.supplier_address || '—'}</Descriptions.Item>
            <Descriptions.Item label="签订时间">{detailC.sign_date || '—'}</Descriptions.Item>
            <Descriptions.Item label="服务期限">{(detailC.service_start || detailC.service_end) ? `${detailC.service_start || ''} 至 ${detailC.service_end || ''}` : '—'}</Descriptions.Item>
            <Descriptions.Item label="备注" span={2}>{detailC.notes || '—'}</Descriptions.Item>
          </Descriptions>
        )}
        {detailC && (
          <div style={{ marginTop: 14 }}>
            <HermesPanel taskType="procurement-contract" projectId={detailC.project_id}
              title={detailC.contract_name} fields={contractFields} contractId={detailC.id}
              directSubmitUrl={`/contracts/${detailC.id}/submit-to-rdweb`}
              directStatusUrl={`/contracts/${detailC.id}/rdweb-status`}
              autofillUrl={`/contracts/${detailC.id}/rdweb-autofill`} />
          </div>
        )}
        {detailC && (
          <div style={{ marginTop: 16 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>
              <PaperClipOutlined /> 相关附件（含代理机构上传的草案附件）
            </div>
            {detailAtts.length === 0 ? (
              <Text type="secondary" style={{ fontSize: 13 }}>暂无附件</Text>
            ) : (
              detailAtts.map(att => (
                <div key={att.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 10px', borderRadius: 6, marginBottom: 4,
                  background: '#fafafa', border: '1px solid #f0f0f0',
                }}>
                  <Space size={8} style={{ flex: 1, minWidth: 0 }}>
                    <FileTypeIcon mime={att.mime_type} />
                    <Tooltip title={att.original_name}>
                      <span style={{ fontSize: 13, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                        {att.original_name}
                      </span>
                    </Tooltip>
                    <Tag color={att.stage === '草案' ? 'blue' : 'green'}>{att.stage}</Tag>
                    <Text type="secondary" style={{ fontSize: 11 }}>{fmtSize(att.file_size)}</Text>
                  </Space>
                  <Space size={4}>
                    {isPreviewable(att.original_name) && (
                      <Button size="small" type="link" icon={<EyeOutlined />}
                        onClick={() => setDocPreview({ open: true, url: attachmentPreviewUrl(detailC.id, att.id), name: att.original_name })}>预览</Button>
                    )}
                    <Button size="small" type="link" icon={<DownloadOutlined />}
                      href={attachmentDownloadUrl(detailC.id, att.id)} download={att.original_name}>下载</Button>
                  </Space>
                </div>
              ))
            )}
          </div>
        )}
      </Modal>

      {/* ── 驳回合同 ─────────────────────────────────────────────── */}
      <Modal
        open={!!rejectRow}
        title={`驳回合同 — ${rejectRow?.contract_name || ''}`}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        onOk={handleReject}
        onCancel={() => { setRejectRow(null); setRejectReason('') }}
      >
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message="驳回后合同退回「合同草案」，编制方改完重新提交审核。驳回原因会记入审批过程记录，归档时随项目一并留存。" />
        <Input.TextArea
          rows={4} maxLength={500} showCount
          placeholder="请写明需要修改的具体内容，例如：合同金额与采购结果确认函不一致；服务期限未填写"
          value={rejectReason}
          onChange={e => setRejectReason(e.target.value)}
        />
      </Modal>
    </Card>
  )
}
