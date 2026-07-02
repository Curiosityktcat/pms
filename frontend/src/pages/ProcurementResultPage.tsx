import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import {
  Button,
  Drawer,
  Form,
  Input,
  Select,
  Radio,
  InputNumber,
  Card,
  Space,
  Tag,
  Tabs,
  App,
  Typography,
  Row,
  Col,
  Divider,
  Checkbox,
  Upload,
  List,
  Popconfirm,
  Alert,
  Modal,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  FileWordOutlined,
  CheckCircleOutlined,
  RollbackOutlined,
  SaveOutlined,
  MinusCircleOutlined,
  UploadOutlined,
  PaperClipOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileDoneOutlined,
} from '@ant-design/icons'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import {
  listResults,
  createResult,
  updateResult,
  deleteResult,
  submitResult,
  confirmResult,
  revokeResult,
  resultWordUrl,
  listPriceAttachments,
  uploadPriceAttachmentUrl,
  downloadPriceAttachment,
  pricePreviewUrl,
  deletePriceAttachment,
  listAwardNotice,
  uploadAwardNoticeUrl,
  downloadAwardNotice,
  awardNoticePreviewUrl,
  deleteAwardNotice,
  type ProcurementResult,
  type ResultPackage,
  type PriceAttachment,
} from '../services/procurementResult'
import { getProjects, type Project } from '../services/project'
import { getProjectRounds } from '../services/procurementDoc'
import { useAuth } from '../hooks/useAuth'
import { useFocusTarget, flashRow } from '../hooks/useFocusRow'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'

const { Title, Text } = Typography

