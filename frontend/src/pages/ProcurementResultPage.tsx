import { useState, useEffect, useCallback } from 'react'
import {
  Table,
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
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  listResults,
  createResult,
  updateResult,
  deleteResult,
  confirmResult,
  revokeResult,
  resultWordUrl,
  type ProcurementResult,
  type ResultPackage,
} from '../services/procurementResult'
import { getProjects, type Project } from '../services/project'

const { Title } = Typography

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
        const amtWan = p.amount >= 10000 ? `${(p.amount / 10000).toFixed(1)}万` : `${p.amount}元`
        return `包${i + 1}:成交 ¥${amtWan}`
      }
      return `包${i + 1}:废标`
    })
    .join(' / ')
}

export default function ProcurementResultPage() {
  const { message, modal } = App.useApp()
  const [results, setResults] = useState<ProcurementResult[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [tabStatus, setTabStatus] = useState<'草稿' | '已确认'>('草稿')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [packages, setPackages] = useState<ResultPackage[]>([emptyPackage()])
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

  // ─── 打开新建 ────────────────────────────────────────────────────────────────
  const openCreate = () => {
    setEditingId(null)
    setPackages([emptyPackage()])
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

  // ─── 选择项目后自动填充 ──────────────────────────────────────────────────────
  const handleProjectChange = (projectId: number) => {
    const proj = projectMap[projectId]
    if (!proj) return
    form.setFieldsValue({
      agency_name: proj.agency_name || '',
      bid_time: proj.bid_time || '',
    })
  }

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
      content: `确认后状态将变为"已确认"，是否继续？`,
      onOk: async () => {
        try {
          await confirmResult(record.id)
          message.success('已确认')
          loadResults()
        } catch {
          message.error('操作失败')
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
    } catch {
      message.error('操作失败')
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

  // ─── 表格列定义 ──────────────────────────────────────────────────────────────
  const columns: ColumnsType<ProcurementResult> = [
    {
      title: '项目名称',
      key: 'project_name',
      ellipsis: true,
      render: (_, r) => projectMap[r.project_id]?.name || `项目#${r.project_id}`,
    },
    {
      title: '项目编号',
      key: 'project_number',
      width: 140,
      render: (_, r) => projectMap[r.project_id]?.number || '—',
    },
    {
      title: '竞选次数',
      dataIndex: 'round_number',
      width: 80,
      render: (v: number) => (v && v > 1 ? `第${v}次` : '第1次'),
    },
    {
      title: '竞选时间',
      dataIndex: 'bid_time',
      width: 120,
    },
    {
      title: '代理机构',
      dataIndex: 'agency_name',
      width: 120,
      ellipsis: true,
    },
    {
      title: '采购方式',
      dataIndex: 'procurement_method',
      width: 100,
    },
    {
      title: '采购结果摘要',
      key: 'summary',
      ellipsis: true,
      render: (_, r) => packagesSummary(r.packages),
    },
    {
      title: '签章日期',
      dataIndex: 'confirm_date',
      width: 110,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (v: string) => (
        <Tag color={v === '已确认' ? 'green' : 'default'}>{v}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, r) => (
        <Space size={4} wrap>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(r)}
          >
            编辑
          </Button>
          {r.status === '草稿' ? (
            <Button
              size="small"
              type="primary"
              icon={<CheckCircleOutlined />}
              onClick={() => handleConfirm(r)}
            >
              确认
            </Button>
          ) : (
            <Button
              size="small"
              icon={<RollbackOutlined />}
              onClick={() => handleRevoke(r)}
            >
              撤回
            </Button>
          )}
          <Button
            size="small"
            icon={<FileWordOutlined />}
            type={r.status === '已确认' ? 'primary' : 'default'}
            ghost={r.status === '已确认'}
            onClick={() => handleDownloadWord(r)}
          >
            Word
          </Button>
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(r)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

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
          onChange={(k) => setTabStatus(k as '草稿' | '已确认')}
          items={[
            { key: '草稿', label: `草稿 (${results.filter((r) => r.status === '草稿').length})` },
            { key: '已确认', label: `已确认 (${results.filter((r) => r.status === '已确认').length})` },
          ]}
          style={{ marginBottom: 0 }}
        />
        <Table
          rowKey="id"
          dataSource={filtered}
          columns={columns}
          loading={loading}
          size="small"
          pagination={{ pageSize: 15, showSizeChanger: false }}
          scroll={{ x: 1200 }}
        />
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
                    options={projects.map((p) => ({
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
              <Button
                type="dashed"
                icon={<PlusOutlined />}
                onClick={addPackage}
                size="small"
              >
                添加采购包
              </Button>
            }
          >
            {packages.map((pkg, idx) => (
              <PackageCard
                key={idx}
                index={idx}
                pkg={pkg}
                onUpdate={(field, value) => updatePackage(idx, field, value)}
                onRemove={packages.length > 1 ? () => removePackage(idx) : undefined}
              />
            ))}
          </Card>
        </Form>
      </Drawer>
    </div>
  )
}

// ─── 单包子卡片 ────────────────────────────────────────────────────────────────
interface PackageCardProps {
  index: number
  pkg: ResultPackage
  onUpdate: (field: keyof ResultPackage, value: unknown) => void
  onRemove?: () => void
}

function PackageCard({ index, pkg, onUpdate, onRemove }: PackageCardProps) {
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
          <span style={{ fontWeight: 600 }}>采购包 {index + 1}</span>
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
