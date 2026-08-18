/**
 * 项目管理器：把各业务环节已经产生的数据汇成只读进度看板。
 * 这里不放任何编辑动作；经办人需要办事时跳回原项目详情，避免出现第二套数据入口。
 */
import { useCallback, useEffect, useState } from 'react'
import {
  App, Button, Card, Col, Empty, Input, Row, Segmented, Select, Space,
  Statistic, Steps, Table, Tabs, Tag, Tooltip, Typography,
} from 'antd'
import {
  DownloadOutlined, ReloadOutlined, SearchOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import PendingOwnerTag from '../components/PendingOwnerTag'
import {
  getMonitorMeta, getMonitorStats, getMonitorTimeline, listMonitorPlans,
  listMonitorProjects, monitorExportUrl,
  type MonitorFilters, type MonitorMeta, type MonitorPlan, type MonitorProject,
  type MonitorStats, type MonitorTimeline,
} from '../services/projectMonitor'

const { Text } = Typography

const money = (n: number | null) => {
  if (n == null || n === 0) return '招单价'
  return n >= 10000 ? `${(n / 10000).toFixed(2)} 万元` : `${n.toFixed(2)} 元`
}

const STAGE_COLOR: Record<string, string> = {
  establish: 'default', demand_confirm: 'orange', inquiry: 'orange',
  doc_confirm: 'blue', announce: 'geekblue', bid_open: 'cyan', review: 'cyan',
  round_failed: 'red', result: 'gold', contract: 'purple', archive: 'green',
}

function ProjectTimeline({ projectId }: { projectId: number }) {
  const [data, setData] = useState<MonitorTimeline | null>(null)
  const [round, setRound] = useState<number>()
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    getMonitorTimeline(projectId).then((res) => {
      setData(res.data.data)
      setRound(res.data.data.project.current_round || res.data.data.rounds.at(-1)?.round_number)
    }).catch(() => setFailed(true))
  }, [projectId])

  if (failed) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="时间线加载失败" />
  if (!data) return <div style={{ padding: 20, textAlign: 'center' }}>正在加载时间线…</div>
  if (!data.rounds.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无里程碑记录" />
  const current = data.rounds.find((item) => item.round_number === round) || data.rounds[0]
  return (
    <div style={{ padding: '8px 12px 2px' }}>
      {data.rounds.length > 1 && (
        <Segmented
          size="small" style={{ marginBottom: 16 }} value={current.round_number}
          onChange={(value) => setRound(Number(value))}
          options={data.rounds.map((item) => ({ label: `第 ${item.round_number} 次`, value: item.round_number }))}
        />
      )}
      <Steps
        size="small" responsive items={current.nodes.map((node) => ({
          title: node.label,
          status: node.done ? 'finish' : 'wait',
          description: node.done ? (
            <Tooltip title={node.by ? `操作人：${node.by}` : ''}>
              <Text type="secondary" style={{ fontSize: 12 }}>{node.at || '已完成'}</Text>
            </Tooltip>
          ) : <Text type="secondary" style={{ fontSize: 12 }}>未完成</Text>,
        }))}
      />
    </div>
  )
}

