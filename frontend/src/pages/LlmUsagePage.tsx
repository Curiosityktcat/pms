import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Tabs, Button, Space, Typography, Tag, App,
  InputNumber, Modal, Form, Alert,
} from 'antd'
import { BarChartOutlined, ReloadOutlined, WalletOutlined } from '@ant-design/icons'
import {
  getUsageSummary, getUsageRecent, getBilling, updatePrice, updateBalance,
  type UsageSummaryRow, type UsageRecord, type BillingInfo, type AgencyBalance,
} from '../services/llmUsage'

const { Text } = Typography

const FEATURE_CN: Record<string, string> = {
  'ai-review': 'AI 编制建议',
}

function fmtNum(n: number) {
  return (n || 0).toLocaleString('zh-CN')
}
function fmtYuan(n: number) {
  return `¥${(n || 0).toFixed(2)}`
}

export default function LlmUsagePage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState<UsageSummaryRow[]>([])
  const [recent, setRecent] = useState<UsageRecord[]>([])
  const [billing, setBilling] = useState<BillingInfo | null>(null)

  // 改价 / 改余额
  const [priceForm] = Form.useForm()
  const [savingPrice, setSavingPrice] = useState(false)
  const [editAgency, setEditAgency] = useState<AgencyBalance | null>(null)
  const [editVal, setEditVal] = useState<number>(0)
  const [savingBal, setSavingBal] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, r, b] = await Promise.all([getUsageSummary(), getUsageRecent(200), getBilling()])
      setSummary(s.data.data || [])
      setRecent(r.data.data || [])
      setBilling(b.data.data)
      priceForm.setFieldsValue({ price: b.data.data.price_per_million })
    } catch {
      message.error('加载用量数据失败')
    } finally {
      setLoading(false)
    }
  }, [message, priceForm])

  useEffect(() => { load() }, [load])

  const savePrice = async () => {
    const { price } = priceForm.getFieldsValue()
    setSavingPrice(true)
    try {
      await updatePrice(Number(price))
      message.success('计价已更新')
      load()
    } catch {
      message.error('保存失败')
    } finally { setSavingPrice(false) }
  }

  const saveBalance = async () => {
    if (!editAgency) return
    setSavingBal(true)
    try {
      await updateBalance(editAgency.agency_code, Number(editVal))
      message.success('余额已更新')
      setEditAgency(null)
      load()
    } catch {
      message.error('保存失败')
    } finally { setSavingBal(false) }
  }

  const totalTokens = summary.reduce((a, b) => a + (b.total_tokens || 0), 0)
  const totalCalls = summary.reduce((a, b) => a + (b.calls || 0), 0)
  const totalCost = summary.reduce((a, b) => a + (b.cost || 0), 0)

  const summaryCols = [
    {
      title: '账号', dataIndex: 'username', key: 'username',
      render: (v: string, r: UsageSummaryRow) =>
        <span>{r.display_name || v}{r.display_name && <Text type="secondary">（{v}）</Text>}</span>,
    },
    { title: '调用次数', dataIndex: 'calls', key: 'calls', sorter: (a: UsageSummaryRow, b: UsageSummaryRow) => a.calls - b.calls, render: fmtNum },
    { title: '输入 tokens', dataIndex: 'prompt_tokens', key: 'prompt_tokens', render: fmtNum },
    { title: '输出 tokens', dataIndex: 'completion_tokens', key: 'completion_tokens', render: fmtNum },
    {
      title: '合计 tokens', dataIndex: 'total_tokens', key: 'total_tokens',
      defaultSortOrder: 'descend' as const,
      sorter: (a: UsageSummaryRow, b: UsageSummaryRow) => a.total_tokens - b.total_tokens,
      render: (v: number) => <Text strong>{fmtNum(v)}</Text>,
    },
    { title: '费用', dataIndex: 'cost', key: 'cost', render: (v: number) => <Text type="danger">{fmtYuan(v)}</Text> },
    { title: '最近使用', dataIndex: 'last_used', key: 'last_used', render: (v: string) => (v || '').replace('T', ' ') },
  ]

  const recentCols = [
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170, render: (v: string) => (v || '').replace('T', ' ') },
    { title: '账号', dataIndex: 'username', key: 'username', render: (v: string, r: UsageRecord) => r.display_name || v },
    { title: '功能', dataIndex: 'feature', key: 'feature', render: (v: string) => <Tag>{FEATURE_CN[v] || v}</Tag> },
    { title: '模型', dataIndex: 'model', key: 'model', render: (v: string) => <Text type="secondary">{v}</Text> },
    { title: '输入', dataIndex: 'prompt_tokens', key: 'prompt_tokens', render: fmtNum },
    { title: '输出', dataIndex: 'completion_tokens', key: 'completion_tokens', render: fmtNum },
    { title: '合计', dataIndex: 'total_tokens', key: 'total_tokens', render: (v: number) => <Text strong>{fmtNum(v)}</Text> },
  ]

  const balanceCols = [
    { title: '代理机构', dataIndex: 'agency_name', key: 'agency_name' },
    { title: '编码', dataIndex: 'agency_code', key: 'agency_code', render: (v: string) => <Text type="secondary">{v}</Text> },
    {
      title: '余额', dataIndex: 'balance', key: 'balance',
      sorter: (a: AgencyBalance, b: AgencyBalance) => a.balance - b.balance,
      render: (v: number) => <Text strong type={v <= 0 ? 'danger' : v < 10 ? 'warning' : undefined}>{fmtYuan(v)}</Text>,
    },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', render: (v: string) => (v || '').replace('T', ' ') },
    {
      title: '操作', key: 'op',
      render: (_: unknown, r: AgencyBalance) => (
        <Button size="small" onClick={() => { setEditAgency(r); setEditVal(r.balance) }}>改余额 / 充值</Button>
      ),
    },
  ]

  return (
    <Card
      title={
        <Space>
          <BarChartOutlined style={{ color: '#1677ff' }} />
          <span style={{ fontWeight: 700, fontSize: 16 }}>Token 用量与计费</span>
        </Space>
      }
      extra={<Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>}
    >
      <Space style={{ marginBottom: 16 }} size="large" wrap>
        <Text type="secondary">总调用 <Text strong>{fmtNum(totalCalls)}</Text> 次</Text>
        <Text type="secondary">总消耗 <Text strong>{fmtNum(totalTokens)}</Text> tokens</Text>
        <Text type="secondary">总费用 <Text strong type="danger">{fmtYuan(totalCost)}</Text></Text>
        {billing && <Text type="secondary">计价 <Text strong>¥{billing.price_per_million}</Text> / 百万 token</Text>}
      </Space>

      <Tabs
        items={[
          {
            key: 'summary', label: '按账号汇总',
            children: (
              <Table rowKey="username" size="middle" loading={loading}
                columns={summaryCols} dataSource={summary} pagination={false} />
            ),
          },
          {
            key: 'balance',
            label: <span><WalletOutlined /> 代理机构余额 / 计费</span>,
            children: (
              <>
                <Card size="small" style={{ marginBottom: 16, background: '#f6f8fc' }}>
                  <Form form={priceForm} layout="inline">
                    <Form.Item label="计价（每百万 token）" name="price" rules={[{ required: true }]}>
                      <InputNumber min={0} step={1} addonBefore="¥" addonAfter="/ 百万" style={{ width: 200 }} />
                    </Form.Item>
                    <Form.Item>
                      <Button type="primary" loading={savingPrice} onClick={savePrice}>保存计价</Button>
                    </Form.Item>
                  </Form>
                </Card>
                <Alert
                  type="info" showIcon style={{ marginBottom: 12 }}
                  message={`代理机构使用 AI 时按 token 实时扣费（内部账号不计费）。新代理机构默认初始余额 ¥${billing?.init_balance ?? 100}。`}
                />
                <Table rowKey="agency_code" size="middle" loading={loading}
                  columns={balanceCols} dataSource={billing?.balances || []} pagination={false} />
              </>
            ),
          },
          {
            key: 'recent', label: '调用明细',
            children: (
              <Table rowKey="id" size="middle" loading={loading}
                columns={recentCols} dataSource={recent}
                pagination={{ pageSize: 20, showSizeChanger: false }} />
            ),
          },
        ]}
      />

      <Modal
        title={`设置余额 — ${editAgency?.agency_name || ''}`}
        open={!!editAgency}
        onCancel={() => setEditAgency(null)}
        onOk={saveBalance}
        confirmLoading={savingBal}
        okText="保存"
        destroyOnHidden
      >
        <Text type="secondary">当前余额：{fmtYuan(editAgency?.balance || 0)}</Text>
        <div style={{ marginTop: 12 }}>
          <InputNumber
            min={0} step={10} addonBefore="¥" style={{ width: '100%' }}
            value={editVal} onChange={(v) => setEditVal(Number(v) || 0)}
          />
        </div>
        <Text type="secondary" style={{ fontSize: 12 }}>直接填入设置后的余额（充值即填更大的数）。</Text>
      </Modal>
    </Card>
  )
}
