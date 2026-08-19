import { useState, useEffect, useCallback } from 'react'
import {
  Button, Drawer, Form, Input, Select, Radio, DatePicker, InputNumber,
  Card, Space, Tabs, Popconfirm, App, Checkbox,
  Row, Col, Divider, Typography,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, FileWordOutlined,
  CheckCircleOutlined, RollbackOutlined,
} from '@ant-design/icons'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import DemandDocPanel, { PreviewSizeToggle, type PreviewSize } from '../components/DemandDocPanel'

// 预览宽度记在本地，下次打开还是上次那一档
const PREVIEW_KEY = 'pms-internal-preview-size'
import dayjs from 'dayjs'
import {
  listInternalBidDemands, createInternalBidDemand, updateInternalBidDemand,
  deleteInternalBidDemand, finalizeInternalBidDemand, revokeInternalBidDemand,
  internalBidDemandWordUrl,
  type InternalBidDemand, type BidItem, type BidPackage, type ReviewFactor,
} from '../services/internalBidDemand'
import { useAuth } from '../hooks/useAuth'

const { TextArea } = Input

type TabKey = '初稿' | '定稿'

// 固定8条一般资格要求
const GENERAL_QUALS = [
  '（一）具有独立承担民事责任的能力；',
  '（二）具有良好的商业信誉；',
  '（三）具有健全的财务会计制度；',
  '（四）具有履行合同所必需的设备和专业技术能力；',
  '（五）有依法缴纳税收和社会保障资金的良好记录；',
  '（六）参加政府采购活动前三年内没有重大违法记录；',
  '（七）供应商单位负责人为同一人或者存在直接控股、管理关系的不同供应商，不得同时参加同一合同项下的采购活动；',
  '（八）不属于为本项目提供整体设计、规范编制或者项目管理、监理、检测等服务的供应商。',
]

const CONTRACT_TYPE_OPTIONS = [
  '买卖合同', '租赁合同', '建设工程合同', '技术合同',
  '委托合同', '物业管理合同', '其他合同',
]

const emptyItem = (): BidItem => ({
  pkg: '包1', no: '1-1', name: '', unit_price: '', qty: '', unit: '台', amount: '',
})

const emptyPackage = (): BidPackage => ({
  pkg_name: '合同包一', budget: '', limit_price: '',
  review_method: '综合评分法', price_method: '固定单价',
  allow_joint: '否', allow_subcontract: '否',
})

const defaultReviewFactors = (): ReviewFactor[] => [
  { factor: '价格分', score: '', is_objective: '是', standard: '' },
  { factor: '技术要求', score: '', is_objective: '', standard: '' },
  { factor: '服务要求', score: '', is_objective: '', standard: '' },
  { factor: '价格扣除（自行采购无需设置）', score: '', is_objective: '', standard: '' },
]

function makeDefault(): Partial<InternalBidDemand> {
  return {
    demand_dept: '',
    manage_dept: '医学装备部',
    year: `${new Date().getFullYear()}`,
    // DatePicker 需要 dayjs 对象（传字符串会导致渲染崩溃白屏）
    compile_date: dayjs() as unknown as string,
    category: '货物',
    overview: '',
    has_consultant: 0,
    consultant_note: '',
    proc_method: '院内竞选',
    pkg_split: '不分包采购',
    multi_year: 0,
    items_json: '[]',
    packages_json: '[]',
    tech_req: '',
    biz_req: '',
    special_qual: '',
    review_factors_json: '[]',
    contract_type: '',
    actual_settlement: 0,
    contract_period: '',
    contract_location: '',
    payment_terms: '',
    acceptance_standard: '',
    warranty: '',
    ip_ownership: '',
    cost_risk: '',
    breach_dispute: '',
    contract_other: '',
    perf_bond: 0,
    perf_bond_ratio: '',
    perf_bond_method: '',
    perf_bond_note: '',
    quality_bond: 1,
    accept_org: '自行验收',
    invite_supplier: 0,
    invite_expert: 0,
    invite_service: 0,
    invite_third: 0,
    accept_procedure: '',
    accept_time: '',
    accept_other: '',
    tech_accept: '',
    biz_accept: '',
    accept_std: '',
    accept_other2: '',
  }
}

