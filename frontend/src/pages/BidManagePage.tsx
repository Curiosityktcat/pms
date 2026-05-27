import { useEffect, useState } from 'react'
import { Table, Button, Tag, Space, Card, Typography, App } from 'antd'
import { getBidList, markBid } from '../services/bid'
import type { Project } from '../services/project'
import { useAuth } from '../hooks/useAuth'

const { Text } = Typography

const CAN_OPEN_TAG: Record<string, { color: string; label: string }> = {
  '可开标': { color: 'green', label: '可开标' },
  '流标': { color: 'red', label: '流标' },
}

export default function BidManagePage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const { user } = useAuth()
  const { message } = App.useApp()

  const canMark = user?.role === 'officer' || user?.role === 'agency'

  const load = async () => {
    setLoading(true)
    try {
      const res = await getBidList()
      setProjects(res.data.data)
    } catch {
      message.error('加载开标列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleMark = async (pid: number, value: '可开标' | '流标') => {
    try {
      await markBid(pid, value)
      message.success(`已标记为「${value}」`)
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '操作失败')
    }
  }

  const columns = [
    {
      title: '编号',
      dataIndex: 'number',
      width: 180,
      render: (val: string) => <Text strong>{val}</Text>,
    },
    { title: '项目名称', dataIndex: 'name' },
    { title: '采购方式', dataIndex: 'method', width: 130 },
    {
      title: '代理机构',
      dataIndex: 'agency_name',
      width: 160,
      render: (val: string) => val || <Text type="secondary">—</Text>,
    },
    {
      title: '开标时间',
      dataIndex: 'bid_time',
      width: 160,
      render: (val: string) => val || <Text type="secondary">—</Text>,
    },
    {
      title: '能否开标',
      dataIndex: 'can_open',
      width: 100,
      render: (val: string) => {
        const t = CAN_OPEN_TAG[val]
        return t ? <Tag color={t.color}>{t.label}</Tag> : <Tag>未判定</Tag>
      },
    },
    { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag color="blue">{v}</Tag> },
    ...(canMark
      ? [{
          title: '操作',
          width: 140,
          render: (_: unknown, row: Project) => (
            <Space size={4}>
              <Button size="small" type="primary" ghost onClick={() => handleMark(row.id, '可开标')}>可开标</Button>
              <Button size="small" danger ghost onClick={() => handleMark(row.id, '流标')}>流标</Button>
            </Space>
          ),
        }]
      : []),
  ]

  return (
    <Card>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50', marginBottom: 16 }}>开标管理</div>
      <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
        展示已立项项目的开标安排。代理机构 / 经办人可标记「能否开标」。
      </Text>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={projects}
        loading={loading}
        size="small"
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
        locale={{ emptyText: '暂无项目' }}
      />
    </Card>
  )
}