function fmtSize(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

// ─── 简单中文大写转换 ──────────────────────────────────────────────────────────
function toCnAmount(amount: number): string {
  const digits = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖']
  if (amount === 0) return '零元整'
  const result = amount.toFixed(2)
  const [intStr, decStr] = result.split('.')
  const intNum = parseInt(intStr, 10)
  const yi = Math.floor(intNum / 100000000)
  const wan = Math.floor((intNum % 100000000) / 10000)
  const qian = intNum % 10000
  const parts: string[] = []
  if (yi) parts.push(`${yi}亿`)
  if (wan) parts.push(`${wan}万`)
  if (qian) parts.push(`${qian}`)
  let cn = parts.join('') + '元'
  const fen = parseInt(decStr, 10)
  if (fen === 0) {
    cn += '整'
  } else if (decStr[0] !== '0') {
    cn += `${digits[parseInt(decStr[0], 10)]}角`
    if (decStr[1] !== '0') cn += `${digits[parseInt(decStr[1], 10)]}分`
  } else {
    cn += `零${digits[parseInt(decStr[1], 10)]}分`
  }
  return cn
}

// ─── 空包 ──────────────────────────────────────────────────────────────────────
const emptyPackage = (): ResultPackage => ({
  result: '成交',
  winner: '',
  amount: 0,
  amount_cn: '',
  note: '',
})

// ─── 默认表单值 ────────────────────────────────────────────────────────────────
const defaultFormValues = {
  project_id: undefined as number | undefined,
  round_number: 1,
  bid_time: '',
  agency_name: '',
  procurement_method: '院内竞选',
  notes: '此结果为评审委员会评审结果',
  confirm_date: '',
}

// ─── 采购结果摘要 ──────────────────────────────────────────────────────────────
function packagesSummary(packages: ResultPackage[]): string {
  if (!packages || packages.length === 0) return '—'
  return packages
    .map((p, i) => {
      if (p.result === '成交') {
        if (p.unit_price_attached) return `包${i + 1}:成交 单价见附件`
        // 金额按原值显示，不进「万」、不四舍五入（仅加千分位便于阅读）
        const amtStr = p.amount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
        return `包${i + 1}:成交 ¥${amtStr}元`
      }
      return `包${i + 1}:废标`
    })
    .join(' / ')
}

export default function ProcurementResultPage() {
  const { message, modal } = App.useApp()
  const { user } = useAuth()
  // 确认/撤回由采购人方完成，代理机构只能编辑/提交内容
  const canConfirm = ['officer', 'assistant', 'leader'].includes(user?.role || '')
  const isAgency = user?.role === 'agency'
  const [results, setResults] = useState<ProcurementResult[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [tabStatus, setTabStatus] = useState<'草稿' | '待确认' | '已确认'>('草稿')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [packages, setPackages] = useState<ResultPackage[]>([emptyPackage()])
  // 包是否由轮次驱动（锁定包集合，不可随意增删）
  const [roundLocked, setRoundLocked] = useState(false)
  // 点项目名在线预览生成的确认函 Word
  const [docPreview, setDocPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })
  // 中标通知书管理弹窗（已确认结果）
  const [awardModal, setAwardModal] = useState<{ open: boolean; result?: ProcurementResult }>({ open: false })
  // 代理机构或采购人方可上传中标通知书
  const canUploadAward = isAgency || canConfirm
  const [form] = Form.useForm()

  // ─── 加载数据 ────────────────────────────────────────────────────────────────
  const loadResults = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listResults()
      setResults(res.data.data || [])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    loadResults()
    getProjects().then((res) => setProjects(res.data.data || []))
  }, [loadResults])

  // ─── 按 tab 过滤 ─────────────────────────────────────────────────────────────
  const filtered = results.filter((r) => r.status === tabStatus)

  // ─── 项目 map ────────────────────────────────────────────────────────────────
  const projectMap = Object.fromEntries(projects.map((p) => [p.id, p]))

  // ─── 可做采购结果的项目：当前轮已开标(可开标)且本轮尚未录结果 ──────────────────
  // current_stage==='result' 已涵盖：代理轨道 + 需求/文件已确认 + 已发公告 + 已确认可开标。
  // 再排除当前轮已存在结果(任意状态)的项目，避免同一轮重复新建。
  const resultRoundKey = new Set(results.map((r) => `${r.project_id}-${r.round_number || 1}`))
  const eligibleProjects = projects.filter(
    (p) =>
      p.current_stage === 'result' &&
      !resultRoundKey.has(`${p.id}-${p.current_round ?? 1}`),
  )

  // 编辑既有结果时，其已绑定项目可能已进入下一轮（文件确认被清零）而不再合规，
  // 这里把它补进下拉，保证项目名能正常显示、不至于变空白。
  const boundProjectId = Form.useWatch('project_id', form)
  const projectOptions = [...eligibleProjects]
  if (boundProjectId && !projectOptions.some((p) => p.id === boundProjectId)) {
    const bound = projectMap[boundProjectId]
    if (bound) projectOptions.unshift(bound)
  }
  // 招单价项目（立项未填固定预算）：成交可选「单价详见附件」并上传附件
  const boundProject = boundProjectId ? projectMap[boundProjectId] : undefined
  const isUnitPriceProject = !!boundProject && !boundProject.amount

  // ─── 打开新建 ────────────────────────────────────────────────────────────────
  const openCreate = () => {
    setEditingId(null)
    setPackages([emptyPackage()])
    setRoundLocked(false)
    form.resetFields()
    form.setFieldsValue({ ...defaultFormValues })
    setDrawerOpen(true)
  }

  // ─── 打开编辑 ────────────────────────────────────────────────────────────────
  const openEdit = (record: ProcurementResult) => {
    setEditingId(record.id)
    const pkgs = record.packages && record.packages.length > 0
      ? record.packages
      : [emptyPackage()]
    setPackages(pkgs)
    setRoundLocked(pkgs.some(p => p.package_no != null))
    form.resetFields()
    form.setFieldsValue({
      project_id: record.project_id,
      round_number: record.round_number,
      bid_time: record.bid_time,
      agency_name: record.agency_name,
      procurement_method: record.procurement_method,
      notes: record.notes,
      confirm_date: record.confirm_date,
    })
    setDrawerOpen(true)
  }

  // ─── 选择项目后自动填充 + 按当前轮次拉取在跑的包 ────────────────────────────
  const handleProjectChange = async (projectId: number) => {
    const proj = projectMap[projectId]
    if (!proj) return
    form.setFieldsValue({
      agency_name: proj.agency_name || '',
      bid_time: proj.bid_time || '',
    })
    try {
      const res = await getProjectRounds(projectId)
      const { packages: pkgs, current_round } = res.data.data
      // 本轮在跑的包 = 状态进行中的包（已中标的不再参与本轮）
      const active = pkgs.filter(p => p.status === '进行中').sort((a, b) => a.package_no - b.package_no)
      if (active.length > 0) {
        setPackages(active.map(p => ({ ...emptyPackage(), package_no: p.package_no })))
        setRoundLocked(true)
        form.setFieldsValue({ round_number: current_round || 1 })
      } else {
        setRoundLocked(false)
      }
    } catch {
      setRoundLocked(false)
    }
  }

  // 待办「去处理」跳转：已有结果→切到其状态页签并高亮；否则打开新建并预选该项目
  useFocusTarget(!loading && projects.length > 0, (id) => {
    const existing = results.find((r) => r.project_id === id)
    if (existing) {
      setTabStatus(existing.status as '草稿' | '待确认' | '已确认')
      flashRow(existing.id)
    } else {
      openCreate()
      form.setFieldsValue({ project_id: id })
      handleProjectChange(id)
    }
  })

  // ─── 包字段变更 ──────────────────────────────────────────────────────────────
  const updatePackage = (idx: number, field: keyof ResultPackage, value: unknown) => {
    setPackages((prev) => {
      const next = [...prev]
      next[idx] = { ...next[idx], [field]: value }
      return next
    })
  }

  const addPackage = () => setPackages((prev) => [...prev, emptyPackage()])

  const removePackage = (idx: number) => {
    setPackages((prev) => prev.filter((_, i) => i !== idx))
  }

  // ─── 保存 ────────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    let values: Record<string, unknown>
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setSaving(true)
    try {
      const payload = { ...values, packages }
      if (editingId) {
        await updateResult(editingId, payload as Partial<ProcurementResult>)
        message.success('保存成功')
      } else {
        await createResult(payload as Partial<ProcurementResult> & { packages: ResultPackage[] })
        message.success('新建成功')
      }
      setDrawerOpen(false)
      loadResults()
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  // ─── 确认 ────────────────────────────────────────────────────────────────────
  const handleConfirm = (record: ProcurementResult) => {
    modal.confirm({
      title: '确认采购结果',
      content: `确认后：成交的包将进入合同阶段，废标的包系统会自动开启下一轮采购。是否继续？`,
      onOk: async () => {
        try {
          const res = await confirmResult(record.id)
          message.success(res.data.message || '已确认')
          loadResults()
          getProjects().then((r) => setProjects(r.data.data || []))
        } catch (err: unknown) {
          const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
          message.error(m || '操作失败')
        }
      },
    })
  }

  // ─── 提交（代理：草稿→待确认） ───────────────────────────────────────────────
  const handleSubmit = (record: ProcurementResult) => {
    modal.confirm({
      title: '提交采购结果',
      content: '提交后将进入「待确认」，由经办人核对确认。是否提交？',
      onOk: async () => {
        try {
          const res = await submitResult(record.id)
          message.success(res.data.message || '已提交')
          loadResults()
        } catch (err: unknown) {
          const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
          message.error(m || '提交失败')
        }
      },
    })
  }

  // ─── 撤回 ────────────────────────────────────────────────────────────────────
  const handleRevoke = async (record: ProcurementResult) => {
    try {
      await revokeResult(record.id)
      message.success('已撤回为草稿')
      loadResults()
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '操作失败')
    }
  }

  // ─── 删除 ────────────────────────────────────────────────────────────────────
  const handleDelete = (record: ProcurementResult) => {
    modal.confirm({
      title: '删除确认',
      content: '确定删除此结果确认函吗？此操作不可撤销。',
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteResult(record.id)
          message.success('已删除')
          loadResults()
        } catch {
          message.error('删除失败')
        }
      },
    })
  }

  // ─── 下载 Word ───────────────────────────────────────────────────────────────
  const handleDownloadWord = (record: ProcurementResult) => {
    window.open(resultWordUrl(record.id), '_blank')
  }

  // ─── 采购结果 → 卡片 ─────────────────────────────────────────────────────────
  const STATUS_COLOR: Record<string, string> = { 已确认: 'green', 待确认: 'orange', 草稿: 'default' }
  const ACCENT: Record<string, string> = { 已确认: '#34a853', 待确认: '#f9ab00', 草稿: '#1a73e8' }
  const resultToCard = (r: ProcurementResult): RecordCardData => {
    const name = projectMap[r.project_id]?.name || `项目#${r.project_id}`
    const rnd = r.round_number && r.round_number > 1 ? `第${r.round_number}次` : '第1次'
    return {
      key: r.id,
      accent: ACCENT[r.status] || '#1a73e8',
      title: name,
      onTitleClick: () => setDocPreview({ open: true, url: resultWordUrl(r.id), name: `${name}-采购结果确认函.docx` }),
      subtitle: `${projectMap[r.project_id]?.number || '—'} · ${rnd}`,
      statusText: r.status,
      statusColor: STATUS_COLOR[r.status],
      tags: r.procurement_method ? <Tag bordered={false} style={{ marginInlineEnd: 0 }}>{r.procurement_method}</Tag> : undefined,
      fields: [
        { label: '竞选时间', value: r.bid_time },
        { label: '代理', value: r.agency_name },
        { label: '结果', value: packagesSummary(r.packages) },
        { label: '签章', value: r.confirm_date },
      ],
      actions: (
        <>
          {r.status === '草稿' && (
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          )}
          {r.status === '草稿' && (
            <Button size="small" type="primary" ghost icon={<CheckCircleOutlined />} onClick={() => handleSubmit(r)}>提交</Button>
          )}
          {r.status === '待确认' && canConfirm && (
            <>
              <Button size="small" type="primary" ghost icon={<CheckCircleOutlined />} onClick={() => handleConfirm(r)}>确认</Button>
              <Button size="small" icon={<RollbackOutlined />} onClick={() => handleRevoke(r)}>退回</Button>
            </>
          )}
          {r.status === '待确认' && isAgency && (
            <Button size="small" icon={<RollbackOutlined />} onClick={() => handleRevoke(r)}>撤回</Button>
          )}
          {r.status === '已确认' && r.packages?.some((p) => p.result === '成交') && (
            <Button size="small" icon={<FileDoneOutlined />} onClick={() => setAwardModal({ open: true, result: r })}>中标通知书</Button>
          )}
          {r.status === '已确认' && canConfirm && (
            <Button size="small" icon={<RollbackOutlined />} onClick={() => handleRevoke(r)}>撤回</Button>
          )}
          <Button size="small" icon={<FileWordOutlined />}
            type={r.status === '已确认' ? 'primary' : 'default'} ghost={r.status === '已确认'}
            onClick={() => handleDownloadWord(r)}>Word</Button>
          {r.status !== '已确认' && (
            <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r)}>删除</Button>
          )}
        </>
      ),
    }
  }

  return (
    <div style={{ padding: 0 }}>
      <Card
        title={<Title level={4} style={{ margin: 0 }}>采购结果确认函</Title>}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建
          </Button>
        }
        style={{ borderRadius: 8 }}
      >
        <Tabs
          activeKey={tabStatus}
          onChange={(k) => setTabStatus(k as '草稿' | '待确认' | '已确认')}
          items={[
            { key: '草稿', label: `草稿 (${results.filter((r) => r.status === '草稿').length})` },
            { key: '待确认', label: `待确认 (${results.filter((r) => r.status === '待确认').length})` },
            { key: '已确认', label: `已确认 (${results.filter((r) => r.status === '已确认').length})` },
          ]}
          style={{ marginBottom: 12 }}
        />
        <RecordCards dataSource={filtered} loading={loading} emptyText="暂无采购结果" toCard={resultToCard} />
      </Card>

      {/* ─── 新建/编辑 Drawer ─────────────────────────────────────────────── */}
      <Drawer
        title={editingId ? '编辑采购结果确认函' : '新建采购结果确认函'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={900}
        destroyOnClose
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
            >
              保存（草稿）
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical" initialValues={defaultFormValues}>
          {/* ─── 基本信息 ─────────────────────────────────────────────────── */}
          <Card
            title="基本信息"
            size="small"
            style={{ marginBottom: 16 }}
          >
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  name="project_id"
                  label="绑定项目"
                  rules={[{ required: true, message: '请选择项目' }]}
                >
                  <Select
                    showSearch
                    placeholder="请选择项目"
                    filterOption={(input, option) =>
                      (option?.label as string ?? '')
                        .toLowerCase()
                        .includes(input.toLowerCase())
                    }
                    onChange={handleProjectChange}
                    options={projectOptions.map((p) => ({
                      value: p.id,
                      label: `${p.number ? `[${p.number}] ` : ''}${p.name}`,
                    }))}
                  />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="round_number" label="竞选次数">
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="procurement_method" label="采购方式">
                  <Select
                    options={[
                      { value: '院内竞选', label: '院内竞选' },
                      { value: '院内单一来源', label: '院内单一来源' },
                      { value: '院内询价', label: '院内询价' },
                      { value: '院内议价', label: '院内议价' },
                    ]}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="bid_time" label="竞选时间">
                  <Input placeholder="例如：2026年5月30日" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="agency_name" label="招标代理机构">
                  <Input placeholder="招标代理机构名称" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="confirm_date" label="签章日期">
                  <Input placeholder="例如：2026年5月30日" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="notes" label="备注">
                  <Input />
                </Form.Item>
              </Col>
            </Row>
          </Card>

          {/* ─── 采购包结果 ───────────────────────────────────────────────── */}
          <Card
            title="采购包结果"
            size="small"
            extra={
              roundLocked ? (
                <Text type="secondary" style={{ fontSize: 12 }}>包由当前轮次自动带出，不可增删</Text>
              ) : (
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={addPackage}
                  size="small"
                >
                  添加采购包
                </Button>
              )
            }
          >
            {packages.map((pkg, idx) => (
              <PackageCard
                key={idx}
                index={idx}
                pkg={pkg}
                isUnitPriceProject={isUnitPriceProject}
                onUpdate={(field, value) => updatePackage(idx, field, value)}
                onRemove={!roundLocked && packages.length > 1 ? () => removePackage(idx) : undefined}
              />
            ))}
          </Card>

          {/* ─── 单价附件（招单价项目「单价详见附件」）──────────────────────── */}
          {isUnitPriceProject && (
            <Card title="单价附件（招单价项目）" size="small" style={{ marginTop: 16 }}>
              {editingId ? (
                <PriceAttachments resultId={editingId} locked={false} />
              ) : (
                <Alert
                  type="info"
                  showIcon
                  message="该项目立项时未填固定预算（招单价）。请先点击下方「保存（草稿）」，再回到此处上传单价附件。"
                />
              )}
            </Card>
          )}
        </Form>
      </Drawer>

      {/* ─── 点项目名：在线预览生成的确认函 Word ─────────────────────────── */}
      <FilePreviewModal
        open={docPreview.open}
        url={docPreview.url}
        filename={docPreview.name}
        onClose={() => setDocPreview((p) => ({ ...p, open: false }))}
      />

      {/* ─── 中标通知书上传/预览（已确认结果）─────────────────────────────── */}
      <Modal
        title={`中标通知书 — ${awardModal.result ? (projectMap[awardModal.result.project_id]?.name || `项目#${awardModal.result.project_id}`) : ''}`}
        open={awardModal.open}
        onCancel={() => setAwardModal({ open: false })}
        footer={null}
        width={680}
        destroyOnClose
      >
        {awardModal.result && (
          <AwardNotice resultId={awardModal.result.id} canUpload={canUploadAward} />
        )}
      </Modal>
    </div>
  )
}

