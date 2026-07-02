/**
 * 投诉质疑数据库：全国政府采购「质疑/投诉受理」(财政部门·政府采购监督管理) 与
 * 「公共资源交易行政监督」渠道库。对应招标文件 2.8《询问、质疑和投诉》。
 * 数据来源：知乎《全国最全招投标网站》(p/697136714) + ccgp-拼音规律补录，并抓取首页快照校验。
 * 只读检索，支持关键字 + 地区/类型/级别筛选。
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Input, Button, Tag, Space, App, Typography, Drawer, Select, Descriptions,
} from 'antd'
import { SearchOutlined, LinkOutlined, AuditOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getSupervision, getSupervisionFilters, type SupervisionChannel,
} from '../services/supervision'

const { Text, Paragraph } = Typography

const orgColor: Record<string, string> = {
  政府采购网: 'geekblue',
  公共资源交易平台: 'cyan',
}

function statusTag(code: number | null) {
  if (code === 200) return <Tag color="green">在线</Tag>
  if (code == null || code === 0) return <Tag color="red">无法访问</Tag>
  if (code === 403 || code === 412 || code === 422 || code === 410)
    return <Tag color="orange">反爬拦截({code})</Tag>
  return <Tag color="volcano">{code}</Tag>
}

export default function SupervisionPage() {
  const { message } = App.useApp()
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [region, setRegion] = useState('')
  const [level, setLevel] = useState('')
  const [rows, setRows] = useState<SupervisionChannel[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [regions, setRegions] = useState<string[]>([])
  const [levels, setLevels] = useState<{ value: string; count: number }[]>([])
  const [counts, setCounts] = useState<{ total: number; alive: number }>({ total: 0, alive: 0 })
  const [detail, setDetail] = useState<SupervisionChannel | null>(null)

  const loadFilters = useCallback(async () => {
    try {
      const res = await getSupervisionFilters()
      setRegions(res.data.regions)
      setLevels(res.data.levels)
      setCounts({ total: res.data.total, alive: res.data.alive })
    } catch { /* ignore */ }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getSupervision({
        keyword: search, region, level, page, page_size: pageSize,
      })
      setRows(res.data.items)
      setTotal(res.data.total)
    } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [search, region, level, page, pageSize, message])

  useEffect(() => { loadFilters() }, [loadFilters])
  useEffect(() => { load() }, [load])
  useEffect(() => { setPage(1) }, [search, region, level])

  const columns: ColumnsType<SupervisionChannel> = [
    { title: '地区', dataIndex: 'region', width: 90,
      render: (v: string, r) => <span>{v}<br /><Text type="secondary" style={{ fontSize: 12 }}>{r.level}</Text></span> },
    { title: '政府采购网', dataIndex: 'name',
      render: (t: string, r) => <a onClick={() => setDetail(r)}>{t}</a> },
    { title: '渠道用途', dataIndex: 'channel', ellipsis: true,
      render: (v: string) => <Text type="secondary">{v}</Text> },
    { title: '链接状态', dataIndex: 'http_status', width: 120,
      render: (v: number | null) => statusTag(v) },
    { title: '访问', key: 'go', width: 70,
      render: (_, r) => <a href={r.url} target="_blank" rel="noreferrer"><LinkOutlined /> 打开</a> },
  ]

  return (
    <Card
      title={<Space><AuditOutlined />投诉质疑数据库</Space>}
      extra={<Text type="secondary">共 {counts.total} 个政府采购网 · 在线核验 {counts.alive} 个</Text>}
    >
      <Paragraph type="secondary" style={{ marginTop: -8 }}>
        各地<b>政府采购网</b> = 财政部门·政府采购监督管理入口，质疑/投诉受理、行政处罚、监管公告均在此发布
        （质疑/投诉书范本、受理联系方式见各站「下载专区/办事指南」）。数据源：知乎 p/697136714 +
        财政部 ccgp-拼音规律补全，并抓取首页快照校验链接有效性。
      </Paragraph>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          placeholder="搜索 地区 / 名称 / 网址 / 渠道用途"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={() => setSearch(keyword.trim())}
          style={{ width: 280 }}
          allowClear
          prefix={<SearchOutlined />}
        />
        <Button type="primary" onClick={() => setSearch(keyword.trim())}>搜索</Button>
        <Select
          placeholder="地区" allowClear showSearch style={{ width: 130 }}
          value={region || undefined} onChange={(v) => setRegion(v || '')}
          options={regions.map((r) => ({ value: r, label: r }))}
        />
        <Select
          placeholder="行政级别" allowClear style={{ width: 140 }}
          value={level || undefined} onChange={(v) => setLevel(v || '')}
          options={levels.map((l) => ({ value: l.value, label: `${l.value} (${l.count})` }))}
        />
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        size="small"
        pagination={{
          current: page, pageSize, total, showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
      />

      <Drawer
        open={!!detail}
        onClose={() => setDetail(null)}
        width={680}
        title={detail?.name || '渠道详情'}
      >
        {detail && (
          <>
            <Descriptions bordered size="small" column={1} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="地区">{detail.region_full || detail.region}</Descriptions.Item>
              <Descriptions.Item label="行政级别">{detail.level || '—'}</Descriptions.Item>
              <Descriptions.Item label="渠道类型">
                <Tag color={orgColor[detail.org_type] || 'default'}>{detail.org_type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="渠道用途">{detail.channel || '—'}</Descriptions.Item>
              <Descriptions.Item label="官网">
                <a href={detail.url} target="_blank" rel="noreferrer">{detail.url} <LinkOutlined /></a>
              </Descriptions.Item>
              <Descriptions.Item label="链接状态">{statusTag(detail.http_status)}</Descriptions.Item>
              <Descriptions.Item label="网页标题">{detail.page_title || '—'}</Descriptions.Item>
              <Descriptions.Item label="抓取时间">{detail.fetched_at || '—'}</Descriptions.Item>
              <Descriptions.Item label="本机快照">{detail.snapshot_file || '（无）'}</Descriptions.Item>
              <Descriptions.Item label="数据来源">{detail.source}</Descriptions.Item>
            </Descriptions>
            <Paragraph type="secondary">
              提示：质疑/投诉书范本、受理投诉联系方式通常在政府采购网「下载专区/办事指南」公布；
              行政处罚、监管公告在「监督管理 / 监管处罚」栏目。
            </Paragraph>
          </>
        )}
      </Drawer>
    </Card>
  )
}
