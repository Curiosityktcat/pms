/**
 * 2.2 四川采购公告看板：抓取四川政府采购网的中标公告 / 合同公告。
 * 数据由后端 Playwright 抓取入库，本页读库展示，可手动刷新触发抓取。
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Card, Table, Tabs, Input, Button, Tag, Space, App, Typography, Tooltip,
  Drawer, Spin,
} from 'antd'
import {
  ReloadOutlined, SearchOutlined, LinkOutlined, FileTextOutlined, SyncOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getCcgpData, getCcgpDetail, refreshCcgp, getCcgpStatus,
  type CcgpNotice,
} from '../services/ccgpBoard'

const { Text, Paragraph } = Typography

export default function CcgpBoardPage() {
  const { message } = App.useApp()
  const [tab, setTab] = useState<'中标公告' | '合同公告'>('中标公告')
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<CcgpNotice[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [detail, setDetail] = useState<CcgpNotice | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getCcgpData({ type: tab, keyword: search, page, page_size: pageSize })
      setRows(res.data.items)
      setTotal(res.data.total)
      setUpdatedAt(res.data.updated_at)
    } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [tab, search, page, pageSize, message])

  useEffect(() => { load() }, [load])

  // 切 tab / 改搜索回到第 1 页
  useEffect(() => { setPage(1) }, [tab, search])

  const doSearch = () => setSearch(keyword.trim())

  const pollStatus = useCallback(() => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await getCcgpStatus()
        if (!res.data.running) {
          if (pollRef.current) clearInterval(pollRef.current)
          setRefreshing(false)
          message.success(`抓取完成：${res.data.last_msg || ''}`)
          load()
        }
      } catch { /* ignore */ }
    }, 3000)
  }, [load, message])

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const doRefresh = async () => {
    setRefreshing(true)
    try {
      const res = await refreshCcgp(3)
      if (res.data.status === 'started') {
        message.info('已开始抓取四川政府采购网，约需半分钟…')
        pollStatus()
      } else if (res.data.status === 'running') {
        message.info('抓取正在进行中，请稍候')
        pollStatus()
      } else if (res.data.status === 'cooldown') {
        setRefreshing(false)
        message.warning(`刚抓取过，请 ${res.data.wait_mins} 分钟后再试`)
      }
    } catch {
      setRefreshing(false)
      message.error('触发抓取失败')
    }
  }

  const openDetail = async (id: string) => {
    setDetailLoading(true)
    setDetail({ id } as CcgpNotice)
    try {
      const res = await getCcgpDetail(id)
      setDetail(res.data.data)
    } catch { message.error('加载详情失败'); setDetail(null) }
    finally { setDetailLoading(false) }
  }

  const columns: ColumnsType<CcgpNotice> = [
    {
      title: '公告标题', dataIndex: 'title', ellipsis: true,
      render: (v: string, r) => (
        <a onClick={() => openDetail(r.id)} title={v}>{v}</a>
      ),
    },
    { title: '采购人', dataIndex: 'purchaser', width: 180, ellipsis: true,
      render: v => v || <Text type="secondary">—</Text> },
    { title: '代理机构', dataIndex: 'agency', width: 170, ellipsis: true,
      render: v => v || <Text type="secondary">—</Text> },
    {
      title: tab === '合同公告' ? '供应商' : '中标人', dataIndex: 'win_company', width: 160, ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    { title: '金额', dataIndex: 'amount', width: 120,
      render: (v: string) => v ? <Text strong style={{ color: '#c41d7f' }}>{v}</Text> : <Text type="secondary">—</Text> },
    { title: '地区', dataIndex: 'region', width: 90,
      render: v => v || '—' },
    { title: '公告时间', dataIndex: 'notice_time', width: 150,
      render: v => v ? v.slice(0, 16) : '—' },
    {
      title: '操作', key: 'act', width: 120, fixed: 'right' as const,
      render: (_: unknown, r) => (
        <Space size={4}>
          <Button size="small" icon={<FileTextOutlined />} onClick={() => openDetail(r.id)}>详情</Button>
          <Tooltip title="打开原文">
            <Button size="small" type="text" icon={<LinkOutlined />}
              href={r.source_url} target="_blank" />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title={<span style={{ fontWeight: 700, fontSize: 16 }}>四川政府采购公告</span>}
      extra={
        <Space>
          {updatedAt && <Text type="secondary" style={{ fontSize: 12 }}>更新于 {updatedAt.replace('T', ' ').slice(0, 16)}</Text>}
          <Button type="primary" icon={refreshing ? <SyncOutlined spin /> : <ReloadOutlined />}
            loading={false} disabled={refreshing} onClick={doRefresh}>
            {refreshing ? '抓取中…' : '抓取更新'}
          </Button>
        </Space>
      }
    >
      <Tabs
        activeKey={tab}
        onChange={k => setTab(k as '中标公告' | '合同公告')}
        items={[{ key: '中标公告', label: '中标公告' }, { key: '合同公告', label: '合同公告' }]}
      />

      <Space style={{ marginBottom: 12 }}>
        <Input
          allowClear
          placeholder="搜索标题 / 采购人 / 代理 / 中标人 / 项目编号"
          style={{ width: 360 }}
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          onPressEnter={doSearch}
          prefix={<SearchOutlined />}
        />
        <Button onClick={doSearch}>搜索</Button>
      </Space>

      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        scroll={{ x: 1100 }}
        pagination={{
          current: page, pageSize, total,
          showSizeChanger: true, pageSizeOptions: [20, 50, 100],
          showTotal: t => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
      />

      <Drawer
        title="公告详情"
        width={760}
        open={!!detail}
        onClose={() => setDetail(null)}
        extra={detail?.source_url && (
          <Button icon={<LinkOutlined />} href={detail.source_url} target="_blank">原文</Button>
        )}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : detail ? (
          <div>
            <Typography.Title level={5} style={{ marginTop: 0 }}>{detail.title}</Typography.Title>
            <Space wrap style={{ marginBottom: 12 }}>
              <Tag color="blue">{detail.notice_type}</Tag>
              {detail.notice_time && <Tag>{detail.notice_time.slice(0, 16)}</Tag>}
              {detail.region && <Tag>{detail.region}</Tag>}
            </Space>
            <DescRow label="项目编号" v={detail.project_no} />
            <DescRow label="采购人" v={detail.purchaser} />
            <DescRow label="代理机构" v={detail.agency} />
            <DescRow label={detail.notice_type === '合同公告' ? '供应商' : '中标人'} v={detail.win_company} />
            <DescRow label="金额" v={detail.amount} />
            <Typography.Title level={5} style={{ marginTop: 16 }}>正文</Typography.Title>
            <Paragraph style={{ whiteSpace: 'pre-wrap', fontSize: 13, color: '#333', maxHeight: '52vh', overflow: 'auto', background: '#fafafa', padding: 12, borderRadius: 6 }}>
              {detail.content || <Text type="secondary">（无正文，请点右上角「原文」查看）</Text>}
            </Paragraph>
          </div>
        ) : null}
      </Drawer>
    </Card>
  )
}

function DescRow({ label, v }: { label: string; v?: string }) {
  if (!v) return null
  return (
    <div style={{ marginBottom: 6 }}>
      <Text type="secondary" style={{ display: 'inline-block', width: 76 }}>{label}</Text>
      <Text>{v}</Text>
    </div>
  )
}