// ─── 单包子卡片 ────────────────────────────────────────────────────────────────
interface PackageCardProps {
  index: number
  pkg: ResultPackage
  isUnitPriceProject?: boolean
  onUpdate: (field: keyof ResultPackage, value: unknown) => void
  onRemove?: () => void
}

function PackageCard({ index, pkg, isUnitPriceProject, onUpdate, onRemove }: PackageCardProps) {
  const handleAutoCalc = () => {
    const cn = toCnAmount(pkg.amount || 0)
    onUpdate('amount_cn', cn)
  }

  return (
    <Card
      size="small"
      style={{ marginBottom: 12, background: '#fafafa', border: '1px solid #e8e8e8' }}
      title={
        <Space>
          <span style={{ fontWeight: 600 }}>包 {pkg.package_no ?? index + 1}</span>
        </Space>
      }
      extra={
        onRemove ? (
          <Button
            type="text"
            danger
            icon={<MinusCircleOutlined />}
            size="small"
            onClick={onRemove}
          >
            删除
          </Button>
        ) : null
      }
    >
      <Row gutter={16} align="middle">
        <Col span={6}>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 12, color: '#555', display: 'block', marginBottom: 4 }}>
              评审结果
            </label>
            <Radio.Group
              value={pkg.result}
              onChange={(e) => onUpdate('result', e.target.value)}
            >
              <Radio value="成交">成交</Radio>
              <Radio value="废标">废标</Radio>
            </Radio.Group>
          </div>
        </Col>
      </Row>

      {pkg.result === '成交' && (
        <>
          <Row gutter={16}>
            <Col span={12}>
              <div style={{ marginBottom: 8 }}>
                <label style={{ fontSize: 12, color: '#555', display: 'block', marginBottom: 4 }}>
                  中标人
                </label>
                <Input
                  value={pkg.winner}
                  onChange={(e) => onUpdate('winner', e.target.value)}
                  placeholder="中标供应商名称"
                />
              </div>
            </Col>
            {isUnitPriceProject && (
              <Col span={12}>
                <div style={{ marginBottom: 8 }}>
                  <label style={{ fontSize: 12, color: 'transparent', display: 'block', marginBottom: 4 }}>
                    单价
                  </label>
                  <Checkbox
                    checked={!!pkg.unit_price_attached}
                    onChange={(e) => onUpdate('unit_price_attached', e.target.checked)}
                  >
                    单价详见附件（招单价项目）
                  </Checkbox>
                </div>
              </Col>
            )}
          </Row>

          {!(isUnitPriceProject && pkg.unit_price_attached) && (
            <>
              <Row gutter={16}>
                <Col span={12}>
                  <div style={{ marginBottom: 8 }}>
                    <label style={{ fontSize: 12, color: '#555', display: 'block', marginBottom: 4 }}>
                      中标金额（元）
                    </label>
                    <InputNumber
                      value={pkg.amount}
                      onChange={(v) => onUpdate('amount', v ?? 0)}
                      style={{ width: '100%' }}
                      min={0}
                      precision={2}
                      step={1000}
                      formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                      parser={(v) => v?.replace(/,/g, '') as unknown as number}
                    />
                  </div>
                </Col>
                <Col span={12} />
              </Row>
              <Row gutter={16}>
                <Col span={18}>
                  <div style={{ marginBottom: 8 }}>
                    <label style={{ fontSize: 12, color: '#555', display: 'block', marginBottom: 4 }}>
                      金额大写
                    </label>
                    <Input
                      value={pkg.amount_cn}
                      onChange={(e) => onUpdate('amount_cn', e.target.value)}
                      placeholder="可手动填写或点击自动计算"
                    />
                  </div>
                </Col>
                <Col span={6}>
                  <div style={{ marginBottom: 8 }}>
                    <label style={{ fontSize: 12, color: 'transparent', display: 'block', marginBottom: 4 }}>
                      操作
                    </label>
                    <Button onClick={handleAutoCalc} style={{ width: '100%' }}>
                      自动计算
                    </Button>
                  </div>
                </Col>
              </Row>
            </>
          )}

          {isUnitPriceProject && pkg.unit_price_attached && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              已选「单价详见附件」：中标金额不填，请在下方「单价附件」上传报价单。
            </Text>
          )}
        </>
      )}

      {pkg.result === '废标' && (
        <div style={{ marginBottom: 8 }}>
          <label style={{ fontSize: 12, color: '#555', display: 'block', marginBottom: 4 }}>
            废标原因
          </label>
          <Input.TextArea
            value={pkg.note}
            onChange={(e) => onUpdate('note', e.target.value)}
            rows={2}
            placeholder="请填写废标原因"
          />
        </div>
      )}

      <Divider style={{ margin: '8px 0 0' }} />
    </Card>
  )
}