export default function ProjectMonitorPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [meta, setMeta] = useState<MonitorMeta | null>(null)
  const [stats, setStats] = useState<MonitorStats | null>(null)
  const [rows, setRows] = useState<MonitorProject[]>([])
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<MonitorFilters>({})
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [tab, setTab] = useState('projects')

  const [plans, setPlans] = useState<MonitorPlan[]>([])
  const [planPage, setPlanPage] = useState(1)
  const [planTotal, setPlanTotal] = useState(0)
  const [planKeyword, setPlanKeyword] = useState('')
  const [planSearch, setPlanSearch] = useState('')

  useEffect(() => {
    getMonitorMeta().then((res) => setMeta(res.data.data))
      .catch(() => message.error('加载项目管理器筛选项失败'))
  }, [message])

  const loadProjects = useCallback(() => {
    setLoading(true)
    Promise.all([
      listMonitorProjects({ ...filters, page, page_size: pageSize }),
      getMonitorStats(filters),
    ]).then(([list, summary]) => {
      setRows(list.data.data)
      setTotal(list.data.total)
      setStats(summary.data.data)
    }).catch(() => message.error('加载项目进度失败'))
      .finally(() => setLoading(false))
  }, [filters, page, pageSize, message])

  useEffect(() => { loadProjects() }, [loadProjects])

  const loadPlans = useCallback(() => {
    if (!meta?.show_plans || tab !== 'plans') return
    setLoading(true)
    listMonitorPlans({ year: filters.year, keyword: planSearch, page: planPage, page_size: pageSize })
      .then((res) => { setPlans(res.data.data); setPlanTotal(res.data.total) })
      .catch(() => message.error('加载科室年度计划失败'))
      .finally(() => setLoading(false))
  }, [meta?.show_plans, tab, filters.year, planSearch, planPage, pageSize, message])

  useEffect(() => { loadPlans() }, [loadPlans])

  const changeFilter = (key: keyof MonitorFilters, value?: string) => {
    setPage(1)
    setFilters((old) => ({ ...old, [key]: value || undefined }))
  }

  const projectColumns = [
    {
      title: '项目名称 / 编号', dataIndex: 'name', width: 280, fixed: 'left' as const,
      render: (value: string, row: MonitorProject) => (
        <div>
          <a onClick={() => navigate(`/project/${row.id}`)}>{value}</a>
          <div><Text code style={{ fontSize: 12 }}>{row.number || '无编号'}</Text></div>
        </div>
      ),
    },
    {
      title: '当前阶段', dataIndex: 'stage_label', width: 180,
      render: (v: string, row: MonitorProject) => (
        <Tag color={STAGE_COLOR[row.current_stage] || 'default'}>{v}</Tag>
      ),
    },
    {
      title: '当前处理人（停留）', dataIndex: 'pending', width: 300,
      render: (_: unknown, row: MonitorProject) => (
        // 待办说明有长有短（如「待完成代理机构服务质量考核」），必须允许换行，
        // 否则会溢出压到隔壁科室列上，两行字叠在一起看不清。
        <Space size={4} wrap>
          <PendingOwnerTag p={row.pending} compact doneText="无待处理" />
          {row.overdue && <Tag color="red">超期</Tag>}
        </Space>
      ),
    },
    { title: '归口科室', dataIndex: 'manage_dept', width: 120, render: (v: string) => v || '—' },
    { title: '需求科室', dataIndex: 'demand_dept', width: 120, render: (v: string) => v || '—' },
    { title: '经办人', dataIndex: 'officer', width: 90, render: (v: string) => v || '—' },
    { title: '采购方式', dataIndex: 'method', width: 150, render: (v: string) => v || '—' },
    { title: '预算', dataIndex: 'amount', width: 120, render: money },
    { title: '轮次', dataIndex: 'current_round', width: 70, render: (v: number) => `第 ${v} 次` },
    { title: '最近动作', dataIndex: 'last_action_at', width: 110, render: (v: string) => v || '—' },
    {
      title: '操作', key: 'action', width: 80, fixed: 'right' as const,
      render: (_: unknown, row: MonitorProject) => (
        <Button size="small" onClick={() => navigate(`/project/${row.id}`)}>详情</Button>
      ),
    },
  ]

  const planColumns = [
    { title: '计划项目', dataIndex: 'name', width: 280 },
    { title: '归口科室', dataIndex: 'dept', width: 120 },
    { title: '需求科室', dataIndex: 'demand_dept', width: 120, render: (v: string) => v || '—' },
    { title: '采购方式', dataIndex: 'method', width: 140, render: (v: string) => v || '—' },
    { title: '预算', dataIndex: 'budget', width: 120, render: (v: number) => (v ? money(v) : '—') },
    {
      title: '采购期限', dataIndex: 'deadline', width: 130,
      render: (v: string, row: MonitorPlan) => (
        <Tooltip title={!v && row.deadline_raw ? `原始值：${row.deadline_raw}` : ''}>
          <Text type={row.overdue || row.deadline_near ? 'danger' : undefined} strong={row.overdue || row.deadline_near}>
            {v || '—'}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '状态', dataIndex: 'plan_status', width: 110,
      render: (v: string, row: MonitorPlan) => (
        <Tag color={row.overdue ? 'red' : row.deadline_near ? 'orange' : row.project ? 'green' : 'default'}>{v}</Tag>
      ),
    },
    {
      title: '对应项目进度', dataIndex: 'project',
      render: (_: unknown, row: MonitorPlan) => row.project ? (
        <Space direction="vertical" size={2}>
          <a onClick={() => navigate(`/project/${row.project!.id}`)}>{row.project.number} · {row.project.name}</a>
          <Space size={4}>
            <Tag color={STAGE_COLOR[row.project.current_stage] || 'default'}>{row.project.stage_label}</Tag>
            <PendingOwnerTag p={row.project.pending} compact />
          </Space>
        </Space>
      ) : <Text type={row.overdue || row.deadline_near ? 'danger' : 'secondary'}>还没立项</Text>,
    },
  ]

  const projectView = (
    <>
      {stats && (
        <>
          <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
            <Col xs={12} md={6}><Card size="small"><Statistic title={filters.archived === '1' ? '项目总数（含归档）' : '在办项目'} value={stats.ongoing} suffix="个" /></Card></Col>
            <Col xs={12} md={6}><Card size="small"><Statistic title="本月新立项" value={stats.new_this_month} suffix="个" /></Card></Col>
            <Col xs={12} md={6}><Card size="small"><Statistic title={`超期项目（>${stats.overdue_days}天）`} value={stats.overdue} suffix="个" valueStyle={{ color: '#d93025' }} /></Card></Col>
            <Col xs={12} md={6}>
              <Card size="small" title="阶段积压" styles={{ body: { paddingTop: 8 } }}>
                <Space size={[4, 4]} wrap>{stats.by_stage.map((item) => <Tag key={item.stage} color={STAGE_COLOR[item.stage]}>{item.label} {item.count}</Tag>)}</Space>
              </Card>
            </Col>
          </Row>
          {meta?.show_officer_stats && stats.by_officer.length > 0 && (
            <Card size="small" title="经办人分布" style={{ marginBottom: 12 }}>
              <Space wrap>{stats.by_officer.map((item) => <Tag key={item.name}>{item.name} {item.count}</Tag>)}</Space>
            </Card>
          )}
        </>
      )}

      <Space wrap style={{ marginBottom: 12 }}>
        <Select allowClear placeholder="年度" style={{ width: 105 }} value={filters.year} onChange={(v) => changeFilter('year', v)} options={(meta?.years || []).map((v) => ({ label: `${v} 年`, value: v }))} />
        <Select allowClear showSearch placeholder="归口科室" style={{ width: 140 }} value={filters.manage_dept} onChange={(v) => changeFilter('manage_dept', v)} options={(meta?.manage_depts || []).map((v) => ({ label: v, value: v }))} />
        <Select allowClear showSearch placeholder="需求科室" style={{ width: 140 }} value={filters.demand_dept} onChange={(v) => changeFilter('demand_dept', v)} options={(meta?.demand_depts || []).map((v) => ({ label: v, value: v }))} />
        <Select allowClear showSearch placeholder="经办人" style={{ width: 110 }} value={filters.officer} onChange={(v) => changeFilter('officer', v)} options={(meta?.officers || []).map((v) => ({ label: v, value: v }))} />
        <Select allowClear placeholder="采购方式" style={{ width: 160 }} value={filters.method} onChange={(v) => changeFilter('method', v)} options={(meta?.methods || []).map((v) => ({ label: v, value: v }))} />
        <Select allowClear placeholder="当前阶段" style={{ width: 175 }} value={filters.stage} onChange={(v) => changeFilter('stage', v)} options={meta?.stages || []} />
        <Select allowClear placeholder="是否超期" style={{ width: 120 }} value={filters.overdue} onChange={(v) => changeFilter('overdue', v)} options={[{ label: '已超期', value: '1' }, { label: '未超期', value: '0' }]} />
        <Select placeholder="范围" style={{ width: 140 }} value={filters.archived || '0'} onChange={(v) => changeFilter('archived', v === '0' ? undefined : v)} options={[{ label: '只看在办', value: '0' }, { label: '含已归档', value: '1' }]} />
        <Input.Search prefix={<SearchOutlined />} allowClear placeholder="项目名称 / 编号" style={{ width: 220 }} value={keyword} onChange={(e) => setKeyword(e.target.value)} onSearch={(v) => changeFilter('keyword', v.trim())} />
        <Button icon={<DownloadOutlined />} href={monitorExportUrl(filters)}>导出 Excel</Button>
        <Button icon={<ReloadOutlined />} onClick={loadProjects}>刷新</Button>
      </Space>

      <Table
        rowKey="id" loading={loading} dataSource={rows} columns={projectColumns}
        scroll={{ x: 1720 }} size="middle"
        locale={{ emptyText: (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={
            filters.archived === '1' ? '当前筛选下没有项目'
              : '当前没有在办项目。历史项目已归档，把右上角「只看在办」改成「含已归档」即可查看。'
          } />
        ) }}
        expandable={{ expandedRowRender: (row) => <ProjectTimeline projectId={row.id} /> }}
        pagination={{ current: page, pageSize, total, showSizeChanger: true,
          showTotal: (n) => `共 ${n} 个${filters.archived === '1' ? '项目（含已归档）' : '在办项目'}`,
          onChange: (next, size) => { setPage(next); setPageSize(size) } }}
      />
    </>
  )

  const planView = (
    <>
      <Space wrap style={{ marginBottom: 12 }}>
        <Select allowClear placeholder="年度" style={{ width: 110 }} value={filters.year} onChange={(v) => { changeFilter('year', v); setPlanPage(1) }} options={(meta?.years || []).map((v) => ({ label: `${v} 年`, value: v }))} />
        <Input.Search allowClear placeholder="计划名称 / 编号" style={{ width: 260 }} value={planKeyword} onChange={(e) => setPlanKeyword(e.target.value)} onSearch={(v) => { setPlanSearch(v.trim()); setPlanPage(1) }} />
        <Button icon={<ReloadOutlined />} onClick={loadPlans}>刷新</Button>
        <Text type="secondary">未立项且期限临近或已过的条目会标红提示。</Text>
      </Space>
      <Table rowKey="id" loading={loading} dataSource={plans} columns={planColumns} scroll={{ x: 1200 }}
        pagination={{ current: planPage, pageSize, total: planTotal, showSizeChanger: false,
          showTotal: (n) => `共 ${n} 条计划`, onChange: setPlanPage }} />
    </>
  )

  return (
    <Card title="项目管理器" extra={<Text type="secondary">只读看板 · 数据来自各业务环节</Text>}>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'projects', label: '项目进度', children: projectView },
        ...(meta?.show_plans ? [{ key: 'plans', label: '我科室的年度计划', children: planView }] : []),
      ]} />
    </Card>
  )
}