export default function InternalBidDemandPage() {
  const { message, modal } = App.useApp()
  const { user } = useAuth()
  const isDeptRole = ['dept', 'dept_manage', 'dept_demand'].includes(user?.role || '')
  const canWriteDemand = !isDeptRole || !!user?.perms.includes('internal-bid-demand')

  const [demands, setDemands] = useState<InternalBidDemand[]>([])
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<TabKey>('初稿')

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false)
  // 右侧预览占屏比例：27% / 45% / 隐藏（用户指定的三档）
  const [previewSize, setPreviewSize] = useState<PreviewSize>(() => {
    const raw = localStorage.getItem(PREVIEW_KEY)
    if (raw === null) return 27
    const v = Number(raw)
    return (v === 45 || v === 0 ? v : 27) as PreviewSize
  })
  const changePreviewSize = (v: PreviewSize) => {
    setPreviewSize(v); localStorage.setItem(PREVIEW_KEY, String(v))
  }
  const [editingId, setEditingId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  // Items/packages/reviewFactors state
  const [items, setItems] = useState<BidItem[]>([emptyItem()])
  const [packages, setPackages] = useState<BidPackage[]>([emptyPackage()])
  const [reviewFactors, setReviewFactors] = useState<ReviewFactor[]>(defaultReviewFactors())

  // Watch values for conditional rendering
  const hasConsultant = Form.useWatch('has_consultant', form)
  const perfBond = Form.useWatch('perf_bond', form)
  const pkgSplit = Form.useWatch('pkg_split', form)

  // ── 加载列表 ─────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listInternalBidDemands()
      setDemands(res.data.data || [])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    load()
  }, [load])

  // ── 新建 ─────────────────────────────────────────────────────
  const openCreate = () => {
    setEditingId(null)
    setItems([emptyItem()])
    setPackages([emptyPackage()])
    setReviewFactors(defaultReviewFactors())
    form.resetFields()
    form.setFieldsValue({ ...makeDefault(), demand_dept: user?.dept_name || '' })
    setDrawerOpen(true)
  }

  // ── 编辑 ─────────────────────────────────────────────────────
  const openEdit = (record: InternalBidDemand) => {
    setEditingId(record.id)
    try {
      const its: BidItem[] = JSON.parse(record.items_json || '[]')
      setItems(its.length ? its : [emptyItem()])
    } catch {
      setItems([emptyItem()])
    }
    try {
      const pkgs: BidPackage[] = JSON.parse(record.packages_json || '[]')
      setPackages(pkgs.length ? pkgs : [emptyPackage()])
    } catch {
      setPackages([emptyPackage()])
    }
    try {
      const rfs: ReviewFactor[] = JSON.parse(record.review_factors_json || '[]')
      setReviewFactors(rfs.length ? rfs : defaultReviewFactors())
    } catch {
      setReviewFactors(defaultReviewFactors())
    }
    form.resetFields()
    form.setFieldsValue({
      ...record,
      compile_date: record.compile_date ? dayjs(record.compile_date) : undefined,
      contract_type: record.contract_type ? record.contract_type.split(',').filter(Boolean) : [],
    })
    setDrawerOpen(true)
  }

  // ── 构建 payload ─────────────────────────────────────────────
  const buildPayload = () => {
    const values = form.getFieldsValue()
    const contractTypes = Array.isArray(values.contract_type)
      ? values.contract_type.join(',')
      : (values.contract_type || '')

    return {
      ...values,
      compile_date: values.compile_date
        ? dayjs(values.compile_date).format('YYYY-MM-DD')
        : '',
      contract_type: contractTypes,
      items_json: JSON.stringify(items),
      packages_json: JSON.stringify(packages),
      review_factors_json: JSON.stringify(reviewFactors),
    }
  }

  // ── 保存草稿 ─────────────────────────────────────────────────
  const handleSaveDraft = async () => {
    setSaving(true)
    try {
      const payload = buildPayload()
      if (editingId) {
        await updateInternalBidDemand(editingId, payload)
        message.success('保存成功')
      } else {
        const res = await createInternalBidDemand(payload)
        setEditingId(res.data.data.id)
        message.success('新建成功')
      }
      load()
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  // ── 保存并定稿 ─────────────────────────────────────────────
  const handleFinalize = async () => {
    modal.confirm({
      title: '确认定稿',
      content: '定稿后将无法编辑，确定要定稿吗？',
      onOk: async () => {
        setSaving(true)
        try {
          // 先保存，再定稿
          const payload = buildPayload()
          let id = editingId
          if (id) {
            await updateInternalBidDemand(id, payload)
          } else {
            const res = await createInternalBidDemand(payload)
            id = res.data.data.id
            setEditingId(id)
          }
          await finalizeInternalBidDemand(id!)
          message.success('已定稿')
          setDrawerOpen(false)
          load()
        } catch {
          message.error('操作失败')
        } finally {
          setSaving(false)
        }
      },
    })
  }

  // ── 撤回 ─────────────────────────────────────────────────────
  const handleRevoke = async (id: number) => {
    try {
      await revokeInternalBidDemand(id)
      message.success('已撤回为初稿')
      load()
      setDrawerOpen(false)
    } catch {
      message.error('撤回失败')
    }
  }

  // ── 删除 ─────────────────────────────────────────────────────
  const handleDelete = async (id: number) => {
    try {
      await deleteInternalBidDemand(id)
      message.success('已删除')
      load()
    } catch {
      message.error('删除失败')
    }
  }

  // ── 自动计算标的金额 ─────────────────────────────────────────
  const updateItemAmount = (idx: number, field: keyof BidItem, val: string) => {
    const newItems = items.map((item, i) => {
      if (i !== idx) return item
      const updated = { ...item, [field]: val }
      if (field === 'unit_price' || field === 'qty') {
        const up = parseFloat(updated.unit_price) || 0
        const q = parseFloat(updated.qty) || 0
        updated.amount = up > 0 && q > 0 ? String((up * q).toFixed(2)) : ''
      }
      return updated
    })
    setItems(newItems)
  }

  // ── 同步包信息（根据 items 中的包号自动同步 packages） ────────
  const syncPackages = (newItems: BidItem[]) => {
    const pkgNos = [...new Set(newItems.map(i => i.pkg).filter(Boolean))]
    const existingByName = Object.fromEntries(packages.map(p => [p.pkg_name, p]))
    // Map pkg id like "包1" → "合同包一"
    const toPackageName = (pkg: string) => {
      const nums: Record<string, string> = {
        '包1': '合同包一', '包2': '合同包二', '包3': '合同包三',
        '包4': '合同包四', '包5': '合同包五',
      }
      return nums[pkg] || pkg
    }
    const newPkgs = pkgNos.map(p => {
      const pname = toPackageName(p)
      return existingByName[pname] || { ...emptyPackage(), pkg_name: pname }
    })
    setPackages(newPkgs.length ? newPkgs : [emptyPackage()])
  }

  const filteredDemands = demands.filter(d => d.status === activeTab)

  // ── 列定义 ──────────────────────────────────────────────────
  const demandToCard = (record: InternalBidDemand): RecordCardData => ({
    key: record.id,
    accent: record.status === '定稿' ? '#34a853' : '#1a73e8',
    title: record.project_name || '（未命名）',
    subtitle: record.demand_dept ? `需求科室 ${record.demand_dept}` : undefined,
    statusText: record.status,
    statusColor: record.status === '定稿' ? 'green' : 'default',
    fields: [
      { label: '归口管理科室', value: record.manage_dept },
      { label: '编制时间', value: record.compile_date },
    ],
    actions: (
      <>
        {canWriteDemand && <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} disabled={record.status === '定稿'}>编辑</Button>}
        {canWriteDemand && record.status === '定稿' && (
          <Button size="small" icon={<FileWordOutlined />} type="primary" ghost
            onClick={() => window.open(internalBidDemandWordUrl(record.id), '_blank')}>下载Word</Button>
        )}
        {record.status === '定稿' && (
          <Popconfirm title="确认撤回为初稿？" onConfirm={() => handleRevoke(record.id)}>
            <Button size="small" icon={<RollbackOutlined />}>撤回</Button>
          </Popconfirm>
        )}
        {canWriteDemand && record.status === '初稿' && (
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        )}
      </>
    ),
  })

  // ── 渲染 ─────────────────────────────────────────────────────
  return (
    <div style={{ padding: '0 0 24px' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 16,
      }}>
        <div style={{ fontSize: 18, fontWeight: 600 }}>院内竞选需求编制</div>
        {canWriteDemand && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建需求表
        </Button>}
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={k => setActiveTab(k as TabKey)}
        items={[
          { key: '初稿', label: `初稿 (${demands.filter(d => d.status === '初稿').length})` },
          { key: '定稿', label: `定稿 (${demands.filter(d => d.status === '定稿').length})` },
        ]}
      />

      <RecordCards dataSource={filteredDemands} loading={loading} emptyText="暂无需求表" toCard={demandToCard} />

      {/* ── 编辑抽屉 ────────────────────────────────────────── */}
      <Drawer
        title={editingId ? '编辑院内竞选需求表' : '新建院内竞选需求表'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        // 三栏工作台要横向铺开：左边填信息、右边看成稿，中间不跳页
        width="96vw"
        destroyOnClose
        extra={
          <Space size={8}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>文件预览</Typography.Text>
            <PreviewSizeToggle value={previewSize} onChange={changePreviewSize} />
          </Space>
        }
        footer={
          <div style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setDrawerOpen(false)}>取消</Button>
              <Button onClick={handleSaveDraft} loading={saving} type="default">
                保存草稿
              </Button>
              {(!editingId || demands.find(d => d.id === editingId)?.status === '初稿') && (
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  onClick={handleFinalize}
                  loading={saving}
                >
                  保存并定稿
                </Button>
              )}
              {editingId && demands.find(d => d.id === editingId)?.status === '定稿' && (
                <Popconfirm
                  title="确认撤回为初稿？"
                  onConfirm={() => handleRevoke(editingId)}
                >
                  <Button icon={<RollbackOutlined />}>撤回</Button>
                </Popconfirm>
              )}
            </Space>
          </div>
        }
      >
        {/* 三栏工作台：左边填信息，右边看成稿。预览宽度由顶部三个按钮控制。 */}
        <div style={{ display: 'flex', gap: 12, alignItems: 'stretch',
                      height: 'calc(100vh - 190px)' }}>
          <div style={{
            flex: `1 1 ${100 - previewSize}%`, minWidth: 0,
            overflowY: 'auto', paddingRight: 6,
          }}>
        <Form form={form} layout="vertical" size="middle">

          {/* ── 表头 ── */}
          <Card title="表头" size="small" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item label="项目名称" name="project_name" rules={[{ required: true, message: '请填写项目名称' }]}>
                  <Input placeholder="本院内竞选项目名称（此处为项目起点，无需关联已立项项目）" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="需求科室" name="demand_dept">
                  <Input placeholder="请输入需求科室" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="归口管理科室" name="manage_dept">
                  <Input placeholder="如：医学装备部" />
                </Form.Item>
              </Col>
            </Row>
          </Card>

          {/* ── 第一部分 ── */}
          <Card title="第一部分：项目基本情况" size="small" style={{ marginBottom: 16 }}>
            <Form.Item label="1.1 采购单位">
              <Input value="内江市第一人民医院" disabled />
            </Form.Item>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item label="1.2 所属年度" name="year">
                  <Input placeholder="如：2026" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="1.3 编制单位">
                  <Input value="内江市第一人民医院" disabled />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="1.4 编制时间" name="compile_date">
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="1.5 项目所属分类" name="category">
              <Radio.Group>
                <Radio value="货物">货物</Radio>
                <Radio value="服务">服务</Radio>
                <Radio value="工程">工程</Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item label="1.6 预算金额（元）" name="budget_amount">
              <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="请输入预算金额" />
            </Form.Item>
            <Form.Item label="1.7 项目概况" name="overview">
              <TextArea rows={4} placeholder="请填写项目概况" />
            </Form.Item>
            <Form.Item
              label="1.8 是否有为采购项目提供整体设计、规范编制或者项目管理、监理、检测等服务的供应商"
              name="has_consultant"
            >
              <Radio.Group>
                <Radio value={0}>否</Radio>
                <Radio value={1}>是</Radio>
              </Radio.Group>
            </Form.Item>
            {hasConsultant === 1 && (
              <Form.Item label="若是，请填写说明" name="consultant_note">
                <TextArea rows={3} placeholder="请填写供应商信息" />
              </Form.Item>
            )}
          </Card>

          {/* ── 第三部分 ── */}
          <Card title="第三部分：项目采购实施计划" size="small" style={{ marginBottom: 16 }}>
            <Form.Item label="3.1 采购方式" name="proc_method">
              <Radio.Group>
                <Radio value="院内竞选">院内竞选</Radio>
                <Radio value="院内单一来源">院内单一来源</Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item label="3.2 采购包划分" name="pkg_split">
              <Radio.Group
                onChange={e => {
                  if (e.target.value === '不分包采购') {
                    const newItems = items.map(it => ({ ...it, pkg: '包1' }))
                    setItems(newItems)
                    syncPackages(newItems)
                  }
                }}
              >
                <Radio value="不分包采购">不分包采购</Radio>
                <Radio value="分包采购">分包采购</Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item label="3.3 是否属于一签多年项目" name="multi_year">
              <Radio.Group>
                <Radio value={0}>否</Radio>
                <Radio value={1}>是</Radio>
              </Radio.Group>
            </Form.Item>
          </Card>

          {/* ── 第四部分：标的情况 ── */}
          <Card title="第四部分：标的情况表" size="small" style={{ marginBottom: 16 }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
                <thead>
                  <tr style={{ background: '#fafafa' }}>
                    {['包号', '编号', '标的名称', '单价(元)', '数量', '计量单位', '标的金额(元)', '操作'].map(h => (
                      <th key={h} style={{ border: '1px solid #d9d9d9', padding: '6px 8px', fontSize: 13 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, idx) => (
                    <tr key={idx}>
                      <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 70 }}>
                        <Input
                          size="small"
                          value={item.pkg}
                          onChange={e => {
                            const newItems = items.map((it, i) =>
                              i === idx ? { ...it, pkg: e.target.value } : it
                            )
                            setItems(newItems)
                            syncPackages(newItems)
                          }}
                        />
                      </td>
                      <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 70 }}>
                        <Input
                          size="small"
                          value={item.no}
                          onChange={e => updateItemAmount(idx, 'no', e.target.value)}
                        />
                      </td>
                      <td style={{ border: '1px solid #d9d9d9', padding: 4, minWidth: 150 }}>
                        <Input
                          size="small"
                          value={item.name}
                          onChange={e => updateItemAmount(idx, 'name', e.target.value)}
                        />
                      </td>
                      <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 90 }}>
                        <Input
                          size="small"
                          value={item.unit_price}
                          onChange={e => updateItemAmount(idx, 'unit_price', e.target.value)}
                        />
                      </td>
                      <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 70 }}>
                        <Input
                          size="small"
                          value={item.qty}
                          onChange={e => updateItemAmount(idx, 'qty', e.target.value)}
                        />
                      </td>
                      <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 70 }}>
                        <Input
                          size="small"
                          value={item.unit}
                          onChange={e => updateItemAmount(idx, 'unit', e.target.value)}
                        />
                      </td>
                      <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 100 }}>
                        <Input size="small" value={item.amount} disabled />
                      </td>
                      <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 60, textAlign: 'center' }}>
                        <Button
                          size="small"
                          danger
                          onClick={() => {
                            const newItems = items.filter((_, i) => i !== idx)
                            setItems(newItems.length ? newItems : [emptyItem()])
                            syncPackages(newItems.length ? newItems : [emptyItem()])
                          }}
                        >
                          删除
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Button
              icon={<PlusOutlined />}
              size="small"
              style={{ marginTop: 8 }}
              onClick={() => {
                const pkgNo = pkgSplit === '分包采购'
                  ? `包${[...new Set(items.map(i => i.pkg))].length + 1}`
                  : '包1'
                const newItem = { ...emptyItem(), pkg: pkgNo }
                const newItems = [...items, newItem]
                setItems(newItems)
                syncPackages(newItems)
              }}
            >
              添加标的行
            </Button>
          </Card>

          {/* ── 第四部分：分包情况 ── */}
          <Card title="第四部分：具体分包情况" size="small" style={{ marginBottom: 16 }}>
            {packages.map((pkg, idx) => (
              <Card
                key={idx}
                size="small"
                title={`${pkg.pkg_name}`}
                style={{ marginBottom: 12 }}
                extra={
                  <Button
                    size="small"
                    type="link"
                    onClick={() => {
                      const newPkg = { ...pkg }
                      const keys = ['合同包一', '合同包二', '合同包三', '合同包四', '合同包五']
                      newPkg.pkg_name = keys[packages.length] || `合同包${packages.length + 1}`
                      setPackages([...packages, newPkg])
                    }}
                    style={{ display: idx === packages.length - 1 ? 'inline-block' : 'none' }}
                  >
                    + 添加包
                  </Button>
                }
              >
                <Row gutter={12}>
                  <Col span={8}>
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>合同包名称</div>
                      <Input
                        size="small"
                        value={pkg.pkg_name}
                        onChange={e => {
                          const newPkgs = [...packages]
                          newPkgs[idx] = { ...pkg, pkg_name: e.target.value }
                          setPackages(newPkgs)
                        }}
                      />
                    </div>
                  </Col>
                  <Col span={8}>
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>4.2.1 预算金额（元）</div>
                      <Input
                        size="small"
                        value={pkg.budget}
                        onChange={e => {
                          const newPkgs = [...packages]
                          newPkgs[idx] = { ...pkg, budget: e.target.value }
                          setPackages(newPkgs)
                        }}
                      />
                    </div>
                  </Col>
                  <Col span={8}>
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>最高限价（元）</div>
                      <Input
                        size="small"
                        value={pkg.limit_price}
                        onChange={e => {
                          const newPkgs = [...packages]
                          newPkgs[idx] = { ...pkg, limit_price: e.target.value }
                          setPackages(newPkgs)
                        }}
                      />
                    </div>
                  </Col>
                </Row>
                <Row gutter={12}>
                  <Col span={8}>
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>4.2.2 评审方法</div>
                      <Select
                        size="small"
                        style={{ width: '100%' }}
                        value={pkg.review_method}
                        options={[
                          { value: '综合评分法', label: '综合评分法' },
                          { value: '最低评标价法', label: '最低评标价法' },
                          { value: '性价比法', label: '性价比法' },
                        ]}
                        onChange={v => {
                          const newPkgs = [...packages]
                          newPkgs[idx] = { ...pkg, review_method: v }
                          setPackages(newPkgs)
                        }}
                      />
                    </div>
                  </Col>
                  <Col span={8}>
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>4.2.3 定价方式</div>
                      <Radio.Group
                        size="small"
                        value={pkg.price_method}
                        onChange={e => {
                          const newPkgs = [...packages]
                          newPkgs[idx] = { ...pkg, price_method: e.target.value }
                          setPackages(newPkgs)
                        }}
                      >
                        <Radio value="固定单价">固定单价</Radio>
                        <Radio value="固定总价">固定总价</Radio>
                      </Radio.Group>
                    </div>
                  </Col>
                  <Col span={8}>
                    <Row gutter={8}>
                      <Col span={12}>
                        <div style={{ marginBottom: 8 }}>
                          <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>4.2.4 支持联合体投标</div>
                          <Radio.Group
                            size="small"
                            value={pkg.allow_joint}
                            onChange={e => {
                              const newPkgs = [...packages]
                              newPkgs[idx] = { ...pkg, allow_joint: e.target.value }
                              setPackages(newPkgs)
                            }}
                          >
                            <Radio value="是">是</Radio>
                            <Radio value="否">否</Radio>
                          </Radio.Group>
                        </div>
                      </Col>
                      <Col span={12}>
                        <div style={{ marginBottom: 8 }}>
                          <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>4.2.5 允许合同分包</div>
                          <Radio.Group
                            size="small"
                            value={pkg.allow_subcontract}
                            onChange={e => {
                              const newPkgs = [...packages]
                              newPkgs[idx] = { ...pkg, allow_subcontract: e.target.value }
                              setPackages(newPkgs)
                            }}
                          >
                            <Radio value="是">是</Radio>
                            <Radio value="否">否</Radio>
                          </Radio.Group>
                        </div>
                      </Col>
                    </Row>
                  </Col>
                </Row>
              </Card>
            ))}
          </Card>

          {/* ── 第五部分：技术要求 ── */}
          <Card title="第五部分：技术要求" size="small" style={{ marginBottom: 16 }}>
            <div style={{
              background: '#fffbe6',
              border: '1px solid #ffe58f',
              borderRadius: 4,
              padding: '8px 12px',
              fontSize: 12,
              color: '#666',
              marginBottom: 8,
            }}>
              须知：标注"★"的条款为本项目的实质性条款，投标人不满足的，将按照无效投标处理；标注"▲"的为重要条款。
            </div>
            <Form.Item name="tech_req">
              <TextArea
                rows={6}
                placeholder="请按包填写，如：&#10;一、包一：&#10;1. 技术要求...&#10;&#10;二、包二：&#10;1. 技术要求..."
              />
            </Form.Item>
          </Card>

          {/* ── 第六部分：商务要求 ── */}
          <Card title="第六部分：商务要求" size="small" style={{ marginBottom: 16 }}>
            <Form.Item name="biz_req">
              <TextArea
                rows={6}
                placeholder="请按包填写，如：&#10;一、包一：&#10;1. 商务要求...&#10;&#10;二、包二：&#10;1. 商务要求..."
              />
            </Form.Item>
          </Card>

          {/* ── 第七部分：资格要求 ── */}
          <Card title="第七部分：资格要求" size="small" style={{ marginBottom: 16 }}>
            <Divider style={{ fontSize: 13 }}>第一节：一般资格要求（固定条款，只读）</Divider>
            <div style={{
              background: '#f6f6f6',
              borderRadius: 4,
              padding: '8px 12px',
              fontSize: 13,
              marginBottom: 16,
            }}>
              {GENERAL_QUALS.map((q, i) => (
                <div key={i} style={{ marginBottom: 4 }}>{q}</div>
              ))}
            </div>
            <Divider style={{ fontSize: 13 }}>第二节：特殊资格要求</Divider>
            <Form.Item name="special_qual">
              <TextArea
                rows={4}
                placeholder="请输入特殊资格要求，如：&#10;1. 供应商须具备...&#10;2. 须提供..."
              />
            </Form.Item>
          </Card>

          {/* ── 第八部分：评审因素 ── */}
          <Card title="第八部分：评审因素（综合评分法/性价比法时填写）" size="small" style={{ marginBottom: 16 }}>
            <div style={{
              background: '#fffbe6',
              border: '1px solid #ffe58f',
              borderRadius: 4,
              padding: '6px 12px',
              fontSize: 12,
              color: '#666',
              marginBottom: 8,
            }}>
              须知：若为综合评分法的，按照下表填写，性价比法的自拟格式。
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#fafafa' }}>
                  {['评审因素', '评审分值', '是否客观项', '评审标准'].map(h => (
                    <th key={h} style={{ border: '1px solid #d9d9d9', padding: '6px 8px', fontSize: 13 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {reviewFactors.map((rf, idx) => (
                  <tr key={idx}>
                    <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 180 }}>
                      <Input
                        size="small"
                        value={rf.factor}
                        onChange={e => {
                          const newRf = [...reviewFactors]
                          newRf[idx] = { ...rf, factor: e.target.value }
                          setReviewFactors(newRf)
                        }}
                      />
                    </td>
                    <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 80 }}>
                      <Input
                        size="small"
                        value={rf.score}
                        onChange={e => {
                          const newRf = [...reviewFactors]
                          newRf[idx] = { ...rf, score: e.target.value }
                          setReviewFactors(newRf)
                        }}
                      />
                    </td>
                    <td style={{ border: '1px solid #d9d9d9', padding: 4, width: 100 }}>
                      <Select
                        size="small"
                        style={{ width: '100%' }}
                        value={rf.is_objective}
                        allowClear
                        placeholder="—"
                        options={[
                          { value: '是', label: '是' },
                          { value: '否', label: '否' },
                        ]}
                        onChange={v => {
                          const newRf = [...reviewFactors]
                          newRf[idx] = { ...rf, is_objective: v || '' }
                          setReviewFactors(newRf)
                        }}
                      />
                    </td>
                    <td style={{ border: '1px solid #d9d9d9', padding: 4 }}>
                      <Input
                        size="small"
                        value={rf.standard}
                        onChange={e => {
                          const newRf = [...reviewFactors]
                          newRf[idx] = { ...rf, standard: e.target.value }
                          setReviewFactors(newRf)
                        }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Button
              icon={<PlusOutlined />}
              size="small"
              style={{ marginTop: 8 }}
              onClick={() => setReviewFactors([...reviewFactors, { factor: '', score: '', is_objective: '', standard: '' }])}
            >
              添加评审因素
            </Button>
          </Card>

          {/* ── 第九部分：合同管理安排 ── */}
          <Card title="第九部分：合同管理安排" size="small" style={{ marginBottom: 16 }}>
            <Form.Item label="9.1 合同类型" name="contract_type">
              <Checkbox.Group options={CONTRACT_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item label="9.2 是否为据实结算" name="actual_settlement">
              <Radio.Group>
                <Radio value={0}>否</Radio>
                <Radio value={1}>是</Radio>
              </Radio.Group>
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="9.3 合同履行期限" name="contract_period">
                  <Input placeholder="如：合同签订之日起xx月" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="9.4 合同履约地点" name="contract_location">
                  <Input placeholder="如：内江市汉安大道西段1866号" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="9.5 合同支付约定" name="payment_terms">
              <TextArea rows={3} placeholder="请填写合同支付约定" />
            </Form.Item>
            <Form.Item label="9.6 验收交付标准和方法" name="acceptance_standard">
              <TextArea rows={3} placeholder="请填写验收交付标准和方法" />
            </Form.Item>
            <Form.Item label="9.7 质量保修范围和保修期" name="warranty">
              <TextArea rows={3} placeholder="请填写质量保修范围和保修期" />
            </Form.Item>
            <Form.Item label="9.8 知识产权归属" name="ip_ownership">
              <TextArea rows={2} placeholder="请填写知识产权归属" />
            </Form.Item>
            <Form.Item label="9.9 成本补偿和风险分担约定" name="cost_risk">
              <TextArea rows={2} placeholder="请填写成本补偿和风险分担约定" />
            </Form.Item>
            <Form.Item label="9.10 违约责任与解决争议的方法" name="breach_dispute">
              <TextArea rows={3} placeholder="请填写违约责任与解决争议的方法" />
            </Form.Item>
            <Form.Item label="9.11 合同其他条款" name="contract_other">
              <TextArea rows={3} placeholder="请填写合同其他条款" />
            </Form.Item>
            <Form.Item label="9.12 是否缴纳履约保证金" name="perf_bond">
              <Radio.Group>
                <Radio value={0}>否</Radio>
                <Radio value={1}>是</Radio>
              </Radio.Group>
            </Form.Item>
            {perfBond === 1 && (
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label="比例" name="perf_bond_ratio">
                    <Input placeholder="如：合同总价的10%" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="缴纳方式" name="perf_bond_method">
                    <Input placeholder="如：银行保函" />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Form.Item label="缴纳说明" name="perf_bond_note">
                    <TextArea rows={2} placeholder="请填写缴纳说明" />
                  </Form.Item>
                </Col>
              </Row>
            )}
            <Form.Item label="9.13 是否缴纳质量保证金" name="quality_bond">
              <Radio.Group>
                <Radio value={0}>否</Radio>
                <Radio value={1}>是</Radio>
              </Radio.Group>
            </Form.Item>
          </Card>

          {/* ── 第十部分：履约验收方案 ── */}
          <Card title="第十部分：履约验收方案" size="small" style={{ marginBottom: 16 }}>
            <Form.Item label="10.1 验收组织方式" name="accept_org">
              <Radio.Group>
                <Radio value="自行验收">自行验收</Radio>
                <Radio value="委托采购代理机构验收">委托采购代理机构验收</Radio>
              </Radio.Group>
            </Form.Item>
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item label="10.2 是否邀请其他供应商" name="invite_supplier">
                  <Radio.Group>
                    <Radio value={0}>否</Radio>
                    <Radio value={1}>是</Radio>
                  </Radio.Group>
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="10.3 是否邀请专家" name="invite_expert">
                  <Radio.Group>
                    <Radio value={0}>否</Radio>
                    <Radio value={1}>是</Radio>
                  </Radio.Group>
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="10.4 是否邀请服务对象" name="invite_service">
                  <Radio.Group>
                    <Radio value={0}>否</Radio>
                    <Radio value={1}>是</Radio>
                  </Radio.Group>
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item label="10.5 是否邀请第三方检测机构" name="invite_third">
                  <Radio.Group>
                    <Radio value={0}>否</Radio>
                    <Radio value={1}>是</Radio>
                  </Radio.Group>
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="10.6 履约验收程序" name="accept_procedure">
              <TextArea rows={3} placeholder="请填写履约验收程序" />
            </Form.Item>
            <Form.Item label="10.7 履约验收时间" name="accept_time">
              <Input placeholder="如：货物交付后30日内" />
            </Form.Item>
            <Form.Item label="10.8 验收组织的其他事项" name="accept_other">
              <TextArea rows={2} placeholder="请填写其他事项" />
            </Form.Item>
            <Form.Item label="10.9 技术履约验收内容" name="tech_accept">
              <TextArea rows={3} placeholder="请填写技术履约验收内容" />
            </Form.Item>
            <Form.Item label="10.10 商务履约验收内容" name="biz_accept">
              <TextArea rows={3} placeholder="请填写商务履约验收内容" />
            </Form.Item>
            <Form.Item label="10.11 履约验收标准" name="accept_std">
              <TextArea rows={3} placeholder="请填写履约验收标准" />
            </Form.Item>
            <Form.Item label="10.12 履约验收其他事项" name="accept_other2">
              <TextArea rows={2} placeholder="请填写其他事项" />
            </Form.Item>
          </Card>

        </Form>
          </div>

          {previewSize > 0 && (
            <div style={{ flex: `0 0 ${previewSize}%`, minWidth: 320, overflow: 'hidden' }}>
              <DemandDocPanel demandId={editingId ?? undefined} kind="internal-bid-demands" />
            </div>
          )}
        </div>
      </Drawer>
    </div>
  )
}
