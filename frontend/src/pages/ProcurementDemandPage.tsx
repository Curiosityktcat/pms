import { useState, useEffect, useCallback } from 'react'
import {
  Table, Button, Drawer, Form, Input, Select, Radio, InputNumber,
  DatePicker, Card, Space, Tabs, Popconfirm, App, Typography,
  Row, Col, Tooltip, Modal, Badge, Alert, Upload, Tag,
} from 'antd'
import type { UploadProps } from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, FileWordOutlined,
  CheckCircleOutlined, RollbackOutlined, SendOutlined,
  ArrowRightOutlined, UserSwitchOutlined, PaperClipOutlined,
  UploadOutlined, DownloadOutlined, ImportOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import DemandDocPanel, { PreviewSizeToggle, type PreviewSize } from '../components/DemandDocPanel'
import DictFields from '../components/DictFields'
import PackageEditor, { emptyPackage, type PackageData } from '../components/PackageEditor'
import ProjectListToolbar, { useProjectListFilter, type ListFilterAccessors } from '../components/ProjectListToolbar'

const DEMAND_ACCESSORS: ListFilterAccessors<ProcurementDemand> = {
  searchText: d => [d.project_name, d.project_number],
  createdAt: d => d.created_at,
  number: d => d.project_number,
  method: d => d.procurement_method || d.budget_method,
}
import dayjs from 'dayjs'
import { useNavigate, useParams } from 'react-router-dom'
import {
  listDemands, createDemand, updateDemand, deleteDemand,
  submitDemand, recallDemand, dispatchDemand, returnDemand,
  getPrefillForProject, getAgencies, demandWordUrl, checkDemand,
  demandAttachmentUrl, uploadAttachment,
  demandTemplateUrl, importExcel,
  type ProcurementDemand, type DemandItem, type DemandStatus, type DemandType,
} from '../services/procurementDemand'
import { useAuth } from '../hooks/useAuth'

const { TextArea } = Input
const { Text } = Typography

// 字典里的中文字段名 ↔ 数据库列名。
// 字典用中文（Word 模板里也是中文占位符），模型用英文列，两头要对上。
// 只列走字典的那几项，其余仍由 antd Form 直接管。
const DICT_TO_MODEL: Record<string, string> = {
  采购组织形式: 'org_form',
  采购方式: 'budget_method',
  采购包划分: 'package_split',
  是否属于一签多年项目: 'is_multi_year',
  中小企业政策: 'sme_policy',
}
const MODEL_TO_DICT: Record<string, string> = Object.fromEntries(
  Object.entries(DICT_TO_MODEL).map(([k, v]) => [v, k]))

/** 库里的一条需求 → 字典那几项的初值 */
function toDictValues(rec: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  Object.entries(MODEL_TO_DICT).forEach(([col, name]) => {
    if (rec[col] !== undefined && rec[col] !== null && rec[col] !== '') out[name] = rec[col]
  })
  // 项目所属分类决定「一签多年」锁不锁，必须一起给字典
  if (rec.category) out['项目所属分类'] = rec.category
  return out
}

/** 库里的 packages_json → 分包编辑器的值。
 *  老数据没有分包，就用整条需求上的单值字段兜一个包出来，
 *  免得改造之后历史项目打开是空的。 */
function parsePackages(rec: Record<string, unknown>): PackageData[] {
  try {
    const raw = JSON.parse(String(rec.packages_json || '[]'))
    if (Array.isArray(raw) && raw.length) return raw as PackageData[]
  } catch { /* 坏数据就走下面的兜底 */ }
  return [{
    ...emptyPackage(),
    预算金额: (rec.budget_amount as number) || undefined,
    最高限价: (rec.max_price as number) || undefined,
    评审方法: (rec.eval_method as string) || '综合评分法',
    定价方式: (rec.pricing_method as string) || '固定单价',
    是否支持联合体投标: (rec.allow_consortium as string) || '否',
    是否允许合同分包: (rec.allow_subcontract as string) || '否',
    技术要求: (rec.tech_requirements as string) || '',
    商务要求: (rec.business_requirements as string) || '',
    特殊资格要求: (rec.qualification_requirements as string) || '',
  }]
}

/** 字典那几项 → 存库用的列 */
function fromDictValues(v: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  Object.entries(DICT_TO_MODEL).forEach(([name, col]) => {
    if (v[name] !== undefined) out[col] = v[name]
  })
  return out
}

type TabKey = '草稿' | '待分发' | '已分发' | '已立项'

// 预览宽度记在本地，下次打开还是上次那一档——反复调很烦
const PREVIEW_KEY = 'pms-demand-preview-size'

const STATUS_COLOR: Record<string, string> = {
  草稿: 'default', 待分发: 'orange', 已分发: 'blue', 已立项: 'green',
}

const TYPE_META: Record<string, { label: string; hint: string; defaultMethod: string }> = {
  gov:          { label: '政府采购',   hint: '政府采购（公开招标/竞谈/单一来源等），立项后自动归档', defaultMethod: '' },
  competition:  { label: '院内竞选',   hint: '5万(含)以上，通过代理机构组织竞选', defaultMethod: '院内竞选' },
  sole_source:  { label: '单一来源',   hint: '需专家论证及公示，可选是否走代理', defaultMethod: '院内单一来源' },
  inquiry:      { label: '询议价',     hint: '5万以下采购（询价 2-5万 / 议价 2万以下），简化表单', defaultMethod: '院内询价' },
  emergency:    { label: '紧急采购',   hint: '医用耗材紧急采购，申请→采购部分发→立项', defaultMethod: '紧急采购' },
}

// 询议价：通用资格要求固定条款（只读展示）
const STANDARD_QUALIFICATIONS = [
  '（一）具有独立承担民事责任的能力；',
  '（二）具有良好的商业信誉和健全的财务会计制度；',
  '（三）具有履行合同所必需的设备和专业技术能力；',
  '（四）具有依法缴纳税收和社会保障资金的良好记录；',
  '（五）参加本次采购活动前三年内，在经营活动中没有重大违法记录；',
  '（六）法律、行政法规规定的其他条件；',
  '（七）本项目不允许联合体参加；',
]

const SCOPE_OPTIONS = [
  { value: '1', label: '1. 直接严重影响医院教学、科研及临床工作' },
  { value: '2', label: '2. 病人就医的突发事件' },
  { value: '3', label: '3. 危急重症患者手术及抢救' },
  { value: '4', label: '4. 其他' },
]

const emptyItem = (): DemandItem => ({
  item_no: '', category: '', name: '', unit_price: 0,
  quantity: 0, unit: '台', amount: 0, requirements: '',
})

function makeDefault(dt: DemandType | ''): Partial<ProcurementDemand> {
  return {
    demand_type: (dt || 'competition') as DemandType,
    demand_dept: '', manage_dept: '医学装备部', project_name: '',
    year: `${new Date().getFullYear()}年`, compile_date: '',
    category: '货物', budget_amount: 0, project_overview: '',
    has_related_supplier: '否',
    survey_content: '',
    org_form: '', budget_method: '',
    procurement_method: TYPE_META[dt || 'competition']?.defaultMethod || '院内竞选',
    is_multi_year: '否', package_split: '不分包采购',
    sole_source_reason: '',
    items: [], max_price: 0,
    tech_requirements: '', business_requirements: '', qualification_requirements: '',
    eval_method: '', eval_price_score: 0, eval_tech_criteria: '', eval_service_criteria: '',
    contract_is_actual: '否', contract_period: '', payment_terms: '', breach_terms: '',
    acceptance_procedure: '', acceptance_time: '', acceptance_tech: '',
    acceptance_biz: '', acceptance_standard: '',
    risk_needed: '否', risk_measures: '',
    // 询议价
    inq_after_sales: '',
    inq_delivery_time: '',
    inq_delivery_location: '内江市汉安大道西段1866号',
    inq_performance_bond: '不收取',
    inq_other_requirements: '',
    // 紧急采购
    apply_time: '', expected_use_time: '', consumable_name: '',
    consumable_unit_price: 0, consumable_unit: '', apply_quantity: 1,
    manufacturer: '', model_spec: '', purpose_type: '',
    license_number: '', has_similar_product: '无', needs_companion: '无需',
    surgery_name: '', surgery_level: '', import_domestic: '',
    product_on_catalog: '', applicable_scope: '', clinical_use_desc: '',
    attachment_path: '',
    handler_name: '', manager_opinion: '', legal_opinion: '',
    audit_opinion: '', leader_opinion: '', cfo_opinion: '', president_opinion: '',
  }
}

