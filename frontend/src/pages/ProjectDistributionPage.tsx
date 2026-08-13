import { useState, useEffect, useCallback } from 'react'
import {
  Card, Tabs, Button, Drawer, Form, Input, InputNumber, Select, Switch,
  Space, Tag, App, Upload, Popconfirm, Tooltip, Typography, Divider,
  Modal, DatePicker, Alert, List, Checkbox,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PaperClipOutlined,
  EyeOutlined, DownloadOutlined, RetweetOutlined, CloudDownloadOutlined,
  FileDoneOutlined, PrinterOutlined, ExportOutlined, SafetyCertificateOutlined, KeyOutlined,
  PlusCircleOutlined, AuditOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'
import { useAuth } from '../hooks/useAuth'
import {
  listDistributions, createDistribution, updateDistribution, deleteDistribution,
  reassignAgency, uploadDistAttachment, deleteDistAttachment,
  linkDistProject, cancelDistProject, unlinkDistProject,
  scrapeMine, scrapeMineStatus,
  distAttachmentPreviewUrl, distAttachmentDownloadUrl, distExportUrl, distPrintUrl,
  scrapeRdweb, scrapeStatus, rdwebAction, rdwebActionStatus,
  listRdwebAccounts, createRdwebAccount, updateRdwebAccount, deleteRdwebAccount,
  type Distribution, type DistAttachment, type RdwebAccount,
} from '../services/projectDistribution'
import ProjectListToolbar, { useProjectListFilter, type ListFilterAccessors } from '../components/ProjectListToolbar'
import { getProjects, type Project } from '../services/project'

const { Text } = Typography

const DIST_ACCESSORS: ListFilterAccessors<Distribution> = {
  searchText: r => [r.name, r.project_number, r.agency_name],
  createdAt: r => r.created_at,
  number: r => r.project_number,
  method: r => r.method,
}
const { TextArea } = Input

// 采购方式（与立项一致）；院内竞选/政府采购/单一来源 走代理轮派
const METHODS = ['院内竞选', '政府采购', '院内单一来源采购', '医用耗材紧急采购', '院内询价', '院内议价']
// 各采购方式用不同颜色区分，便于一眼分辨
const METHOD_COLOR: Record<string, string> = {
  '院内竞选': 'magenta', '政府采购': 'red', '院内单一来源采购': 'volcano',
  '医用耗材紧急采购': 'orange', '院内询价': 'green', '院内议价': 'cyan',
}
// 经办人（采购部）。后续可改为后端动态获取
const OFFICERS = ['黄新博', '郑跃俊', '谭群', '杨文炽']
// 三个流程（表单类型）用不同颜色区分
const FORM_TYPE_COLOR: Record<string, string> = {
  '采购需求审签表': 'blue', '设备科维修': 'purple', '医用耗材紧急': 'red',
}
const FORM_TYPE_ACCENT: Record<string, string> = {
  '采购需求审签表': '#1a73e8', '设备科维修': '#722ed1', '医用耗材紧急': '#d4380d',
}
function parseExtra(s: string): Record<string, string> {
  try { return s ? (JSON.parse(s) as Record<string, string>) : {} } catch { return {} }
}

const STATUS_COLOR: Record<string, string> = { 待分发: 'orange', 已分发: 'blue', 已立项: 'green', 已取消: 'default' }
const ACCENT: Record<string, string> = { 待分发: '#f9ab00', 已分发: '#1a73e8', 已立项: '#34a853', 已取消: '#8c8c8c' }
const TABS = ['待分发', '已分发', '已立项', '已取消']

function fmtBudget(v: number | null) {
  if (v == null || v === 0) return '—'
  return `￥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
function fmtSize(n: number) {
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

// 审签表附件（流程打印 PDF）
function flowSheet(d: Distribution): DistAttachment | undefined {
  return d.attachments?.find(a => a.category === '审签表')
}
// 漏项校验：必填字段缺失 / 缺审签表 / 缺附件材料
const REQUIRED_FIELDS: { key: keyof Distribution; label: string }[] = [
  { key: 'name', label: '项目名称' },
  { key: 'manage_dept', label: '归口管理科室' },
  { key: 'demand_dept', label: '需求科室' },
  { key: 'budget', label: '预算金额' },
  { key: 'method', label: '采购方式' },
  { key: 'org_form', label: '采购组织形式' },
]
function missingOf(d: Distribution): string[] {
  const miss: string[] = []
  for (const f of REQUIRED_FIELDS) {
    const v = d[f.key]
    if (v == null || v === '' || v === 0) miss.push(f.label)
  }
  if (!flowSheet(d)) miss.push('审签表(流程打印PDF)')
  if (!d.attachments?.some(a => a.category !== '审签表')) miss.push('附件材料')
  return miss
}

export default function ProjectDistributionPage() {
  const { message, modal } = App.useApp()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // 4.0 项目池（view=pool）：经办人本人的池子，只放本人账号抓的、加「抓取分发给我的」按钮；
  // 无 view（2.1 项目分发）：助理的分发视图，通用抓取 + 分发工具。
  const poolMode = searchParams.get('view') === 'pool'
  const role = user?.role || ''
  const isManager = ['assistant', 'pd_assistant', 'leader'].includes(role) || !!user?.is_admin

  const [rows, setRows] = useState<Distribution[]>([])
  const [loading, setLoading] = useState(false)
  const [scraping, setScraping] = useState(false)
  // 4.0 项目池里「待分发」恒为 0 条（抓进来就直接是已分发给本人），默认停在空列表会让人
  // 以为项目没抓到（实测被这个坑过一次）→ 池子模式默认落在「已分发」＝真正待你立项的那批。
  const [tab, setTab] = useState(searchParams.get('view') === 'pool' ? '已分发' : '待分发')

  // rd-web 办理（接收/驳回/撤回）
  const [acting, setActing] = useState(false)
  const [acceptFor, setAcceptFor] = useState<Distribution | null>(null)
  const [acceptOfficer, setAcceptOfficer] = useState('')
  const [acceptOpinion, setAcceptOpinion] = useState('')

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()
  const watchMethod = Form.useWatch('method', form)

  const [attachFor, setAttachFor] = useState<Distribution | null>(null)
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string; distId?: number }>({ open: false, url: '', name: '' })
  const [exportOpen, setExportOpen] = useState(false)
  const [exportRange, setExportRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)
  const [exportMethods, setExportMethods] = useState<string[]>([])
  const [validateOpen, setValidateOpen] = useState(false)
  const [printFor, setPrintFor] = useState<Distribution | null>(null)
  const [printSel, setPrintSel] = useState<number[]>([])
  const [acctOpen, setAcctOpen] = useState(false)
  const [accts, setAccts] = useState<RdwebAccount[]>([])
  const [acctEditId, setAcctEditId] = useState<number | null>(null)
  const [acctForm] = Form.useForm()

  // 对账：关联到已在 4.1 单独立项的项目
  const [linkFor, setLinkFor] = useState<Distribution | null>(null)
  const [linkPid, setLinkPid] = useState<number | undefined>()
  const [linkOpts, setLinkOpts] = useState<Project[]>([])
  const [linking, setLinking] = useState(false)

  const openLink = async (d: Distribution) => {
    setLinkFor(d)
    setLinkPid(undefined)
    try {
      const r = await getProjects()
      // 只列还没被池内其它条目占用的、非草稿项目
      const taken = new Set(rows.filter(x => x.id !== d.id && x.project_id).map(x => x.project_id))
      setLinkOpts((r.data.data || []).filter(p => !p.is_draft && !taken.has(p.id)))
    } catch { message.error('加载项目列表失败') }
  }

  const doLink = async () => {
    if (!linkFor || !linkPid) return
    setLinking(true)
    try {
      const r = await linkDistProject(linkFor.id, linkPid)
      message.success(r.data.message || '已关联')
      setLinkFor(null)
      load()
    } catch (e: unknown) {
      message.error((e as { response?: { data?: { error?: string } } })?.response?.data?.error || '关联失败')
    } finally { setLinking(false) }
  }

  const doCancel = async (d: Distribution) => {
    try {
      await cancelDistProject(d.id)
      message.success('已标记为不立项')
      load()
    } catch { message.error('操作失败') }
  }

  const doUnlink = async (d: Distribution) => {
    try {
      await unlinkDistProject(d.id)
      message.success('已撤销关联')
      load()
    } catch { message.error('操作失败') }
  }

  // 记下是哪一条记录的附件，好让面板上的「上一件 / 下一件」翻同一批。
  // 一条审签表常带三五个附件（方案、意见、通过文件），一件件点开关掉太费手。
  const previewAtt = (d: Distribution, att: DistAttachment) =>
    setPreview({ open: true, url: distAttachmentPreviewUrl(d.id, att.id), name: att.original_name, distId: d.id })

  const pvOwner = rows.find(d => d.id === preview.distId)
  const pvList = (pvOwner?.attachments || [])
    .filter(a => isPreviewable(a.original_name))
    .map(a => ({ url: distAttachmentPreviewUrl(pvOwner!.id, a.id), filename: a.original_name }))
  const pvIdx = pvList.findIndex(x => x.url === preview.url)

  const loadAccts = useCallback(async () => {
    try { const r = await listRdwebAccounts(); setAccts(r.data.data || []) } catch { /* ignore */ }
  }, [])
  const openAccts = () => { setAcctOpen(true); setAcctEditId(null); acctForm.resetFields(); acctForm.setFieldsValue({ usage: '执行' }); loadAccts() }
  const editAcct = (a: RdwebAccount) => { setAcctEditId(a.id); acctForm.setFieldsValue(a) }
  const saveAcct = async () => {
    const v = await acctForm.validateFields()
    try {
      if (acctEditId) await updateRdwebAccount(acctEditId, v)
      else await createRdwebAccount(v)
      message.success('已保存'); acctForm.resetFields(); acctForm.setFieldsValue({ usage: '执行' }); setAcctEditId(null); loadAccts()
    } catch { message.error('保存失败') }
  }
  const delAcct = async (id: number) => {
    try { await deleteRdwebAccount(id); message.success('已删除'); loadAccts() } catch { message.error('删除失败') }
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listDistributions(poolMode ? 'pool' : undefined)
      setRows(res.data.data || [])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [message, poolMode])
  useEffect(() => { load() }, [load])

  // attachFor 同步最新数据（上传/删除后刷新弹窗内列表）
  useEffect(() => {
    if (attachFor) {
      const fresh = rows.find(r => r.id === attachFor.id)
      if (fresh && fresh !== attachFor) setAttachFor(fresh)
    }
  }, [rows]) // eslint-disable-line react-hooks/exhaustive-deps

  const openCreate = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({ method: '院内竞选', is_central: false })
    setDrawerOpen(true)
  }
  const openEdit = (d: Distribution) => {
    setEditingId(d.id)
    form.resetFields()
    form.setFieldsValue({
      serial_no: d.serial_no, originator: d.originator, name: d.name, content: d.content,
      manage_dept: d.manage_dept, demand_dept: d.demand_dept,
      budget: d.budget, price_limit: d.price_limit, method: d.method, org_form: d.org_form,
      project_number: d.project_number, is_central: !!d.is_central, officer: d.officer,
    })
    setDrawerOpen(true)
  }
  const openPrint = (d: Distribution) => {
    setPrintFor(d)
    setPrintSel((d.attachments || []).map(a => a.id))  // 默认全选
  }

  const handleSave = async () => {
    const v = await form.validateFields()
    setSaving(true)
    try {
      const payload = { ...v, is_central: v.is_central ? 1 : 0 }
      if (editingId) {
        await updateDistribution(editingId, payload)
        message.success('已保存')
      } else {
        const res = await createDistribution(payload)
        const ag = res.data.data.agency_name
        message.success(ag ? `已分发，代理机构：${ag}` : '已分发')
      }
      setDrawerOpen(false)
      load()
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      if (err.response) message.error(err.response.data?.error || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleReassign = (d: Distribution) => {
    modal.confirm({
      title: '重新轮派代理机构',
      content: `按轮派顺序重新指派下一家代理机构给「${d.name}」？`,
      onOk: async () => {
        try {
          const res = await reassignAgency(d.id)
          message.success(`已改派：${res.data.data.agency_name}`)
          load()
        } catch { message.error('改派失败') }
      },
    })
  }

  const handleDelete = async (d: Distribution) => {
    try { await deleteDistribution(d.id); message.success('已删除'); load() }
    catch { message.error('删除失败') }
  }

  // 从 rd-web 抓取（后台跑，轮询状态完成后刷新）
  const handleScrape = async () => {
    setScraping(true)
    try {
      const res = await scrapeRdweb()
      message.success(res.data.message || '已开始抓取')
      let n = 0
      const timer = setInterval(async () => {
        n += 1
        try {
          const st = await scrapeStatus()
          if (!st.data.data.running) {
            clearInterval(timer); setScraping(false)
            if (st.data.data.last_msg) message.info(st.data.data.last_msg)
            load()
          }
        } catch { /* ignore */ }
        if (n > 30) { clearInterval(timer); setScraping(false); load() }
      }, 4000)
    } catch (e) {
      setScraping(false)
      const err = e as { response?: { data?: { error?: string } } }
      message.warning(err.response?.data?.error || '抓取失败')
    }
  }

  // 抓取「分发给我(经办人本人)的待处理审签表」——用本人 rd-web 账号，只进 4.0 项目池
  const handleScrapeMine = async () => {
    setScraping(true)
    try {
      const res = await scrapeMine()
      message.success(res.data.message || '已开始抓取本人待处理项目')
      let n = 0
      const timer = setInterval(async () => {
        n += 1
        try {
          const st = await scrapeMineStatus()
          if (!st.data.data.running) {
            clearInterval(timer); setScraping(false)
            if (st.data.data.last_msg) message.info(st.data.data.last_msg)
            load()
          }
        } catch { /* ignore */ }
        if (n > 45) { clearInterval(timer); setScraping(false); load() }
      }, 4000)
    } catch (e) {
      setScraping(false)
      const err = e as { response?: { data?: { error?: string } } }
      message.warning(err.response?.data?.error || '抓取失败')
    }
  }

  // rd-web 办理：触发后端 RPA → 轮询状态 → 完成刷新
  const runRdwebAction = async (
    d: Distribution, action: 'accept' | 'reject' | 'withdraw', officer?: string, opinion?: string,
  ) => {
    setActing(true)
    try {
      const res = await rdwebAction(d.id, action, officer, opinion)
      message.success(res.data.message || '已提交办理')
      let n = 0
      const timer = setInterval(async () => {
        n += 1
        try {
          const st = await rdwebActionStatus()
          if (!st.data.data.running) {
            clearInterval(timer); setActing(false)
            const msg = st.data.data.last_msg || '办理完成'
            if (st.data.data.ok) message.success(msg)
            else message.warning(msg + '（请到 rd-web 核对）')
            load()
          }
        } catch { /* ignore */ }
        if (n > 30) { clearInterval(timer); setActing(false); load() }
      }, 4000)
    } catch (e) {
      setActing(false)
      const err = e as { response?: { data?: { error?: string } } }
      message.warning(err.response?.data?.error || '办理失败')
    }
  }

  const confirmReject = (d: Distribution) => {
    let opinion = ''
    Modal.confirm({
      title: `驳回「${d.name || d.serial_no}」？`,
      content: (
        <div>
          <Alert type="warning" showIcon style={{ marginBottom: 8 }}
            message="将在 rd-web 真实驳回并盖陈梦霞电子签名、退回发起人，请确认。" />
          <Input.TextArea placeholder="驳回意见（选填）" rows={3}
            onChange={e => { opinion = e.target.value }} />
        </div>
      ),
      okText: '确认驳回', okButtonProps: { danger: true },
      onOk: () => runRdwebAction(d, 'reject', '', opinion),
    })
  }

  const confirmWithdraw = (d: Distribution) => {
    Modal.confirm({
      title: `撤回「${d.name || d.serial_no}」？`,
      content: '将在 rd-web 把该审签表从下一节点撤回到「采购部接收」（陈梦霞），可重新办理。',
      okText: '确认撤回',
      onOk: () => runRdwebAction(d, 'withdraw'),
    })
  }

  const doUpload = async (file: File) => {
    if (!attachFor) return
    setUploading(true)
    try { await uploadDistAttachment(attachFor.id, file); message.success('已上传'); await load() }
    catch { message.error('上传失败') }
    finally { setUploading(false) }
  }

  // 醒目的「审签表」按钮（流程打印PDF），置于操作区最前，便于查找
  const flowBtn = (d: Distribution) => {
    const fs = flowSheet(d)
    return fs ? (
      <Button size="small" type="primary" icon={<FileDoneOutlined />}
        style={{ background: '#d4380d', borderColor: '#d4380d', fontWeight: 700, letterSpacing: 1 }}
        onClick={() => previewAtt(d, fs)}>审签表</Button>
    ) : (
      <Tooltip title="尚未抓到审签表（流程打印 PDF）">
        <Button size="small" danger disabled icon={<FileDoneOutlined />} style={{ fontWeight: 700 }}>审签表缺</Button>
      </Tooltip>
    )
  }
  const printBtn = (d: Distribution) => (
    <Button size="small" icon={<PrinterOutlined />} onClick={() => openPrint(d)}>一键打印</Button>
  )

  const toCard = (d: Distribution): RecordCardData => ({
    key: d.id,
    accent: FORM_TYPE_ACCENT[d.form_type] || ACCENT[d.status] || '#1a73e8',
    title: isManager ? (
      <Tooltip title="点击项目名称编辑">
        <a style={{ fontWeight: 600, color: 'inherit' }} onClick={() => openEdit(d)}>{d.name || '（未命名项目）'}</a>
      </Tooltip>
    ) : <span style={{ fontWeight: 600 }}>{d.name || '（未命名项目）'}</span>,
    subtitle: (
      <Text type="secondary">
        {d.serial_no ? `流水号 ${d.serial_no}` : ''}{d.originator ? `　发起人 ${d.originator}` : ''}
      </Text>
    ),
    statusText: d.status,
    statusColor: STATUS_COLOR[d.status],
    tags: (
      <Space size={4}>
        <Tag color={FORM_TYPE_COLOR[d.form_type] || 'default'}>{d.form_type || '采购需求审签表'}</Tag>
        <Tag bordered={false} color="blue">{d.source}</Tag>
      </Space>
    ),
    fields: (d.form_type && d.form_type !== '采购需求审签表')
      ? [
          { label: '经办人', value: d.officer || <Text type="warning">未指定</Text> },
          // 照搬该流程在 rd-web 的全部字段
          ...Object.entries(parseExtra(d.extra)).slice(0, 16)
            .map(([k, v]) => ({ label: k, value: (v as string) || '—' })),
          { label: '附件', value: d.attachments?.length ? `${d.attachments.length} 个` : '—' },
        ]
      : [
          { label: '归口科室', value: d.manage_dept || '—' },
          { label: '需求科室', value: d.demand_dept || '—' },
          { label: '采购方式', value: d.method ? <Tag color={METHOD_COLOR[d.method] || 'default'} style={{ margin: 0 }}>{d.method}</Tag> : '—' },
          { label: '采购组织形式', value: d.org_form || '—' },
          { label: '预算金额', value: fmtBudget(d.budget) },
          { label: '限价金额', value: fmtBudget(d.price_limit) },
          { label: '项目编号', value: d.project_number || '—' },
          { label: '经办人', value: d.officer || <Text type="warning">未指定</Text> },
          { label: '代理机构', value: d.agency_name || (['院内竞选', '政府采购', '院内单一来源采购'].includes(d.method) ? <Text type="secondary">—</Text> : '不走代理') },
          { label: '附件', value: d.attachments?.length ? `${d.attachments.length} 个` : '—' },
        ],
    actions: (
      <Space size={4} wrap>
        {d.status === '已分发' && d.officer === user?.display_name && (
          <>
            <Button size="small" type="primary" icon={<PlusCircleOutlined />}
              style={{ background: '#52c41a', borderColor: '#52c41a', fontWeight: 600 }}
              onClick={() => navigate(`/new?from_dist=${d.id}`)}>立项</Button>
            {/* 已在 4.1 单独立项的（立项时项目常被改名，系统无法自动匹配）在这里手动销账 */}
            <Button size="small" onClick={() => openLink(d)}>已立项·关联</Button>
            <Popconfirm title="标记为不立项？" description="该条目将移出待办，可在「已取消」中撤销。"
              onConfirm={() => doCancel(d)}>
              <Button size="small">不立项</Button>
            </Popconfirm>
          </>
        )}
        {['已立项', '已取消'].includes(d.status) && d.officer === user?.display_name && (
          <Popconfirm title={d.status === '已取消' ? '撤销「不立项」？' : '撤销关联？'}
            description="该条目将退回「已分发」。" onConfirm={() => doUnlink(d)}>
            <Button size="small">{d.status === '已取消' ? '恢复' : '撤销关联'}</Button>
          </Popconfirm>
        )}
        {/* rd-web 办理：仅采购部助理、且有审签表流水号的记录 */}
        {isManager && d.serial_no && d.status === '待分发' && (
          <>
            <Button size="small" type="primary" ghost loading={acting}
              onClick={() => { setAcceptFor(d); setAcceptOfficer(''); setAcceptOpinion('') }}>接收</Button>
            <Button size="small" danger ghost loading={acting} onClick={() => confirmReject(d)}>驳回</Button>
          </>
        )}
        {isManager && d.serial_no && d.status === '已分发' && (
          <Button size="small" loading={acting} onClick={() => confirmWithdraw(d)}>撤回</Button>
        )}
        {flowBtn(d)}
        {printBtn(d)}
        <Button size="small" icon={<PaperClipOutlined />} onClick={() => setAttachFor(d)}>
          附件{d.attachments?.length ? `(${d.attachments.length})` : ''}
        </Button>
        {isManager && <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(d)}>编辑</Button>}
        {isManager && ['院内竞选', '政府采购', '院内单一来源采购'].includes(d.method) && (
          <Button size="small" icon={<RetweetOutlined />} onClick={() => handleReassign(d)}>改派代理</Button>
        )}
        {isManager && (
          <Popconfirm title="确认删除该分发记录？" onConfirm={() => handleDelete(d)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        )}
      </Space>
    ),
  })

  const tabRows = rows.filter(r => r.status === tab)
  const listFilter = useProjectListFilter(tabRows, DIST_ACCESSORS)
  const filtered = listFilter.filtered
  const counts = (s: string) => rows.filter(r => r.status === s).length

  // 项目池是黄新博本人用自己 rd-web 账号抓来的医院内部资料：
  // 仅本人 + 采购部助理/负责人/管理员可见，其余经办人及代理机构挡在门外。
  const POOL_USERS = ['黄新博', 'agent-hxb']   // 黄新博本人 + 他的 AI 经办人账号
  const canSeePool = ['assistant', 'pd_assistant', 'leader'].includes(role)
    || !!user?.is_admin || POOL_USERS.includes(user?.username || '')
  if (!canSeePool) {
    return (
      <Card>
        <Alert type="error" showIcon message="无权访问"
          description="项目池为经办人本人抓取的医院内部资料，未对当前账号开放。" />
      </Card>
    )
  }

  return (
    <Card
      title={poolMode ? '4.0 项目池（我的）' : '采购项目分发'}
      extra={poolMode ? (
        <Space wrap>
          <Button type="primary" icon={<CloudDownloadOutlined />} loading={scraping} onClick={handleScrapeMine}>
            抓取分发给我的
          </Button>
        </Space>
      ) : (
        <Space wrap>
          {/* 派单前先看这家代理最近考核如何——低于90分要暂停下一轮拟派。
              放在 isManager 外面：经办人也要能进考核，别再被角色挡住 */}
          <Button icon={<AuditOutlined />} onClick={() => navigate('/agency-assessment')}>
            代理机构考核
          </Button>
          {/* 以下是分发管理动作，仍只给助理/负责人/管理员 */}
          {isManager && (
            <>
              <Button icon={<KeyOutlined />} onClick={openAccts}>rd-web账号</Button>
              <Button icon={<SafetyCertificateOutlined />} onClick={() => setValidateOpen(true)}>验证漏项</Button>
              <Button icon={<ExportOutlined />} onClick={() => setExportOpen(true)}>导出清单</Button>
              <Button icon={<CloudDownloadOutlined />} loading={scraping} onClick={handleScrape}>
                从 rd-web 抓取
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建分发</Button>
            </>
          )}
        </Space>
      )}
    >
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={TABS.map(s => ({ key: s, label: `${s}（${counts(s)}）` }))}
      />
      <div style={{ marginBottom: 12 }}>
        <ProjectListToolbar f={listFilter} placeholder="搜索项目名称 / 编号 / 代理机构" />
      </div>
      <RecordCards dataSource={filtered} toCard={toCard} loading={loading} emptyText={`暂无${tab}项目`} />

      {/* 新建/编辑分发 */}
      <Drawer
        title={editingId ? '编辑分发' : '新建分发'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={520}
        extra={<Button type="primary" loading={saving} onClick={handleSave}>保存</Button>}
      >
        <Form form={form} layout="vertical">
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item label="采购需求流水号" name="serial_no" style={{ flex: 1 }}>
              <Input placeholder="rd-web 流水号（抓取自动带入）" />
            </Form.Item>
            <Form.Item label="发起人" name="originator" style={{ width: 130 }}>
              <Input placeholder="发起人" />
            </Form.Item>
          </Space>
          <Form.Item label="项目名称" name="name" rules={[{ required: true, message: '请填写项目名称' }]}>
            <Input placeholder="项目名称" />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item label="归口管理科室" name="manage_dept" style={{ flex: 1 }}>
              <Input placeholder="归口管理科室" />
            </Form.Item>
            <Form.Item label="需求科室" name="demand_dept" style={{ flex: 1 }}>
              <Input placeholder="需求科室" />
            </Form.Item>
          </Space>
          <Form.Item label="项目基本情况" name="content">
            <TextArea rows={3} placeholder="项目基本情况/范围" />
          </Form.Item>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item label="预算金额（元）" name="budget" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="预算" />
            </Form.Item>
            <Form.Item label="限价金额（元）" name="price_limit" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="限价" />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item label="采购组织形式" name="org_form" style={{ flex: 1 }}>
              <Input placeholder="如：自行采购 / 委托代理" />
            </Form.Item>
            <Form.Item label="项目编号" name="project_number" style={{ flex: 1 }}>
              <Input placeholder="项目编号（可空）" />
            </Form.Item>
          </Space>
          <Form.Item label="采购方式" name="method" rules={[{ required: true }]}>
            <Select options={METHODS.map(m => ({ value: m, label: m }))} />
          </Form.Item>
          {watchMethod === '政府采购' && (
            <Form.Item label="是否政采中心项目" name="is_central" valuePropName="checked"
              tooltip="集中采购 / 医疗设备采购 → 指派内江市政府采购中心；否则在 7 家中轮派">
              <Switch checkedChildren="集采/医疗设备(走政采中心)" unCheckedChildren="否(走轮派)" />
            </Form.Item>
          )}
          <Form.Item label="指定经办人" name="officer">
            <Select allowClear showSearch placeholder="分发给哪位经办人"
              options={OFFICERS.map(o => ({ value: o, label: o }))} />
          </Form.Item>
          <Divider />
          <Text type="secondary" style={{ fontSize: 12 }}>
            保存后系统按规则自动指派代理机构（院内竞选/政府采购非政采中心 → 顺序轮派）。附件在保存后于卡片「附件」处上传。
          </Text>
        </Form>
      </Drawer>

      {/* 附件 */}
      <Drawer
        title={`资料 — ${attachFor?.name || ''}`}
        open={!!attachFor}
        onClose={() => setAttachFor(null)}
        width={540}
        extra={attachFor && (
          <Button type="primary" icon={<PrinterOutlined />} onClick={() => openPrint(attachFor)}>一键打印</Button>
        )}
      >
        {attachFor && (
          <div>
            {(attachFor.attachments || []).length === 0 ? (
              <Text type="secondary">暂无资料</Text>
            ) : (
              // 审签表置顶
              [...(attachFor.attachments || [])]
                .sort((a, b) => (a.category === '审签表' ? -1 : 0) - (b.category === '审签表' ? -1 : 0))
                .map(att => {
                  const isFlow = att.category === '审签表'
                  return (
                    <div key={att.id} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: isFlow ? '10px 12px' : '6px 10px', borderRadius: 6, marginBottom: isFlow ? 8 : 4,
                      background: isFlow ? '#fff7e6' : '#fafafa',
                      border: isFlow ? '2px solid #fa8c16' : '1px solid #f0f0f0',
                    }}>
                      <Space size={6}>
                        {isFlow && <Tag color="volcano" style={{ fontWeight: 700, margin: 0 }}>审签表</Tag>}
                        <Tooltip title={att.original_name}>
                          <span style={{
                            fontSize: isFlow ? 15 : 13, fontWeight: isFlow ? 700 : 400,
                            color: isFlow ? '#d4380d' : undefined,
                            maxWidth: 230, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block',
                          }}>
                            {isFlow ? '采购需求审签表（流程打印）' : att.original_name}
                          </span>
                        </Tooltip>
                      </Space>
                      <Space size={2}>
                        <Text type="secondary" style={{ fontSize: 11 }}>{fmtSize(att.file_size)}</Text>
                        {(isFlow || isPreviewable(att.original_name)) && (
                          <Button size="small" type={isFlow ? 'primary' : 'link'} icon={<EyeOutlined />}
                            onClick={() => previewAtt(attachFor, att)}>{isFlow ? '预览' : ''}</Button>
                        )}
                        <Button size="small" type="link" icon={<DownloadOutlined />}
                          href={distAttachmentDownloadUrl(attachFor.id, att.id)} download={att.original_name} />
                        {isManager && (
                          <Popconfirm title="删除该资料？" onConfirm={async () => {
                            try { await deleteDistAttachment(attachFor.id, att.id); message.success('已删除'); await load() }
                            catch { message.error('删除失败') }
                          }}>
                            <Button size="small" type="link" danger icon={<DeleteOutlined />} />
                          </Popconfirm>
                        )}
                      </Space>
                    </div>
                  )
                })
            )}
            {isManager && (
              <Upload showUploadList={false} beforeUpload={(f) => { doUpload(f as File); return false }}>
                <Button icon={<PaperClipOutlined />} loading={uploading} style={{ marginTop: 8 }}>添加附件</Button>
              </Upload>
            )}
          </div>
        )}
      </Drawer>

      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        siblings={pvList}
        index={pvIdx}
        onNavigate={i => setPreview(p => ({ ...p, url: pvList[i].url, name: pvList[i].filename }))}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />

      {/* rd-web 接收：指定经办人 + 意见（提交 = 真实盖章并推进流程）*/}
      <Modal
        title={`接收并指定经办人 — ${acceptFor?.name || acceptFor?.serial_no || ''}`}
        open={!!acceptFor}
        confirmLoading={acting}
        okText="确认接收"
        onCancel={() => setAcceptFor(null)}
        onOk={async () => {
          if (!acceptFor) return
          if (!acceptOfficer.trim()) { message.warning('请填写项目经办人姓名'); return }
          const d = acceptFor
          setAcceptFor(null)
          await runRdwebAction(d, 'accept', acceptOfficer.trim(), acceptOpinion.trim())
        }}
      >
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message="确认后将在 rd-web 真实「接收」该审签表、盖陈梦霞电子签名并推进到经办人节点。" />
        <div style={{ marginBottom: 8 }}>
          <Text>项目经办人 *</Text>
          <Input placeholder="如：黄新博（须与 rd-web 采购部成员姓名一致）"
            value={acceptOfficer} onChange={e => setAcceptOfficer(e.target.value)} />
        </div>
        <div>
          <Text>意见（选填）</Text>
          <Input.TextArea rows={3} value={acceptOpinion}
            onChange={e => setAcceptOpinion(e.target.value)} />
        </div>
      </Modal>

      {/* 导出清单 */}
      <Modal
        title="导出项目分发清单"
        open={exportOpen}
        onCancel={() => setExportOpen(false)}
        okText="导出 Excel"
        onOk={() => {
          const from = exportRange?.[0]?.format('YYYY-MM-DD') || ''
          const to = exportRange?.[1]?.format('YYYY-MM-DD') || ''
          window.open(distExportUrl({ date_from: from, date_to: to, methods: exportMethods }), '_blank')
          setExportOpen(false)
        }}
      >
        <Form layout="vertical">
          <Form.Item label="创建时间范围（不选=全部）">
            <DatePicker.RangePicker style={{ width: '100%' }} value={exportRange}
              onChange={(v) => setExportRange(v as [dayjs.Dayjs | null, dayjs.Dayjs | null] | null)} />
          </Form.Item>
          <Form.Item label="采购方式（可多选，不选=全部）">
            <Select mode="multiple" allowClear placeholder="全部采购方式" value={exportMethods}
              onChange={(v) => setExportMethods(v)}
              options={METHODS.map(m => ({ value: m, label: m }))} />
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 12 }}>
            导出含全部字段（流水号/项目名称/归口科室/需求科室/预算/限价/采购组织形式/采购方式/项目编号/内容/经办人/代理机构/状态等）。
          </Text>
        </Form>
      </Modal>

      {/* 一键打印：勾选要打印的附件（默认全选） */}
      <Modal
        title={`一键打印 — ${printFor?.name || ''}`}
        open={!!printFor}
        onCancel={() => setPrintFor(null)}
        okText="打印选中"
        onOk={() => {
          if (!printFor) return
          const pdfIds = (printFor.attachments || [])
            .filter(a => printSel.includes(a.id) && /\.pdf$/i.test(a.original_name))
            .map(a => a.id)
          if (pdfIds.length === 0) { message.warning('选中的项里没有可打印的 PDF'); return }
          window.open(distPrintUrl(printFor.id, pdfIds), '_blank')  // 合并为一个PDF，一次打印
          setPrintFor(null)
        }}
      >
        {printFor && ((printFor.attachments || []).length === 0 ? (
          <Text type="secondary">该项目暂无可打印资料</Text>
        ) : (
          <>
            <Text type="secondary" style={{ fontSize: 12 }}>默认全选；仅 PDF 能在浏览器打印，docx 等会自动跳过。</Text>
            <Checkbox.Group style={{ display: 'block', marginTop: 10 }}
              value={printSel} onChange={(v) => setPrintSel(v as number[])}>
              {[...(printFor.attachments || [])]
                .sort((a, b) => (a.category === '审签表' ? -1 : 0) - (b.category === '审签表' ? -1 : 0))
                .map(att => {
                  const isFlow = att.category === '审签表'
                  const isPdf = /\.pdf$/i.test(att.original_name)
                  return (
                    <div key={att.id} style={{ padding: '4px 0' }}>
                      <Checkbox value={att.id}>
                        {isFlow && <Tag color="volcano" style={{ fontWeight: 700 }}>审签表</Tag>}
                        <span style={{ fontWeight: isFlow ? 700 : 400, color: isFlow ? '#d4380d' : undefined }}>
                          {isFlow ? '采购需求审签表（流程打印）' : att.original_name}
                        </span>
                        {!isPdf && <Text type="secondary" style={{ fontSize: 11 }}>（非PDF，不可打印）</Text>}
                      </Checkbox>
                    </div>
                  )
                })}
            </Checkbox.Group>
          </>
        ))}
      </Modal>

      {/* 验证漏项 */}
      <Modal
        title="验证漏项"
        open={validateOpen}
        onCancel={() => setValidateOpen(false)}
        footer={<Button onClick={() => setValidateOpen(false)}>关闭</Button>}
        width={600}
      >
        {(() => {
          const bad = rows.map(r => ({ r, miss: missingOf(r) })).filter(x => x.miss.length > 0)
          if (bad.length === 0) {
            return <Alert type="success" showIcon message={`全部 ${rows.length} 个项目资料齐全，无漏项。`} />
          }
          return (
            <>
              <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                message={`共 ${bad.length} 个项目存在漏项，请补全后再办理。`} />
              <List size="small" dataSource={bad}
                renderItem={({ r, miss }) => (
                  <List.Item actions={[
                    <Button key="att" size="small" type="link" onClick={() => { setValidateOpen(false); setAttachFor(r) }}>查看</Button>,
                  ]}>
                    <List.Item.Meta
                      title={<span>{r.name || '（未命名）'} <Text type="secondary" style={{ fontSize: 12 }}>{r.serial_no}</Text></span>}
                      description={<span style={{ color: '#d4380d' }}>缺：{miss.join('、')}</span>}
                    />
                  </List.Item>
                )} />
            </>
          )
        })()}
      </Modal>

      {/* rd-web 账号维护 */}
      <Drawer
        title="rd-web 账号维护"
        open={acctOpen}
        onClose={() => setAcctOpen(false)}
        width={560}
      >
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="账号变动时在此更新。用途选「分发」的账号(陈梦霞)会被自动抓取使用；「执行」账号供经办人办理。" />
        <Form form={acctForm} layout="vertical">
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item label="姓名/用途" name="owner" rules={[{ required: true, message: '填姓名' }]} style={{ flex: 1 }}>
              <Input placeholder="如 陈梦霞 / 黄新博" />
            </Form.Item>
            <Form.Item label="用途" name="usage" style={{ width: 110 }}>
              <Select options={[{ value: '分发', label: '分发(抓取)' }, { value: '执行', label: '执行' }]} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item label="登录手机号" name="phone" rules={[{ required: true, message: '填手机号' }]} style={{ flex: 1 }}>
              <Input placeholder="登录手机号" />
            </Form.Item>
            <Form.Item label="登录密码" name="password" style={{ flex: 1 }}>
              <Input.Password placeholder="登录密码" visibilityToggle />
            </Form.Item>
          </Space>
          <Form.Item label="备注" name="note">
            <Input placeholder="备注（可空）" />
          </Form.Item>
          <Space>
            <Button type="primary" onClick={saveAcct}>{acctEditId ? '保存修改' : '添加账号'}</Button>
            {acctEditId && <Button onClick={() => { setAcctEditId(null); acctForm.resetFields(); acctForm.setFieldsValue({ usage: '执行' }) }}>取消编辑</Button>}
          </Space>
        </Form>
        <Divider>已有账号</Divider>
        <List size="small" dataSource={accts} locale={{ emptyText: '暂无账号' }}
          renderItem={(a) => (
            <List.Item actions={[
              <Button key="e" size="small" type="link" onClick={() => editAcct(a)}>编辑</Button>,
              <Popconfirm key="d" title="删除该账号？" onConfirm={() => delAcct(a.id)}>
                <Button size="small" type="link" danger>删除</Button>
              </Popconfirm>,
            ]}>
              <List.Item.Meta
                title={<span>{a.owner} <Tag color={a.usage === '分发' ? 'volcano' : 'blue'}>{a.usage}</Tag></span>}
                description={<Text type="secondary" style={{ fontSize: 12 }}>{a.phone} · 密码 {a.password ? '已设置' : '（空）'}{a.note ? ` · ${a.note}` : ''}</Text>}
              />
            </List.Item>
          )} />
      </Drawer>

      {/* 对账：把池内条目关联到已在 4.1 单独立项的项目 */}
      <Modal
        title="关联已立项项目"
        open={!!linkFor}
        onCancel={() => setLinkFor(null)}
        onOk={doLink}
        okText="关联"
        okButtonProps={{ disabled: !linkPid }}
        confirmLoading={linking}
        destroyOnHidden
        width={620}
      >
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="这条采购需求你已经在「4.1 项目立项」单独建过项目了？选中它即可销账。"
          description="立项时项目名称常被改写，系统无法自动匹配，需要你指认一次。关联后本条目转为「已立项」。" />
        <div style={{ marginBottom: 8 }}>
          <Text type="secondary">项目池条目：</Text>
          <Text strong>{linkFor?.name}</Text>
          {linkFor?.serial_no ? <Text type="secondary">（流水号 {linkFor.serial_no}）</Text> : null}
        </div>
        <Select
          showSearch
          style={{ width: '100%' }}
          placeholder="搜索并选择已立项的项目（按名称或编号）"
          value={linkPid}
          onChange={setLinkPid}
          filterOption={(input, opt) => (opt?.label as string).toLowerCase().includes(input.toLowerCase())}
          options={linkOpts.map(p => ({
            value: p.id,
            label: `${p.number || '无编号'} — ${p.name}`,
          }))}
        />
      </Modal>
    </Card>
  )
}