// ─── 单价附件（招单价项目）上传/管理 ─────────────────────────────────────────────
// antd 自定义上传选项类型较繁琐，这里用 any 简化
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type UploadRequestOption = any

function PriceAttachments({ resultId, locked }: { resultId: number; locked: boolean }) {
  const { message } = App.useApp()
  const [files, setFiles] = useState<PriceAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })

  const load = useCallback(async () => {
    try {
      const res = await listPriceAttachments(resultId)
      setFiles(res.data.data || [])
    } catch { /* ignore */ }
  }, [resultId])

  useEffect(() => { load() }, [load])

  const customUpload = async (options: UploadRequestOption) => {
    const { file, onSuccess, onError } = options
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file as Blob)
    try {
      const res = await axios.post(uploadPriceAttachmentUrl(resultId), formData, {
        withCredentials: true,
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      onSuccess?.(res.data)
      message.success('上传成功')
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      onError?.(err as Error)
      message.error(e.response?.data?.error || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleDownload = async (f: PriceAttachment) => {
    try {
      const res = await downloadPriceAttachment(resultId, f.id)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = f.original_name
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('下载失败')
    }
  }

  const handleDelete = async (f: PriceAttachment) => {
    try {
      await deletePriceAttachment(resultId, f.id)
      message.success('已删除')
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      message.error(e.response?.data?.error || '删除失败')
    }
  }

  return (
    <>
      {locked ? (
        <Alert type="success" showIcon style={{ marginBottom: 12 }}
          message="该结果已确认，附件已锁定；如需增删请先撤回。" />
      ) : (
        <Upload
          customRequest={customUpload}
          showUploadList={false}
          multiple
          accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar"
          disabled={uploading}
        >
          <Button icon={<UploadOutlined />} loading={uploading}>
            上传单价附件 / 报价单（PDF / Word / Excel / 图片 / 压缩包）
          </Button>
        </Upload>
      )}

      <List
        size="small"
        style={{ marginTop: 12 }}
        locale={{ emptyText: '暂无上传文件' }}
        dataSource={files}
        renderItem={(f) => (
          <List.Item
            actions={[
              ...(isPreviewable(f.original_name) ? [
                <Button key="pv" type="link" size="small" icon={<EyeOutlined />}
                  onClick={() => setPreview({ open: true, url: pricePreviewUrl(resultId, f.id), name: f.original_name })}>预览</Button>,
              ] : []),
              <Button key="dl" type="link" size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(f)}>下载</Button>,
              ...(locked ? [] : [
                <Popconfirm key="del" title="删除该文件？" onConfirm={() => handleDelete(f)} okText="删除" cancelText="取消">
                  <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                </Popconfirm>,
              ]),
            ]}
          >
            <List.Item.Meta
              avatar={<PaperClipOutlined />}
              title={f.original_name}
              description={`${fmtSize(f.file_size)} · ${f.uploaded_by || ''} ${f.uploaded_at ? f.uploaded_at.replace('T', ' ') : ''}`}
            />
          </List.Item>
        )}
      />
      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />
    </>
  )
}

// ─── 中标通知书上传/预览（已确认采购结果）──────────────────────────────────────
function AwardNotice({ resultId, canUpload }: { resultId: number; canUpload: boolean }) {
  const { message } = App.useApp()
  const [files, setFiles] = useState<PriceAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })

  const load = useCallback(async () => {
    try {
      const res = await listAwardNotice(resultId)
      setFiles(res.data.data || [])
    } catch { /* ignore */ }
  }, [resultId])

  useEffect(() => { load() }, [load])

  const customUpload = async (options: UploadRequestOption) => {
    const { file, onSuccess, onError } = options
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file as Blob)
    try {
      const res = await axios.post(uploadAwardNoticeUrl(resultId), formData, {
        withCredentials: true,
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      onSuccess?.(res.data)
      message.success('上传成功')
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      onError?.(err as Error)
      message.error(e.response?.data?.error || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleDownload = async (f: PriceAttachment) => {
    try {
      const res = await downloadAwardNotice(resultId, f.id)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = f.original_name
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('下载失败')
    }
  }

  const handleDelete = async (f: PriceAttachment) => {
    try {
      await deleteAwardNotice(resultId, f.id)
      message.success('已删除')
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      message.error(e.response?.data?.error || '删除失败')
    }
  }

  return (
    <>
      {canUpload ? (
        <Upload
          customRequest={customUpload}
          showUploadList={false}
          multiple
          accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar"
          disabled={uploading}
        >
          <Button icon={<UploadOutlined />} loading={uploading} type="primary">
            上传中标通知书（PDF / Word / 图片 等）
          </Button>
        </Upload>
      ) : (
        <Alert type="info" showIcon message="中标通知书由代理机构上传，此处仅可查看。" />
      )}

      <List
        size="small"
        style={{ marginTop: 12 }}
        locale={{ emptyText: '尚未上传中标通知书' }}
        dataSource={files}
        renderItem={(f) => (
          <List.Item
            actions={[
              ...(isPreviewable(f.original_name) ? [
                <Button key="pv" type="link" size="small" icon={<EyeOutlined />}
                  onClick={() => setPreview({ open: true, url: awardNoticePreviewUrl(resultId, f.id), name: f.original_name })}>预览</Button>,
              ] : []),
              <Button key="dl" type="link" size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(f)}>下载</Button>,
              ...(canUpload ? [
                <Popconfirm key="del" title="删除该中标通知书？" onConfirm={() => handleDelete(f)} okText="删除" cancelText="取消">
                  <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                </Popconfirm>,
              ] : []),
            ]}
          >
            <List.Item.Meta
              avatar={<PaperClipOutlined />}
              title={
                isPreviewable(f.original_name)
                  ? <a onClick={() => setPreview({ open: true, url: awardNoticePreviewUrl(resultId, f.id), name: f.original_name })}>{f.original_name}</a>
                  : f.original_name
              }
              description={`${fmtSize(f.file_size)} · ${f.uploaded_by || ''} ${f.uploaded_at ? f.uploaded_at.replace('T', ' ') : ''}`}
            />
          </List.Item>
        )}
      />
      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />
    </>
  )
}
