/**
 * 法规库：政府采购相关法律法规 / 部门规章 / 规范性文件 / 政策解读 / 地方法规。
 * 数据来源：易采通法规库(law.ycait.com) + 四川政府采购制度汇编（联网补全）。只读检索。
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Input, Button, Tag, Space, App, Typography, Drawer, Select, Spin, Descriptions,
} from 'antd'
import { SearchOutlined, LinkOutlined, BookOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getLaws, getLawLevels, getLawDetail, type Law } from '../services/law'

const { Text, Paragraph } = Typography

const timeColor: Record<string, string> = { 有效: 'green', 失效: 'orange', 废止: 'red' }

export default function LawLibraryPage() {
  const { message } = App.useApp()
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [level, setLevel] = useState<string>('')
  const [timeliness, setTimeliness] = useState<string>('')
  const [catalogOnly, setCatalogOnly] = useState(false)
  const [rows, setRows] = useState<Law[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [levels, setLevels] = useState<{ level: string; count: number }[]>([])
  const [counts, setCounts] = useState<{ total: number; catalog: number }>({ total: 0, catalog: 0 })
  const [detail, setDetail] = useState<Law | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const loadLevels = useCallback(async () => {
    try {
      const res = await getLawLevels()
      setLevels(res.data.levels)
      setCounts({ total: res.data.total, catalog: res.data.catalog_total })
    } catch { /* ignore */ }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getLaws({
        keyword: search, level, timeliness, catalog_only: catalogOnly,
        page, page_size: pageSize,
      })
      setRows(res.data.items)
      setTotal(res.data.total)
    } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [search, level, timeliness, catalogOnly, page, pageSize, message])

  useEffect(() => { loadLevels() }, [loadLevels])
  useEffect(() => { load() }, [load])
  useEffect(() => { setPage(1) }, [search, level, timeliness, catalogOnly])

  const openDetail = async (id: number) => {
    setDetailLoading(true)
    setDetail({} as Law)
    try {
      const res = await getLawDetail(id)
      setDetail(res.data.data)
    } catch { message.error('加载详情失败'); setDetail(null) } finally { setDetailLoading(false) }
  }

  const columns: ColumnsType<Law> = [
    {
      title: '序号', dataIndex: 'catalog_num', width: 64,
      render: (n: number | null) => n ? <Tag color="blue">{n}</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: '标题', dataIndex: 'title',
      render: (t: string, r) => (
        <a onClick={() => openDetail(r.id)}>{t}</a>
      ),
    },
    { title: '发文字号', dataIndex: 'law_number', width: 160,
      render: (v: string) => v || <Text type="secondary">—</Text> },
    { title: '法规库层次', dataIndex: 'level', width: 130,
      render: (v: string) => v ? <Tag>{v}</Tag> : '—' },
    { title: '颁布单位', dataIndex: 'issue_unit', width: 120, ellipsis: true },
    { title: '实施日期', dataIndex: 'implementation_date', width: 110 },
    { title: '时效性', dataIndex: 'timeliness', width: 80,
      render: (v: string) => v ? <Tag color={timeColor[v] || 'default'}>{v}</Tag> : '—' },
    { title: '适用地区', dataIndex: 'region', width: 90 },
  ]

  return (
    <Card
      title={<Space><BookOutlined />法规库</Space>}
      extra={<Text type="secondary">共 {counts.total} 部 · 汇编目录 {counts.catalog} 项</Text>}
    >
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          placeholder="搜索标题 / 文号 / 颁布单位 / 全文"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={() => setSearch(keyword.trim())}
          style={{ width: 280 }}
          allowClear
          prefix={<SearchOutlined />}
        />
        <Button type="primary" onClick={() => setSearch(keyword.trim())}>搜索</Button>
        <Select
          placeholder="法规库层次" allowClear style={{ width: 160 }}
          value={level || undefined} onChange={(v) => setLevel(v || '')}
          options={levels.map((l) => ({ value: l.level, label: `${l.level} (${l.count})` }))}
        />
        <Select
          placeholder="时效性" allowClear style={{ width: 110 }}
          value={timeliness || undefined} onChange={(v) => setTimeliness(v || '')}
          options={[{ value: '有效', label: '有效' }, { value: '失效', label: '失效' }, { value: '废止', label: '废止' }]}
        />
        <Button type={catalogOnly ? 'primary' : 'default'} onClick={() => setCatalogOnly((v) => !v)}>
          仅看汇编目录(145)
        </Button>
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
        width={860}
        title={detail?.title || '法规详情'}
      >
        {detailLoading || !detail?.title ? <Spin /> : (
          <>
            <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="法规库层次">{detail.level || '—'}</Descriptions.Item>
              <Descriptions.Item label="颁布单位">{detail.issue_unit || '—'}</Descriptions.Item>
              <Descriptions.Item label="颁布日期">{detail.issue_date || '—'}</Descriptions.Item>
              <Descriptions.Item label="实施日期">{detail.implementation_date || '—'}</Descriptions.Item>
              <Descriptions.Item label="时效性">
                {detail.timeliness ? <Tag color={timeColor[detail.timeliness] || 'default'}>{detail.timeliness}</Tag> : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="适用地区">{detail.region || '—'}</Descriptions.Item>
              <Descriptions.Item label="发文字号">{detail.law_number || '—'}</Descriptions.Item>
              <Descriptions.Item label="条法类别">{detail.category || '—'}</Descriptions.Item>
            </Descriptions>
            {detail.source_url && (
              <Paragraph>
                <a href={detail.source_url} target="_blank" rel="noreferrer">
                  <LinkOutlined /> 查看原文
                </a>
              </Paragraph>
            )}
            <Paragraph style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9 }}>
              {detail.full_text || '（暂无正文）'}
            </Paragraph>
          </>
        )}
      </Drawer>
    </Card>
  )
}
