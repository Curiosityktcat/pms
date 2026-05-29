import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Table, Button, Space, Tag, Input, Tabs, Popconfirm, App, Typography,
} from 'antd'
import { InboxOutlined, RollbackOutlined } from '@ant-design/icons'
import {
  listArchive, archiveProject, revokeArchive, type ArchiveItem,
} from '../services/archive'

const { Title, Text } = Typography

export default function ArchivePage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<ArchiveItem[]>([])
  const [keyword, setKeyword] = useState('')
  const [tab, setTab] = useState<'todo' | 'done'>('todo')
  const [acting, setActing] = useState(0)

  const load = useCallback(() => {
    setLoading(true)
    listArchive()
      .then(res => setItems(res.data.data || []))
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }, [message])
  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    const kw = keyword.trim()
    return items
      .filter(it => (tab === 'done' ? it.archived : !it.archived))
      .filter(it =>
        !kw ||
        (it.name || '').includes(kw) ||
        (it.number || '').includes(kw) ||
        (it.officer || '').includes(kw),
      )
  }, [items, keyword, tab])

  const doArchive = async (id: number) => {
    setActing(id)
    try {
      await archiveProject(id)
      message.success('已归档')
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '归档失败')
    } finally {
      setActing(0)
    }
  }

  const doRevoke = async (id: number) => {
    setActing(id)
    try {
      await revokeArchive(id)
      message.success('已撤销归档')
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '撤销失败')
    } finally {
      setActing(0)
    }
  }

  const countTag = (n: number, label: string) =>
    n > 0 ? <Tag color="blue">{label} {n}</Tag> : <Tag>{label} 0</Tag>

  const columns = [
    {
      title: '项目编号',
      dataIndex: 'number',
      width: 170,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    { title: '项目名称', dataIndex: 'name', ellipsis: true },
    { title: '经办人', dataIndex: 'officer', width: 90 },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <Tag color={v === '已归档' ? 'green' : 'default'}>{v}</Tag> },
    {
      title: '归档要件',
      width: 260,
      render: (_: unknown, r: ArchiveItem) => (
        <Space size={4} wrap>
          {countTag(r.auth_letter_count, '授权函')}
          {countTag(r.result_count, '结果')}
          {countTag(r.contract_count, '合同')}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 130,
      render: (_: unknown, r: ArchiveItem) =>
        r.archived ? (
          <Popconfirm title="撤销归档？状态将回退为「合同签订」" onConfirm={() => doRevoke(r.id)}>
            <Button type="link" danger icon={<RollbackOutlined />} loading={acting === r.id}>
              撤销归档
            </Button>
          </Popconfirm>
        ) : (
          <Popconfirm title="确认归档该项目？" onConfirm={() => doArchive(r.id)}>
            <Button type="link" icon={<InboxOutlined />} loading={acting === r.id}>
              归档
            </Button>
          </Popconfirm>
        ),
    },
  ]

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <InboxOutlined /> 项目归档
          </Title>
          <Text type="secondary">
            汇总项目要件（授权函 / 采购结果 / 合同），由采购部助理确认归档。
          </Text>
        </div>

        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Tabs
            activeKey={tab}
            onChange={k => setTab(k as 'todo' | 'done')}
            items={[{ key: 'todo', label: '待归档' }, { key: 'done', label: '已归档' }]}
          />
          <Input.Search
            placeholder="搜索名称 / 编号 / 经办人"
            allowClear
            style={{ width: 280 }}
            onChange={e => setKeyword(e.target.value)}
          />
        </Space>

        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={filtered}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          size="middle"
        />
      </Space>
    </Card>
  )
}