export default function ProcurementDemandPage() {
  const { message, modal } = App.useApp()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { type } = useParams<{ type?: string }>()

  const demandType = (type || '') as DemandType | ''
  const isTyped      = !!demandType && demandType in TYPE_META
  const isGov         = demandType === 'gov'
  const isCompetition = demandType === 'competition'
  const isSoleSource  = demandType === 'sole_source'
  const isEmergency   = demandType === 'emergency'
  const isInquiry     = demandType === 'inquiry'
  const meta = isTyped ? TYPE_META[demandType] : null

  const role        = user?.role || ''
  const isAssistant = role === 'assistant' || role === 'leader'
  const isOfficer   = role === 'officer'
  const isDeptRole = ['dept', 'dept_manage', 'dept_demand'].includes(role)
  const permByType: Partial<Record<DemandType, string>> = {
    gov: 'procurement-demand-gov', sole_source: 'procurement-demand-sole',
    inquiry: 'procurement-demand-inquiry', emergency: 'procurement-demand-emergency',
  }
  const canWriteDemand = !isDeptRole || !!(permByType[demandType as DemandType]
    && user?.perms.includes(permByType[demandType as DemandType]!))

  const [demands,  setDemands]  = useState<ProcurementDemand[]>([])
  const [agencies, setAgencies] = useState<{ code: string; name: string }[]>([])
  const [loading,  setLoading]  = useState(false)
  const [activeTab, setActiveTab] = useState<TabKey>('草稿')

  // 编辑抽屉
  const [drawerOpen, setDrawerOpen] = useState(false)
  // 右侧预览占屏比例：27% / 45% / 隐藏（用户指定的三档）
  // 字典驱动那几项的值。放在表单之外单独存——它们的取值受条件约束，
  // 由后端 resolve 决定，不走 antd Form 的那套。
  // 分包：每个包一份第四~第八部分（⑥⑪）。单包项目也存成一条，出稿逻辑不分两套。
  const [packages, setPackages] = useState<PackageData[]>([emptyPackage()])
  const [pkgTab, setPkgTab] = useState('0')
  const [dictValues, setDictValues] = useState<Record<string, unknown>>({})
  // 每保存一次 +1，右边预览跟着自动重出
  const [docReload, setDocReload] = useState(0)
  const [previewSize, setPreviewSize] = useState<PreviewSize>(() => {
    // 没存过就用默认的 27%。不能直接 Number(null)——那是 0，正好等于「隐藏」，
    // 结果第一次打开预览就是关的（实测踩到）。
    const raw = localStorage.getItem(PREVIEW_KEY)
    if (raw === null) return 27
    const v = Number(raw)
    return (v === 45 || v === 0 ? v : 27) as PreviewSize
  })
  const changePreviewSize = (v: PreviewSize) => {
    setPreviewSize(v); localStorage.setItem(PREVIEW_KEY, String(v))
  }
  const [editingId,  setEditingId]  = useState<number | null>(null)
  const [saving,     setSaving]     = useState(false)
  const [items,      setItems]      = useState<DemandItem[]>([])
  const [form] = Form.useForm()
  const [showSurvey, setShowSurvey] = useState(false)

  // 紧急采购：监听用途类型（手术时显示手术名称/级别）
  const purposeType = Form.useWatch('purpose_type', form)

  // 紧急采购：附件上传状态
  const [attachName,    setAttachName]    = useState('')   // 当前附件文件名
  const [uploading,     setUploading]     = useState(false)

  // Excel 导入状态
  const [importing, setImporting] = useState(false)

  // 分发弹窗（助理用）
  const [dispatchOpen,   setDispatchOpen]   = useState(false)
  const [dispatchTarget, setDispatchTarget] = useState<ProcurementDemand | null>(null)
  const [dispatchForm]   = Form.useForm()
  const [dispatching,    setDispatching]    = useState(false)

  // ── 加载列表 ─────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listDemands(undefined, demandType || undefined)
      setDemands(res.data.data || [])
    } catch { message.error('加载失败') }
    finally { setLoading(false) }
  }, [message, demandType])

  useEffect(() => {
    load()
    getAgencies().then(r => setAgencies(r.data.data || [])).catch(() => {})
  }, [load])

  useEffect(() => { setShowSurvey(isGov) }, [isGov])

  // ── 新建 ────────────────────────────────────────────────────────
  const openCreate = () => {
    setEditingId(null)
    setItems([emptyItem()])
    setAttachName('')
    form.resetFields()
    const def0 = makeDefault(demandType)
    form.setFieldsValue({ ...def0, demand_dept: user?.dept_name || '' })
    setDictValues(toDictValues(def0 as Record<string, unknown>))
    setPackages([emptyPackage()])
    setPkgTab('0')
    setShowSurvey(isGov)
    setDrawerOpen(true)
  }

  // ── 编辑 ────────────────────────────────────────────────────────
  const openEdit = (record: ProcurementDemand) => {
    setEditingId(record.id)
    const its = record.items?.length ? record.items : [emptyItem()]
    setItems(its)
    setAttachName(record.attachment_path ? record.attachment_path.split('/').pop() || '' : '')
    form.resetFields()
    form.setFieldsValue({
      ...record,
      compile_date:       record.compile_date       ? dayjs(record.compile_date)       : undefined,
      apply_time:         record.apply_time         ? dayjs(record.apply_time)         : undefined,
      expected_use_time:  record.expected_use_time  ? dayjs(record.expected_use_time)  : undefined,
    })
    setDictValues(toDictValues(record as unknown as Record<string, unknown>))
    setPackages(parsePackages(record as unknown as Record<string, unknown>))
    setPkgTab('0')
    setShowSurvey(isGov || !!(record.survey_content))
    setDrawerOpen(true)
  }

  /** 保存后提醒一句还缺什么。**不拦保存**——填一半存着是常态；
   *  真正拦的是提交（黄新博 2026-08-20：「缺件后可以保存但是无法提交就行」）。 */
  const hintMissing = (id?: number | null) => {
    if (!id) return
    checkDemand(id).then(r => {
      const miss = r.data.data.missing || []
      if (miss.length) {
        message.warning({
          content: `还差 ${miss.length} 项必填：${miss.slice(0, 4).join('、')}`
            + (miss.length > 4 ? ' 等' : '') + '。可以继续存着，提交前补齐就行',
          duration: 6,
        })
      }
    }).catch(() => { /* 查不到就算了，不打扰 */ })
  }

  // ── 保存 ────────────────────────────────────────────────────────
  const handleSave = async () => {
    try { await form.validateFields() }
    catch { message.warning('请检查必填项'); return }
    setSaving(true)
    try {
      const values = form.getFieldsValue()
      const payload: Partial<ProcurementDemand> = {
        ...values,
        // 字典那几项以字典为准——它们是被条件锁定/联动纠正过的值
        ...fromDictValues(dictValues),
        packages_json: JSON.stringify(packages),
        package_count: packages.length,
        demand_type: (demandType as DemandType) || values.demand_type,
        compile_date:      values.compile_date      ? dayjs(values.compile_date).format('YYYY-MM-DD')      : '',
        apply_time:        values.apply_time        ? dayjs(values.apply_time).format('YYYY-MM-DD')        : '',
        expected_use_time: values.expected_use_time ? dayjs(values.expected_use_time).format('YYYY-MM-DD') : '',
        items,
      }
      if (editingId) {
        await updateDemand(editingId, payload)
        message.success('保存成功')
        setDocReload(n => n + 1)   // 右边预览跟着重出，不用再点「重新出稿」
        hintMissing(editingId)
        setDrawerOpen(false)
        load()
      } else {
        const res = await createDemand(payload)
        const newId = res.data.data.id
        message.success('新建成功')
        hintMissing(newId)
        load()
        if (isEmergency) {
          // 紧急采购：留在抽屉，切换为编辑状态，供上传附件
          setEditingId(newId)
          message.info('可继续上传情况说明及病历资料附件')
        } else {
          setDrawerOpen(false)
        }
      }
    } catch { message.error('保存失败') }
    finally { setSaving(false) }
  }

  // ── 紧急采购：上传附件 ───────────────────────────────────────────
  const handleUpload: UploadProps['customRequest'] = async ({ file, onSuccess, onError }) => {
    if (!editingId) { onError?.(new Error('请先保存草稿再上传附件')); return }
    setUploading(true)
    try {
      const res = await uploadAttachment(editingId, file as File)
      setAttachName(res.data.original_name)
      form.setFieldValue('attachment_path', res.data.path)
      onSuccess?.(res.data)
      message.success(`附件「${res.data.original_name}」上传成功`)
    } catch (e: any) {
      onError?.(e)
      message.error(e.response?.data?.error || '上传失败')
    } finally { setUploading(false) }
  }

  // ── 提交/撤回/分发/退回/立项/删除 ─────────────────────────────
  const handleSubmit = async (id: number) => {
    try { await submitDemand(id); message.success('已提交，等待采购部分发'); load() }
    catch (e: any) {
      // 缺件被拦时，一行 message 塞不下——列成弹窗，让人知道去补哪几项
      const miss: string[] = e.response?.data?.missing || []
      if (miss.length) {
        modal.warning({
          title: `还差 ${miss.length} 项必填，补齐了才能提交`,
          width: 480,
          content: (
            <div style={{ maxHeight: 320, overflowY: 'auto', marginTop: 8 }}>
              {miss.map((m, i) => (
                <div key={i} style={{ fontSize: 13, lineHeight: 2 }}>· {m}</div>
              ))}
              <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 10 }}>
                已经填的都存着了，补完这几项再点提交就行。
              </div>
            </div>
          ),
          okText: '知道了',
        })
        return
      }
      message.error(e.response?.data?.error || '操作失败')
    }
  }
  const handleRecall = async (id: number) => {
    try { await recallDemand(id); message.success('已撤回为草稿'); load() }
    catch (e: any) { message.error(e.response?.data?.error || '操作失败') }
  }
  const openDispatch = (record: ProcurementDemand) => {
    setDispatchTarget(record); dispatchForm.resetFields(); setDispatchOpen(true)
  }
  const handleDispatch = async () => {
    if (!dispatchTarget) return
    try { await dispatchForm.validateFields() } catch { return }
    setDispatching(true)
    try {
      const vals = dispatchForm.getFieldsValue()
      await dispatchDemand(dispatchTarget.id, {
        assigned_officer: vals.assigned_officer,
        assigned_agency_code: vals.assigned_agency_code || '',
      })
      message.success(`已分发给 ${vals.assigned_officer}`)
      setDispatchOpen(false); load()
    } catch (e: any) { message.error(e.response?.data?.error || '分发失败') }
    finally { setDispatching(false) }
  }
  const handleReturn = async (id: number) => {
    try { await returnDemand(id); message.success('已退回'); load() }
    catch (e: any) { message.error(e.response?.data?.error || '操作失败') }
  }
  const handleCreateProject = async (record: ProcurementDemand) => {
    try {
      const res = await getPrefillForProject(record.id)
      const pf = res.data.prefill
      sessionStorage.setItem('demand_prefill', JSON.stringify(pf))
      navigate(`/new?from_demand=${pf.demand_id}`)
    } catch (e: any) { message.error(e.response?.data?.error || '操作失败') }
  }
  const handleDelete = async (id: number) => {
    try { await deleteDemand(id); message.success('已删除'); load() }
    catch (e: any) { message.error(e.response?.data?.error || '删除失败') }
  }

  // ── Excel 导入 ────────────────────────────────────────────────────
  const handleImportExcel: UploadProps['customRequest'] = async ({ file, onSuccess, onError }) => {
    if (!demandType) { onError?.(new Error('未知需求类型')); return }
    setImporting(true)
    try {
      const res = await importExcel(demandType, file as File)
      const { basic_data, items: importedItems } = res.data.data
      // 填充基本信息（合并，不覆盖已有必填字段）
      const current = form.getFieldsValue()
      form.setFieldsValue({ ...current, ...basic_data })
      // 填充标的
      if (importedItems && importedItems.length > 0) {
        setItems(importedItems)
        message.success(`导入成功：${Object.keys(basic_data).length} 个字段，${importedItems.length} 条标的`)
      } else {
        message.success(`导入成功：${Object.keys(basic_data).length} 个字段（无标的数据）`)
      }
      onSuccess?.(res.data)
    } catch (e: any) {
      onError?.(e)
      message.error(e.response?.data?.error || 'Excel 解析失败，请检查文件格式')
    } finally { setImporting(false) }
  }

  // ── 标的 CRUD ────────────────────────────────────────────────────
  const updateItem = (idx: number, field: keyof DemandItem, value: string | number) => {
    setItems(prev => {
      const next = [...prev]
      const row = { ...next[idx], [field]: value }
      if (field === 'unit_price' || field === 'quantity') {
        const up  = field === 'unit_price' ? Number(value) : Number(row.unit_price)
        const qty = field === 'quantity'   ? Number(value) : Number(row.quantity)
        row.amount = parseFloat((up * qty).toFixed(2))
      }
      next[idx] = row; return next
    })
  }
  const addItem    = () => setItems(p => [...p, emptyItem()])
  const removeItem = (idx: number) => setItems(p => p.filter((_, i) => i !== idx))

  const listFilter = useProjectListFilter(demands, DEMAND_ACCESSORS)
  const byTab = (tab: TabKey) => listFilter.filtered.filter(d => d.status === tab)

  // ── 操作列 ───────────────────────────────────────────────────────
  const demandActions = (record: ProcurementDemand, status: DemandStatus) => (
    <>
      {canWriteDemand && (status === '草稿' || status === '已分发') && (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
      )}
      {canWriteDemand && status === '草稿' && (
        <Popconfirm title="提交后等待采购部分发，确认？" onConfirm={() => handleSubmit(record.id)}>
          <Button size="small" type="primary" icon={<SendOutlined />}>提交</Button>
        </Popconfirm>
      )}
      {canWriteDemand && status === '待分发' && (
        <Popconfirm title="撤回为草稿？" onConfirm={() => handleRecall(record.id)}>
          <Button size="small" icon={<RollbackOutlined />}>撤回</Button>
        </Popconfirm>
      )}
      {status === '待分发' && isAssistant && (
        <Button size="small" type="primary" icon={<UserSwitchOutlined />} onClick={() => openDispatch(record)}>分发</Button>
      )}
      {status === '已分发' && isAssistant && (
        <Popconfirm title="退回该需求？经办人将无法立项。" onConfirm={() => handleReturn(record.id)}>
          <Button size="small" danger icon={<RollbackOutlined />}>退回</Button>
        </Popconfirm>
      )}
      {status === '已分发' && isOfficer && record.assigned_officer === user?.display_name && (
        <Button size="small" type="primary" style={{ background: '#52c41a', borderColor: '#52c41a' }}
          icon={<ArrowRightOutlined />} onClick={() => handleCreateProject(record)}>前往立项</Button>
      )}
      {record.attachment_path && (
        <Tooltip title="下载附件">
          <Button size="small" icon={<PaperClipOutlined />} onClick={() => window.open(demandAttachmentUrl(record.id), '_blank')}>附件</Button>
        </Tooltip>
      )}
      {record.project_id && (
        <Tooltip title="下载采购需求表 Word">
          <Button size="small" icon={<FileWordOutlined />} onClick={() => window.open(demandWordUrl(record.id), '_blank')}>Word</Button>
        </Tooltip>
      )}
      {canWriteDemand && status === '草稿' && (
        <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      )}
    </>
  )

  const typeTag = (r: ProcurementDemand) => {
    const m: Record<string, string> = {
      gov: '政府', competition: '竞选', sole_source: '单一', inquiry: '询议价', emergency: '紧急',
    }
    return m[r.demand_type] || r.demand_type
  }

  const demandToCard = (record: ProcurementDemand, status: DemandStatus): RecordCardData => {
    const fields: { label: string; value: React.ReactNode }[] = []
    if (!isEmergency) {
      fields.push({ label: '预算', value: record.budget_amount ? record.budget_amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '' })
      fields.push({ label: '方式', value: record.procurement_method })
    } else {
      fields.push({ label: '耗材', value: record.consumable_name })
      fields.push({ label: '用途', value: record.purpose_type })
    }
    fields.push({ label: '编制人', value: record.created_by })
    if (status === '已分发') {
      fields.push({ label: '经办人', value: record.assigned_officer })
      fields.push({ label: '代理', value: record.agency_name })
      fields.push({ label: '分发', value: record.dispatched_at ? record.dispatched_at.slice(0, 16) : '' })
    }
    if (status === '已立项') {
      fields.push({ label: '立项编号', value: record.project_number })
    }
    return {
      key: record.id,
      accent: STATUS_COLOR[status] === 'default' ? '#9aa0a6' : status === '已立项' ? '#34a853' : status === '已分发' ? '#1a73e8' : '#f9ab00',
      title: record.project_name,
      subtitle: record.demand_dept ? `科室 ${record.demand_dept}` : undefined,
      statusText: status,
      statusColor: STATUS_COLOR[status],
      tags: !isTyped ? <Tag bordered={false} style={{ marginInlineEnd: 0 }}>{typeTag(record)}</Tag> : undefined,
      fields,
      actions: demandActions(record, status),
    }
  }

  const itemColumns: ColumnsType<DemandItem & { _idx: number }> = [
    { title: '序号',    dataIndex: '_idx',         width: 50,  render: (_,__,i)   => i+1 },
    { title: '品目编号', dataIndex: 'item_no',       width: 90,  render: (v,_,i)   => <Input size="small" value={v} onChange={e=>updateItem(i,'item_no',e.target.value)} placeholder="1-1"/> },
    { title: '品目类别', dataIndex: 'category',      width: 100, render: (v,_,i)   => <Input size="small" value={v} onChange={e=>updateItem(i,'category',e.target.value)} placeholder="医疗设备"/> },
    { title: '标的名称', dataIndex: 'name',          width: 160, render: (v,_,i)   => <Input size="small" value={v} onChange={e=>updateItem(i,'name',e.target.value)} /> },
    { title: '单价（元）', dataIndex: 'unit_price',  width: 110, render: (v,_,i)   => <InputNumber size="small" value={v} min={0} precision={2} style={{width:'100%'}} onChange={val=>updateItem(i,'unit_price',val??0)}/> },
    { title: '数量',    dataIndex: 'quantity',       width: 80,  render: (v,_,i)   => <InputNumber size="small" value={v} min={0} style={{width:'100%'}} onChange={val=>updateItem(i,'quantity',val??0)}/> },
    { title: '单位',    dataIndex: 'unit',           width: 70,  render: (v,_,i)   => <Input size="small" value={v} onChange={e=>updateItem(i,'unit',e.target.value)} /> },
    // 标的还没填金额时 v 是 undefined，直接 .toLocaleString() 会把整个抽屉炸成白屏
    { title: '金额（元）', dataIndex: 'amount',      width: 110,
      render: (v?: number) => (v == null ? '' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })) },
    { title: '技术要求摘要', dataIndex: 'requirements', width: 180, render: (v,_,i) => <Input size="small" value={v} onChange={e=>updateItem(i,'requirements',e.target.value)} placeholder="简要说明"/> },
    { title: '', key: 'del', width: 50, render: (_,__,i) => <Button size="small" danger type="text" onClick={()=>removeItem(i)}>✕</Button> },
  ]

  const tabItems: { key: TabKey }[] = [
    { key: '草稿' }, { key: '待分发' }, { key: '已分发' }, { key: '已立项' },
  ]

  const pageTitle = meta ? `${meta.label}需求编制` : '采购需求总览（分发）'
  const pageHint  = meta?.hint || '所有类型需求汇总，供采购部分发使用'

  return (
    <div>
      <Card
        title={
          <Space>
            <span style={{ fontWeight: 600, fontSize: 16 }}>{pageTitle}</span>
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>{pageHint}</Text>
          </Space>
        }
        extra={
          isTyped && canWriteDemand && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建{meta?.label}{isEmergency ? '登记' : '需求'}
            </Button>
          )
        }
      >
        {isGov && (
          <Alert type="warning" showIcon style={{ marginBottom: 12 }}
            message="政府采购项目立项成功后将自动归档（不进入后续院内流程）" />
        )}
        <div style={{ marginBottom: 8 }}>
          <ProjectListToolbar f={listFilter} placeholder="搜索项目名称 / 编号" />
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={k => setActiveTab(k as TabKey)}
          items={tabItems.map(t => ({
            key: t.key,
            label: (
              <Space>
                {t.key}
                {byTab(t.key).length > 0 && (
                  <Badge count={byTab(t.key).length}
                    style={{ backgroundColor: STATUS_COLOR[t.key] === 'default' ? '#d9d9d9' : undefined }} />
                )}
              </Space>
            ),
            children: (
              <RecordCards
                dataSource={byTab(t.key)}
                loading={loading}
                emptyText={`暂无${t.key}需求`}
                toCard={(r) => demandToCard(r, t.key)}
              />
            ),
          }))}
        />
      </Card>

      {/* ── 分发弹窗 ── */}
      <Modal
        title={`分发：${dispatchTarget?.project_name || ''}`}
        open={dispatchOpen} onCancel={() => setDispatchOpen(false)}
        onOk={handleDispatch} confirmLoading={dispatching} okText="确认分发"
      >
        <Form form={dispatchForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="指派经办人（填写姓名）" name="assigned_officer"
            rules={[{ required: true, message: '请填写经办人姓名' }]}>
            <Input placeholder="如：黄新博" />
          </Form.Item>
          <Form.Item label="预指派代理机构（院内竞选/单一来源项目填写，其他留空）"
            name="assigned_agency_code">
            <Select allowClear placeholder="（不走代理免选）"
              options={agencies.map(a => ({ value: a.code, label: a.name }))} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 编辑/新建抽屉 ── */}
      <Drawer
        title={editingId
          ? `编辑${meta?.label || ''}${isEmergency ? '登记' : '需求'}`
          : `新建${meta?.label || ''}${isEmergency ? '登记' : '需求'}`}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        // 三栏工作台要横向铺开：左边填信息、右边看成稿，中间不跳页
        width="96vw"
        extra={
          <Space size={8}>
            <Text type="secondary" style={{ fontSize: 12 }}>文件预览</Text>
            <PreviewSizeToggle value={previewSize} onChange={changePreviewSize} />
          </Space>
        }
        styles={{ body: { paddingBottom: 80, paddingTop: 12 } }}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space>
              <Button type="primary" loading={saving} icon={<CheckCircleOutlined />} onClick={handleSave}>
                保存{isEmergency && !editingId ? '（保存后可上传附件）' : ''}
              </Button>
              <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            </Space>
            {/* 导入/导出工具 */}
            {isTyped && (
              <Space size={8}>
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() => window.open(demandTemplateUrl(demandType), '_blank')}
                >
                  下载 Excel 模板
                </Button>
                <Upload
                  customRequest={handleImportExcel}
                  showUploadList={false}
                  accept=".xlsx"
                >
                  <Button size="small" icon={<ImportOutlined />} loading={importing}>
                    从 Excel 导入
                  </Button>
                </Upload>
              </Space>
            )}
          </div>
        }
      >
        {/* 三栏工作台：左边填信息，右边看成稿，中间不跳页。
            预览宽度由顶部那三个按钮控制（27% / 45% / 隐藏）。 */}
        <div style={{ display: 'flex', gap: 12, alignItems: 'stretch',
                      height: 'calc(100vh - 190px)' }}>
          <div style={{
            flex: `1 1 ${100 - previewSize}%`, minWidth: 0,
            overflowY: 'auto', paddingRight: 6,
          }}>
        <Form form={form} layout="vertical" size="middle">

          {/* ════════════════════════════════════════════════════ */}
          {/* 紧急采购登记表单                                      */}
          {/* ════════════════════════════════════════════════════ */}
          {isEmergency ? (
            <>
              {/* 申请信息 */}
              <Card size="small" title="申请信息" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  <Col span={16}>
                    <Form.Item label="申请名称（用于列表显示）" name="project_name"
                      rules={[{ required: true, message: '请填写申请名称' }]}>
                      <Input placeholder="如：骨科急用XX耗材紧急采购申请" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="申请科室" name="demand_dept"
                      rules={[{ required: true, message: '请填写申请科室' }]}>
                      <Input placeholder="如：骨科" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="申请时间" name="apply_time">
                      <DatePicker style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="预计使用紧急耗材时间" name="expected_use_time"
                      rules={[{ required: true, message: '请填写预计使用时间' }]}>
                      <DatePicker style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* 耗材基本信息 */}
              <Card size="small" title="耗材基本信息" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  <Col span={16}>
                    <Form.Item label="耗材通用名" name="consumable_name"
                      rules={[{ required: true, message: '请填写耗材通用名' }]}>
                      <Input placeholder="如：骨科接骨板" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="单位" name="consumable_unit">
                      <Input placeholder="如：套、个、箱" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="预算单价（元）" name="consumable_unit_price">
                      <InputNumber style={{ width: '100%' }} min={0} precision={2}
                        formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                        parser={v => parseFloat(v?.replace(/,/g, '') || '0') as never} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="申请数量" name="apply_quantity">
                      <InputNumber style={{ width: '100%' }} min={1} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="生产厂家" name="manufacturer">
                      <Input placeholder="生产厂家全称" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="型号" name="model_spec">
                      <Input placeholder="产品型号/规格" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="耗材使用证（注册证号）" name="license_number">
                      <Input placeholder="注册证号" />
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item label="进口 / 国产" name="import_domestic">
                      <Radio.Group>
                        <Radio value="进口">进口</Radio>
                        <Radio value="国产">国产</Radio>
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item label="产品类型" name="product_on_catalog">
                      <Radio.Group>
                        <Radio value="挂网产品">挂网产品</Radio>
                        <Radio value="非挂网产品">非挂网产品</Radio>
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* 用途信息 */}
              <Card size="small" title="用途信息" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item label="用途" name="purpose_type"
                      rules={[{ required: true, message: '请选择用途' }]}>
                      <Radio.Group>
                        <Radio value="手术">手术</Radio>
                        <Radio value="治疗">治疗</Radio>
                        <Radio value="检查">检查</Radio>
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item label="院内有无类似产品" name="has_similar_product">
                      <Radio.Group>
                        <Radio value="有">有</Radio>
                        <Radio value="无">无</Radio>
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item label="是否需要配套设备/器械" name="needs_companion">
                      <Radio.Group>
                        <Radio value="需要">需要</Radio>
                        <Radio value="无需">无需</Radio>
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                  {/* 手术专用字段 */}
                  {purposeType === '手术' && (
                    <>
                      <Col span={12}>
                        <Form.Item label="手术名称"  name="surgery_name"
                          rules={[{ required: true, message: '请填写手术名称' }]}>
                          <Input placeholder="如：股骨干骨折内固定术" />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="手术级别" name="surgery_level">
                          <Select placeholder="请选择手术级别" allowClear
                            options={['一级手术','二级手术','三级手术','四级手术'].map(v=>({ value: v, label: v }))} />
                        </Form.Item>
                      </Col>
                    </>
                  )}
                </Row>
              </Card>

              {/* 适用范围 & 申购用途 */}
              <Card size="small" title="申购理由" style={{ marginBottom: 16 }}>
                <Form.Item
                  label="适用范围"
                  name="applicable_scope"
                  rules={[{ required: true, message: '请选择适用范围' }]}
                >
                  <Radio.Group>
                    <Space direction="vertical">
                      {SCOPE_OPTIONS.map(o => (
                        <Radio key={o.value} value={o.value}>{o.label}</Radio>
                      ))}
                    </Space>
                  </Radio.Group>
                </Form.Item>
                <Form.Item
                  label="申购耗材用途（重点描述耗材临床用途、优势、适应症）"
                  name="clinical_use_desc"
                  rules={[{ required: true, message: '请填写申购耗材用途' }]}
                >
                  <TextArea rows={5} placeholder="请详细描述耗材的临床用途、优势及适应症" />
                </Form.Item>
              </Card>

              {/* 附件上传 */}
              <Card size="small" title="情况说明及病历资料（附件）" style={{ marginBottom: 16 }}>
                {!editingId ? (
                  <Alert type="info" showIcon
                    message="请先点击「保存」创建草稿，保存成功后即可上传附件" />
                ) : (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {attachName && (
                      <Space>
                        <PaperClipOutlined style={{ color: '#1677ff' }} />
                        <Text>{attachName}</Text>
                        <Button size="small" type="link"
                          onClick={() => window.open(demandAttachmentUrl(editingId!), '_blank')}>
                          查看/下载
                        </Button>
                        <Tag color="green">已上传</Tag>
                      </Space>
                    )}
                    <Upload
                      customRequest={handleUpload}
                      showUploadList={false}
                      accept=".pdf,.jpg,.jpeg,.png,.docx,.doc,.xlsx,.xls"
                    >
                      <Button icon={<UploadOutlined />} loading={uploading}>
                        {attachName ? '重新上传' : '上传附件'}
                      </Button>
                    </Upload>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      支持 PDF、图片（JPG/PNG）、Word、Excel，文件将替换旧附件
                    </Text>
                  </Space>
                )}
              </Card>
            </>
          ) : isInquiry ? (
            <>
              {/* ════════════════════════════════════════════════ */}
              {/* 询议价采购需求表单                                */}
              {/* ════════════════════════════════════════════════ */}

              {/* 基本信息 */}
              <Card size="small" title="基本信息" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  <Col span={24}>
                    <Form.Item label="采购需求名称" name="project_name"
                      rules={[{ required: true, message: '请填写采购需求名称' }]}
                      extra="提交后经采购部分发，经办人立项时可再修改">
                      <Input placeholder="如：2025年两名中层干部离任经济责任审计采购项目" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="需求科室" name="demand_dept"
                      rules={[{ required: true, message: '请填写需求科室' }]}>
                      <Input placeholder="如：审计科" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="归口管理科室" name="manage_dept">
                      <Input placeholder="医学装备部" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="采购年度" name="year">
                      <Input placeholder="如：2026年" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="项目分类" name="category">
                      <Radio.Group>
                        <Radio value="货物">货物</Radio>
                        <Radio value="服务">服务</Radio>
                        <Radio value="工程">工程</Radio>
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="采购方式" name="procurement_method">
                      <Radio.Group>
                        <Radio value="院内询价">院内询价（2～5万）</Radio>
                        <Radio value="院内议价">院内议价（2万以下）</Radio>
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label="预算总额（元）" name="budget_amount">
                      <InputNumber style={{ width: '100%' }} min={0} precision={2}
                        formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                        parser={v => parseFloat(v?.replace(/,/g, '') || '0') as never} />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* 一、资格要求 */}
              <Card size="small" title="一、资格要求" style={{ marginBottom: 16 }}>
                <div style={{
                  background: '#fafafa', border: '1px solid #f0f0f0',
                  borderRadius: 6, padding: '10px 14px', marginBottom: 12,
                }}>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
                    通用资格要求（以下条款为实质性要求，不满足则作无效响应处理）：
                  </Text>
                  {STANDARD_QUALIFICATIONS.map((line, i) => (
                    <div key={i} style={{ fontSize: 13, color: '#555', lineHeight: '22px' }}>{line}</div>
                  ))}
                </div>
                <Form.Item
                  label="（八）本项目特定资格要求（如无特定要求可留空）"
                  name="qualification_requirements"
                >
                  <TextArea rows={4}
                    placeholder="如：供应商需具备国家行业主管部门颁发的有效执业证书，提供复印件并加盖公章。" />
                </Form.Item>
              </Card>

              {/* 二、技术/服务要求 */}
              <Card size="small" title="二、技术参数 / 服务要求" style={{ marginBottom: 16 }}>
                <Form.Item
                  label="项目内容及技术参数/服务具体要求（以下要求均为实质性要求）"
                  name="tech_requirements"
                  rules={[{ required: true, message: '请填写技术/服务要求' }]}
                >
                  <TextArea rows={10}
                    placeholder={`1. 项目内容\n1.1 …\n根据要求，请描述：\n  1.1.1 …\n  1.1.2 …\n\n2. 具体要求\n2.1 …\n2.2 …`} />
                </Form.Item>
              </Card>

              {/* 三、商务服务要求 */}
              <Card size="small" title="三、商务服务要求" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  <Col span={24}>
                    <Form.Item label="1. 付款方式" name="payment_terms">
                      <TextArea rows={3}
                        placeholder="如：完成项目并经验收合格后，提供普通增值税发票后20个工作日内支付合同总金额100%。" />
                    </Form.Item>
                  </Col>
                  <Col span={24}>
                    <Form.Item label="2. 售后服务要求" name="inq_after_sales">
                      <TextArea rows={3}
                        placeholder="如：自合同起始日起提供1年相关咨询服务。" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="3. 交付时间" name="inq_delivery_time">
                      <Input placeholder="如：合同签订后2个月内交付" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="服务/交付地点" name="inq_delivery_location">
                      <Input placeholder="如：内江市汉安大道西段1866号" />
                    </Form.Item>
                  </Col>
                  <Col span={24}>
                    <Form.Item label="4. 验收标准" name="acceptance_standard">
                      <TextArea rows={3}
                        placeholder="如：完成项目成果，经采购人对内容审核无异议后完成验收。" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="5. 履约保证金" name="inq_performance_bond">
                      <Input placeholder="不收取" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="6. 违约责任" name="breach_terms">
                      <Input placeholder="如：无。或填写违约处理方式。" />
                    </Form.Item>
                  </Col>
                  <Col span={24}>
                    <Form.Item label="7. 其他要求" name="inq_other_requirements">
                      <TextArea rows={4}
                        placeholder="如：（1）报价应包含人工、交通、税金等所有费用。&#10;（2）存在以下问题采购人可终止合同…" />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* 标的清单 */}
              <Card size="small" title="标的清单" style={{ marginBottom: 16 }}
                extra={<Button size="small" type="dashed" icon={<PlusOutlined />} onClick={addItem}>添加标的</Button>}
              >
                <Table
                  rowKey="key"
                  dataSource={items.map((it, i) => ({ ...it, _idx: i, key: i }))}
                  columns={itemColumns}
                  pagination={false} size="small" scroll={{ x: 800 }}
                  locale={{ emptyText: '暂无标的，点击「添加标的」' }}
                />
              </Card>
            </>

          ) : (
            <>
              {/* ════════════════════════════════════════════════ */}
              {/* 2.2 标准采购需求表单（政府采购/院内竞选/单一来源） */}
              {/* ════════════════════════════════════════════════ */}

              {/* 表头 */}
              <Card size="small" title="表头信息" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item label="需求科室" name="demand_dept"
                      rules={[{ required: true, message: '请填写需求科室' }]}>
                      <Input placeholder="如：骨科" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="归口管理科室" name="manage_dept">
                      <Input placeholder="医学装备部" />
                    </Form.Item>
                  </Col>
                  <Col span={24}>
                    <Form.Item label="采购需求名称" name="project_name"
                      rules={[{ required: true, message: '请填写采购需求名称' }]}
                      extra="提交后经采购部分发、经办人立项时可再修改为正式项目名称">
                      <Input placeholder="如：骨科2026年XX耗材采购需求" />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* 第一部分 */}
              <Card size="small" title="第一部分：项目基本情况" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  {isGov && (
                    <>
                      <Col span={12}>
                        <Form.Item label="1.1 采购单位">
                          <Input value="内江市第一人民医院" disabled />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="1.3 编制单位">
                          <Input value="内江市第一人民医院" disabled />
                        </Form.Item>
                      </Col>
                    </>
                  )}
                  <Col span={8}>
                    <Form.Item label={isGov ? '1.2 所属年度' : '所属年度'} name="year">
                      <Input placeholder="如：2026年" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item label={isGov ? '1.4 编制时间' : '编制时间'} name="compile_date">
                      <DatePicker style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item
                      label={isGov ? '1.6 预算金额（元）' : '预算金额（元）'}
                      name="budget_amount"
                      rules={isCompetition ? [{
                        validator: (_: unknown, v: number) =>
                          v > 0 && v < 50000
                            ? Promise.reject('预算金额低于5万元，请通过询议价需求进行编制')
                            : Promise.resolve(),
                      }] : []}
                    >
                      <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="0.00"
                        formatter={v => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                        parser={v => parseFloat(v?.replace(/,/g, '') || '0') as never} />
                    </Form.Item>
                  </Col>
                  <Col span={24}>
                    <Form.Item label={isGov ? '1.5 项目所属分类' : '项目所属分类'} name="category">
                      <Radio.Group>
                        <Radio value="货物">货物</Radio>
                        <Radio value="服务">服务</Radio>
                        <Radio value="工程">工程</Radio>
                        {isCompetition && (
                          <Radio value="挂网医用耗材（招单价）">挂网医用耗材（招单价）</Radio>
                        )}
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                  <Col span={24}>
                    <Form.Item label={isGov ? '1.7 项目概况' : '项目概况'} name="project_overview">
                      <TextArea rows={3} placeholder="请描述项目概况" />
                    </Form.Item>
                  </Col>
                  <Col span={24}>
                    <Form.Item
                      label={isGov
                        ? '1.8 本项目是否有为采购项目提供整体设计、规范编制或项目管理、监理、检测等服务的供应商'
                        : '本项目是否有为采购项目提供整体设计/规范编制/项目管理/监理/检测等服务的供应商'}
                      name="has_related_supplier">
                      <Radio.Group>
                        <Radio value="是">是</Radio>
                        <Radio value="否">否</Radio>
                      </Radio.Group>
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* 第二部分 */}
              {!isGov && (
                <div style={{ marginBottom: 8 }}>
                  <Button type="link" style={{ paddingLeft: 0 }}
                    onClick={() => setShowSurvey(v => !v)}>
                    {showSurvey ? '▼ 隐藏第二部分（需求调查，选填）' : '▶ 展开第二部分（需求调查，选填）'}
                  </Button>
                </div>
              )}
              {(isGov || showSurvey) && (
                <Card size="small"
                  title={`第二部分：采购需求调查情况${isGov ? '' : '（选填）'}`}
                  style={{ marginBottom: 16 }}>
                  {isGov ? (
                    <Row gutter={16}>
                      <Col span={24}>
                        <Form.Item label="是否需要需求调查" name="survey_needed">
                          <Radio.Group>
                            <Radio value="需要">需要</Radio>
                            <Radio value="不需要">不需要</Radio>
                          </Radio.Group>
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="2.1 相关产业发展情况" name="survey_industry">
                          <TextArea rows={3} placeholder="填写相关产业发展情况" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="2.2 市场供给情况" name="survey_market">
                          <TextArea rows={3} placeholder="填写市场供给情况" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="2.3 同类采购项目历史成交信息情况" name="survey_history">
                          <TextArea rows={3} placeholder="填写同类项目历史成交信息" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="2.4 可能涉及的运行维护、升级更新、备品备件、耗材等后续采购情况" name="survey_followup">
                          <TextArea rows={3} placeholder="填写后续采购情况" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="2.5 其他相关情况" name="survey_other">
                          <TextArea rows={3} placeholder="填写其他相关情况" />
                        </Form.Item>
                      </Col>
                    </Row>
                  ) : (
                    <Form.Item name="survey_content" noStyle>
                      <TextArea rows={5}
                        placeholder="填写需求调查情况：同类产品市场价格、供应商信息、技术参数调查等" />
                    </Form.Item>
                  )}
                </Card>
              )}

              {/* 第三部分 */}
              <Card size="small" title="第三部分：项目采购实施计划" style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  {isGov ? (
                    <>
                      {/* 3.1~3.6 改成字段字典驱动：哪些选项能选、什么条件下锁死、
                          选了要再填什么，全由后端字典说了算，这里不写业务判断。
                          好处是界面和成稿用同一套规则，不会「界面让填、出稿被纠正」。 */}
                      <Col span={24}>
                        <DictFields
                          names={['采购组织形式', '采购方式', '采购包划分', '包数',
                                  '是否属于一签多年项目', '中小企业政策',
                                  '面向的企业规模', '预留形式', '预留比例']}
                          values={dictValues}
                          onChange={patch => setDictValues(v => ({ ...v, ...patch }))}
                        />
                      </Col>
                      {([
                        ['3.6 是否采购环境标识产品', 'is_eco_product'],
                        ['3.7 是否采购节能产品',     'is_energy_save'],
                        ['3.8 项目采购标的是否包含进口产品', 'has_import_product'],
                        ['3.9 采购标的是否属于政府购买服务', 'is_govt_service'],
                        ['3.10 是否属于政务信息系统项目',    'is_info_system'],
                        ['3.11 是否省属高校/科研院所科研设备采购', 'is_research_equip'],
                      ] as [string, string][]).map(([label, name]) => (
                        <Col span={12} key={name}>
                          <Form.Item label={label} name={name}>
                            <Radio.Group>
                              <Radio value="是">是</Radio>
                              <Radio value="否">否</Radio>
                            </Radio.Group>
                          </Form.Item>
                        </Col>
                      ))}
                    </>
                  ) : (
                    <>
                      <Col span={24}>
                        <Form.Item label="采购方式（自行采购）" name="procurement_method">
                          <Radio.Group>
                            <Radio value="院内竞选">院内竞选</Radio>
                            <Radio value="院内单一来源">院内单一来源</Radio>
                            <Radio value="院内询价">院内询价</Radio>
                            <Radio value="院内议价">院内议价</Radio>
                          </Radio.Group>
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="3.3 采购包划分" name="package_split">
                          <Radio.Group>
                            <Radio value="不分包采购">不分包采购</Radio>
                            <Radio value="分包采购">分包采购</Radio>
                          </Radio.Group>
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="3.4 是否属于一签多年项目" name="is_multi_year">
                          <Radio.Group>
                            <Radio value="是">是</Radio>
                            <Radio value="否">否</Radio>
                          </Radio.Group>
                        </Form.Item>
                      </Col>
                    </>
                  )}
                  {isSoleSource && (
                    <Col span={24}>
                      <Form.Item label="单一来源采购论证理由" name="sole_source_reason"
                        rules={[{ required: true, message: '单一来源采购需说明论证理由' }]}>
                        <TextArea rows={4} placeholder="请填写只能从单一供应商采购的理由及依据" />
                      </Form.Item>
                    </Col>
                  )}
                </Row>
              </Card>

              {/* 第四部分：标的 */}
              <Card size="small" title="第四部分：分包情况及标的情况" style={{ marginBottom: 16 }}
                extra={<Button size="small" type="dashed" icon={<PlusOutlined />} onClick={addItem}>添加标的</Button>}
              >
                <div style={{ fontWeight: 500, marginBottom: 8, color: '#555' }}>一、标的情况</div>
                <Table
                  rowKey="key"
                  dataSource={items.map((it, i) => ({ ...it, _idx: i, key: i }))}
                  columns={itemColumns}
                  pagination={false} size="small" scroll={{ x: 950 }}
                  locale={{ emptyText: '暂无标的，点击「添加标的」' }}
                />
                {isGov && (
                  <>
                    <div style={{ fontWeight: 500, margin: '16px 0 8px', color: '#555' }}>
                      二、具体分包情况
                      <span style={{ fontWeight: 400, fontSize: 12, color: '#5f6368', marginLeft: 8 }}>
                        每个包就是一份独立合同，第四~第八部分各填一份；
                        各包只差几个参数时用「复制上一个包」
                      </span>
                    </div>
                    <PackageEditor value={packages} onChange={setPackages}
                      activeKey={pkgTab} onActiveChange={setPkgTab} />
                  </>
                )}
              </Card>

              {/* 第五～七部分。政府采购已并进上面的分包编辑器（每包一份），
                  这里只留给院内竞选等单包口径的需求。 */}
              {!isGov && (
              <>
              <Card size="small" title="第五部分：技术要求" style={{ marginBottom: 16 }}>
                <Form.Item name="tech_requirements" noStyle>
                  <TextArea rows={5} placeholder="请填写技术要求内容" />
                </Form.Item>
              </Card>
              <Card size="small" title="第六部分：商务要求" style={{ marginBottom: 16 }}>
                <Form.Item name="business_requirements" noStyle>
                  <TextArea rows={4} placeholder="请填写商务要求内容" />
                </Form.Item>
              </Card>
              <Card size="small" title="第七部分：资格要求" style={{ marginBottom: 16 }}>
                <Form.Item name="qualification_requirements" noStyle>
                  <TextArea rows={4} placeholder="请填写资格要求内容" />
                </Form.Item>
              </Card>
              </>
              )}

              {/* 第八部分已并入分包编辑器：评审因素按包填，
                  综合评分法/最低评标价法两套口径也按包定（⑨）。 */}

              {/* 第九部分 */}
              <Card size="small"
                title={`第九部分：合同管理安排${isGov ? '' : '（简化版）'}`}
                style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  {isGov && (
                    <Col span={24}>
                      <Form.Item label="9.1 合同类型" name="contract_type">
                        <Radio.Group>
                          {['买卖合同','租赁合同','建设工程合同','技术合同','委托合同','物业管理合同','其他合同'].map(v => (
                            <Radio key={v} value={v}>{v}</Radio>
                          ))}
                        </Radio.Group>
                      </Form.Item>
                    </Col>
                  )}
                  <Col span={12}>
                    <Form.Item label="9.2 是否为据实结算" name="contract_is_actual">
                      <Radio.Group><Radio value="是">是</Radio><Radio value="否">否</Radio></Radio.Group>
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="9.3 合同履行期限" name="contract_period">
                      <Input placeholder="如：签订合同后365天内" />
                    </Form.Item>
                  </Col>
                  {isGov && (
                    <Col span={12}>
                      <Form.Item label="9.4 合同履约地点" name="contract_location">
                        <Input placeholder="如：内江市第一人民医院" />
                      </Form.Item>
                    </Col>
                  )}
                  <Col span={24}>
                    <Form.Item label="9.5 合同支付约定" name="payment_terms">
                      <TextArea rows={3} placeholder="请填写合同支付约定" />
                    </Form.Item>
                  </Col>
                  {isGov && (
                    <>
                      <Col span={24}>
                        <Form.Item label="9.6 验收交付标准和方法" name="acceptance_delivery">
                          <TextArea rows={3} placeholder="请填写验收交付标准和方法" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="9.7 质量保修范围和保修期" name="warranty_terms">
                          <TextArea rows={2} placeholder="请填写质量保修范围和保修期" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="9.8 知识产权归属和处理方式" name="ip_terms">
                          <TextArea rows={2} placeholder="请填写知识产权归属和处理方式" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="9.9 成本补偿和风险分担约定" name="cost_risk_terms">
                          <TextArea rows={2} placeholder="请填写成本补偿和风险分担约定" />
                        </Form.Item>
                      </Col>
                    </>
                  )}
                  <Col span={24}>
                    <Form.Item label="9.10 违约责任与解决争议的方法" name="breach_terms">
                      <TextArea rows={3} placeholder="请填写违约责任与争议解决方式" />
                    </Form.Item>
                  </Col>
                  {isGov && (
                    <>
                      <Col span={24}>
                        <Form.Item label="9.11 合同其他条款" name="other_contract_terms">
                          <TextArea rows={2} placeholder="请填写合同其他条款" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="9.12 履约保证" name="performance_bond_terms">
                          <TextArea rows={2} placeholder="请填写履约保证相关约定" />
                        </Form.Item>
                      </Col>
                    </>
                  )}
                </Row>
              </Card>

              {/* 第十部分 */}
              <Card size="small"
                title={`第十部分：履约验收方案${isGov ? '' : '（简化版）'}`}
                style={{ marginBottom: 16 }}>
                <Row gutter={16}>
                  {isGov && (
                    <>
                      <Col span={12}>
                        <Form.Item label="10.1 验收组织方式" name="acceptance_org">
                          <Radio.Group>
                            <Radio value="自行验收">自行验收</Radio>
                            <Radio value="委托采购代理机构验收">委托采购代理机构验收</Radio>
                          </Radio.Group>
                        </Form.Item>
                      </Col>
                      {([
                        ['10.2 是否邀请本项目的其他供应商', 'invite_other_supplier'],
                        ['10.3 是否邀请专家',               'invite_expert'],
                        ['10.4 是否邀请服务对象',           'invite_service_obj'],
                        ['10.5 是否邀请第三方检测机构',     'invite_third_party'],
                      ] as [string, string][]).map(([label, name]) => (
                        <Col span={12} key={name}>
                          <Form.Item label={label} name={name}>
                            <Radio.Group>
                              <Radio value="是">是</Radio>
                              <Radio value="否">否</Radio>
                            </Radio.Group>
                          </Form.Item>
                        </Col>
                      ))}
                    </>
                  )}
                  <Col span={24}><Form.Item label="10.6 履约验收程序" name="acceptance_procedure">
                    <TextArea rows={3} placeholder="请填写履约验收程序" />
                  </Form.Item></Col>
                  <Col span={12}><Form.Item label="10.7 履约验收时间" name="acceptance_time">
                    <Input placeholder="如：货物到达后30日内" />
                  </Form.Item></Col>
                  {isGov && (
                    <Col span={24}><Form.Item label="10.8 验收组织的其他事项" name="acceptance_misc">
                      <TextArea rows={2} placeholder="请填写验收组织其他事项" />
                    </Form.Item></Col>
                  )}
                  <Col span={24}><Form.Item label="10.9 技术履约验收内容" name="acceptance_tech">
                    <TextArea rows={3} placeholder="请填写技术履约验收内容" />
                  </Form.Item></Col>
                  <Col span={24}><Form.Item label="10.10 商务履约验收内容" name="acceptance_biz">
                    <TextArea rows={3} placeholder="请填写商务履约验收内容" />
                  </Form.Item></Col>
                  <Col span={24}><Form.Item label="10.11 履约验收标准" name="acceptance_standard">
                    <TextArea rows={3} placeholder="请填写履约验收标准" />
                  </Form.Item></Col>
                  {isGov && (
                    <Col span={24}><Form.Item label="10.12 履约验收其他事项" name="acceptance_extra">
                      <TextArea rows={2} placeholder="请填写履约验收其他事项" />
                    </Form.Item></Col>
                  )}
                </Row>
              </Card>

              {/* 第十一部分（仅政府采购） */}
              {isGov && (
                <Card size="small" title="第十一部分：风险控制措施和替代方案" style={{ marginBottom: 16 }}>
                  <Row gutter={16}>
                    <Col span={24}>
                      <Form.Item label="是否需要组织风险判断、提出处置措施和替代方案" name="risk_needed">
                        <Radio.Group><Radio value="是">是</Radio><Radio value="否">否</Radio></Radio.Group>
                      </Form.Item>
                    </Col>
                    <Col span={24}>
                      <Form.Item label="风险控制措施和替代方案" name="risk_measures">
                        <TextArea rows={4} placeholder="请填写风险控制措施和替代方案（如需要）" />
                      </Form.Item>
                    </Col>
                  </Row>
                </Card>
              )}

            </>
          )}

        </Form>
          </div>

          {/* 「隐藏」不是把整个右栏收掉，而是只收文件预览——
              Agent 操作区留下并占满，正好比原来更大。 */}
          {/* 收起预览时右栏给 45%——那一档整栏都是 Agent 对话，300px 太窄，
              一行塞不下几个字（黄新博 2026-08-20 提的）。 */}
          <div style={{ flex: `0 0 ${previewSize > 0 ? previewSize : 45}%`,
                        minWidth: 320, overflow: 'hidden' }}>
            <DemandDocPanel demandId={editingId ?? undefined}
              previewHidden={previewSize === 0} reloadToken={docReload}
              onApplied={async () => {
                // Agent 采纳后值已经写进库了，把这条重新拉一遍灌进表单，
                // 否则左边还是旧的，一保存又把 Agent 填的覆盖回去
                const fresh = await listDemands(undefined, demandType || undefined)
                const one = (fresh.data.data || []).find(x => x.id === editingId)
                if (one) openEdit(one)
                load()
              }} />
          </div>
        </div>
      </Drawer>
    </div>
  )
}
