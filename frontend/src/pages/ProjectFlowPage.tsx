import { useEffect, useState } from 'react'
import { Table, Button, Tag, Space, Popconfirm, Tabs, Input, Select, App, Typography, Card } from 'antd'
import { PlusOutlined, SearchOutlined, RollbackOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { getProjects, deleteProject, restoreProject } from '../services/project'
import type { Project } from '../services/project'
import { useAuth } from '../hooks/useAuth'

const { Text } = Typography

const STATUS_DONE = '已归档'
const METHODS = ['院内议价', '院内询价', '院内竞选', '院内单一来源采购']

export default function ProjectFlowPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [deleted, setDeleted] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'ongoing' | 'done' | 'deleted'>('ongoing')
  const [search, setSearch] = useState('')
  const [filterYear, setFilterYear] = useState<string | undefined>()
  const [filterMethod, setFilterMethod] = useState<string | undefined>()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { message } = App.useApp()

  const load = async () => {
    setLoading(true)
    try {
      const [res, resD] = await Promise.all([
        getProjects(false),
        getProjects(true),
      ])
      setProjects(res.data.data)
      setDeleted(resD.data.data)
    } catch {
      message.error('加载项目列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (id: number) => {
    try {
      await deleteProject(id)
      message.success('已删除，可在「已删除」标签中恢复')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '删除失败')
    }
  }

  const handleRestore = async (id: number) => {
    try {
      await restoreProject(id)
      message.success('项目已恢复')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '恢复失败')
    }
  }

  // 收集所有已有年度用于下拉
  const yearOptions = Array.from(
    new Set(projects.map(p => p.year).filter(Boolean))
  ).sort().reverse()

  // 过滤逻辑
  const applyFilter = (list: Project[]) => {
    const q = search.trim().toLowerCase()
    return list.filter(p => {
      const matchSearch = !q ||
        p.name.toLowerCase().includes(q) ||
        (p.number || '').toLowerCase().includes(q)
      const matchYear = !filterYear || p.year === filterYear
      const matchMethod = !filterMethod || p.method === filterMethod
      return matchSearch && matchYear && matchMethod
    })
  }

  const ongoing = projects.filter(p => p.status !== STATUS_DONE)
  const done = projects.filter(p => p.status === STATUS_DONE)

  const filteredOngoing = applyFilter(ongoing)
  const filteredDone = applyFilter(done)
  const filteredDeleted = applyFilter(deleted)

  const canEdit = user?.role === 'officer'
  const canCreate = user?.role === 'officer'

  const baseColumns = [
    {
      title: '编号',
      dataIndex: 'number',
      width: 190,
      render: (val: string, row: Project) =>
        row.is_draft ? (
          <Tag color="orange">草稿</Tag>
        ) : (
          <a onClick={() => navigate(`/project/${row.id}`)}>{val}</a>
        ),
    },
    {
      title: '项目名称',
      dataIndex: 'name',
      render: (val: string, row: Project) => (
        <a style={{ color: '#333' }} onClick={() => navigate(`/project/${row.id}`)}>{val}</a>
      ),
    },
    {
      title: '年度',
      dataIndex: 'year',
      width: 80,
      render: (val: string) => val || <Text type="secondary">—</Text>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 70,
      render: (val: string) => val || <Text type="secondary">—</Text>,
    },
    {
      title: '预算金额',
      dataIndex: 'amount',
      width: 110,
      render: (val: number | null) =>
        val && val > 0 ? `${val.toFixed(0)} 元` : <Text type="secondary">招单价</Text>,
    },
    {
      title: '采购方式',
      dataIndex: 'method',
      width: 130,
    },
    {
      title: '代理机构',
      dataIndex: 'agency_name',
      width: 160,
      render: (val: string) => val || <Text type="secondary">—</Text>,
    },
    { title: '经办人', dataIndex: 'officer', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (val: string) => (
        <Tag color={val === STATUS_DONE ? 'default' : 'blue'}>{val}</Tag>
      ),
    },
    {
      title: '开标时间',
      dataIndex: 'bid_time',
      width: 160,
      render: (val: string) => val || <Text type="secondary">—</Text>,
    },
  ]

  const activeColumns = [
    ...baseColumns,
    {
      title: '操作',
      width: 100,
      render: (_: unknown, row: Project) =>
        canEdit ? (
          <Space size={4}>
            <Button size="small" type="link" onClick={() => navigate(`/project/${row.id}`)}>编辑</Button>
            <Popconfirm
              title="删除后可在「已删除」中恢复"
              onConfirm={() => handleDelete(row.id)}
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
            >
              <Button size="small" type="link" danger>删除</Button>
            </Popconfirm>
          </Space>
        ) : (
          <Button size="small" type="link" onClick={() => navigate(`/project/${row.id}`)}>查看</Button>
        ),
    },
  ]

  const deletedColumns = [
    ...baseColumns,
    {
      title: '删除时间',
      dataIndex: 'deleted_at',
      width: 160,
      render: (val: string) => val ? val.replace('T', ' ') : '—',
    },
    {
      title: '操作',
      width: 80,
      render: (_: unknown, row: Project) =>
        canEdit ? (
          <Popconfirm
            title="确定恢复该项目？"
            onConfirm={() => handleRestore(row.id)}
            okText="恢复"
            cancelText="取消"
          >
            <Button size="small" type="link" icon={<RollbackOutlined />}>恢复</Button>
          </Popconfirm>
        ) : null,
    },
  ]

  const currentData = tab === 'ongoing' ? filteredOngoing
    : tab === 'done' ? filteredDone
    : filteredDeleted
  const currentColumns = tab === 'deleted' ? deletedColumns : activeColumns

  return (
    <Card>
      {/* 顶部工具栏 */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12, gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50' }}>项目流程</span>
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索项目名称或编号"
          allowClear
          style={{ width: 220 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select
          placeholder="采购年度"
          allowClear
          style={{ width: 110 }}
          value={filterYear}
          onChange={setFilterYear}
          options={yearOptions.map(y => ({ value: y, label: y }))}
        />
        <Select
          placeholder="采购方式"
          allowClear
          style={{ width: 160 }}
          value={filterMethod}
          onChange={setFilterMethod}
          options={METHODS.map(m => ({ value: m, label: m }))}
        />
        {canCreate && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            style={{ marginLeft: 'auto' }}
            onClick={() => navigate('/new')}
          >
            项目立项
          </Button>
        )}
      </div>

      {/* 标签页 */}
      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as 'ongoing' | 'done' | 'deleted')}
        items={[
          { key: 'ongoing', label: `进行中（${ongoing.length}）` },
          { key: 'done', label: `已归档（${done.length}）` },
          {
            key: 'deleted',
            label: (
              <span style={{ color: deleted.length > 0 ? '#ff4d4f' : undefined }}>
                已删除{deleted.length > 0 ? `（${deleted.length}）` : ''}
              </span>
            ),
          },
        ]}
      />

      <Table
        rowKey="id"
        columns={currentColumns}
        dataSource={currentData}
        loading={loading}
        size="small"
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
        locale={{ emptyText: tab === 'deleted' ? '没有已删除的项目' : '暂无项目' }}
      />
    </Card>
  )
}
