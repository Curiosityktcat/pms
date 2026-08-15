/**
 * 科室门户 —— 归口科室自助查看本科室的采购项目。
 *
 * 只读。两件事：①这个项目走到哪一步了、卡在谁手上；②相关资料在哪、能不能取走。
 * 数据全部走 /api/dept/*，那套接口自己按科室收口；科室角色被后端闸门限制在这个
 * 命名空间内，所以这里不需要（也不能）复用采购部的接口。
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Tag, Typography, Space, Select, Input, Row, Col, Statistic,
  Drawer, Timeline, List, Button, Empty, Alert, Tabs, Switch, App, Spin,
} from 'antd'
import {
  ReloadOutlined, FileTextOutlined, DownloadOutlined, EyeOutlined,
  ClockCircleOutlined, CheckCircleOutlined, ProfileOutlined,
} from '@ant-design/icons'
import {
  getDeptMe, getDeptOverview, listDeptProjects, getDeptProject,
  getDeptProgress, getDeptTree, listDeptContracts, listDeptPlans,
  type DeptMe, type DeptOverview, type DeptProject, type DeptProjectDetail,
  type DeptContract, type DeptPlan,
} from '../services/deptPortal'

const { Text, Title, Paragraph } = Typography

const money = (n: number | null) =>
  !n ? '—' : n >= 10000 ? `${(n / 10000).toFixed(2)} 万元` : `${n.toFixed(2)} 元`

// 阶段配色：在办的用蓝/橙提示需要关注，终态用绿/灰
const STAGE_COLOR: Record<string, string> = {
  demand_confirm: 'orange',
  inquiry: 'orange',
  doc_confirm: 'blue',
  announce: 'blue',
  bid_open: 'cyan',
  review: 'cyan',
  result: 'gold',
  contract: 'gold',
  round_failed: 'red',
  done: 'green',
  archived: 'default',
}

interface ProgressNode { key: string; label: string; done: boolean; at: string; by: string }
interface ProgressRound { round_number: number; status: string; nodes: ProgressNode[] }
interface ProgressData {
  project: {
    number: string
    name: string
    current_round: number
    current_stage: string
    pending?: {
      label: string
      owner_name: string
      role_label: string
      waiting_days: number
      since: string
    } | null
  }
  rounds: ProgressRound[]
}
interface TreeFolder { folder: string; items: { name: string; url: string; preview_url: string }[] }

export default function DeptPortalPage() {
  const { message } = App.useApp()
  const [me, setMe] = useState<DeptMe | null>(null)
  const [deptCode, setDeptCode] = useState<string | undefined>()   // 采购部角色切换用
  const [ov, setOv] = useState<DeptOverview | null>(null)
  const [rows, setRows] = useState<DeptProject[]>([])
  const [contracts, setContracts] = useState<DeptContract[]>([])
  const [plans, setPlans] = useState<DeptPlan[]>([])
  const [loading, setLoading] = useState(false)

  const [year, setYear] = useState<string>()
  const [stage, setStage] = useState<string>()
  const [keyword, setKeyword] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  // 抽屉：单个项目的进度与资料
  const [openId, setOpenId] = useState<number | null>(null)
  const [detail, setDetail] = useState<DeptProjectDetail | null>(null)
  const [progress, setProgress] = useState<ProgressData | null>(null)
  const [tree, setTree] = useState<TreeFolder[]>([])
  const [drawerLoading, setDrawerLoading] = useState(false)

  useEffect(() => {
    getDeptMe().then((r) => {
      setMe(r.data.data)
      if (r.data.data.can_switch && r.data.data.depts?.length) {
        setDeptCode(r.data.data.depts[0].code)
      }
    }).catch(() => message.error('取科室信息失败'))
  }, [message])

  const canSwitch = !!me?.can_switch
  // 科室账号自己不传 dept，后端按会话锁定；采购部角色才需要显式指定
  const scope = canSwitch ? deptCode : undefined
  const ready = !canSwitch || !!deptCode

  const load = useCallback(() => {
    if (!ready) return
    setLoading(true)
    Promise.all([
      getDeptOverview(scope),
      listDeptProjects({
        dept: scope, year, stage, keyword: keyword.trim() || undefined,
        archived: showArchived ? '1' : '0',
      }),
      listDeptContracts(scope),
      listDeptPlans({ dept: scope }),
    ]).then(([o, p, c, pl]) => {
      setOv(o.data.data)
      setRows(p.data.data)
      setContracts(c.data.data)
      setPlans(pl.data.data)
    }).catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }, [ready, scope, year, stage, keyword, showArchived, message])

  useEffect(() => { load() }, [load])

  const openProject = (id: number) => {
    setOpenId(id)
    setDrawerLoading(true)
    setDetail(null); setProgress(null); setTree([])
    Promise.all([
      getDeptProject(id, scope),
      getDeptProgress(id, scope),
      getDeptTree(id, scope),
    ]).then(([d, pr, t]) => {
      setDetail(d.data.data)
      setProgress(pr.data.data as ProgressData)
      setTree((t.data.data as TreeFolder[]) || [])
    }).catch(() => message.error('取项目详情失败'))
      .finally(() => setDrawerLoading(false))
  }

  const columns = [
    {
      title: '项目编号', dataIndex: 'number', width: 190,
      render: (v: string) => <Text code>{v || '—'}</Text>,
    },
    {
      title: '项目名称', dataIndex: 'name',
      render: (v: string, r: DeptProject) => (
        <a onClick={() => openProject(r.id)}>{v}</a>
      ),
    },
    { title: '采购方式', dataIndex: 'method', width: 110 },
    {
      title: '预算金额', dataIndex: 'amount', width: 120,
      render: (v: number | null) => money(v),
    },
    {
      title: '当前进度', dataIndex: 'stage_cn', width: 170,
      render: (v: string, r: DeptProject) => (
        <Tag color={STAGE_COLOR[r.current_stage] || 'default'}>{v}</Tag>
      ),
    },
    { title: '开标时间', dataIndex: 'bid_time', width: 150, render: (v: string) => v || '—' },
  ]

  const pending = progress?.project?.pending

  return (
    <div style={{ padding: 16 }}>
      <Card
        size="small"
        title={
          <Space>
            <ProfileOutlined />
            <span>科室门户 · {ov?.dept || me?.dept?.name || '未绑定科室'}</span>
          </Space>
        }
        extra={
          <Space>
            {canSwitch && (
              <Select
                style={{ width: 180 }} value={deptCode} onChange={setDeptCode}
                placeholder="选择科室" options={(me?.depts || []).map((d) => ({
                  value: d.code, label: d.name,
                }))}
              />
            )}
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
          </Space>
        }
      >
        {canSwitch && (
          <Alert
            type="info" showIcon style={{ marginBottom: 12 }}
            message="你正以采购部身份借用科室视角查看——这就是该科室账号登录后看到的内容。"
          />
        )}
        {!ready ? <Empty description="请选择科室" /> : (
          <>
            <Row gutter={16} style={{ marginBottom: 12 }}>
              <Col span={6}><Statistic title="本科室项目" value={ov?.total ?? 0} /></Col>
              <Col span={6}><Statistic title="在办" value={ov?.ongoing ?? 0}
                valueStyle={{ color: '#1677ff' }} /></Col>
              <Col span={6}><Statistic title="已归档" value={ov?.archived ?? 0} /></Col>
              <Col span={6}><Statistic title="合同" value={contracts.length} /></Col>
            </Row>

            <Tabs
              items={[
                {
                  key: 'projects',
                  label: `项目进度（${rows.length}）`,
                  children: (
                    <>
                      <Space wrap style={{ marginBottom: 12 }}>
                        <Select
                          allowClear placeholder="年度" style={{ width: 110 }}
                          value={year} onChange={setYear}
                          options={(ov?.years || []).map((y) => ({
                            value: y.year, label: `${y.year}（${y.count}）`,
                          }))}
                        />
                        <Select
                          allowClear placeholder="当前进度" style={{ width: 200 }}
                          value={stage} onChange={setStage}
                          options={(ov?.stages || []).map((s) => ({
                            value: s.stage, label: `${s.stage_cn}（${s.count}）`,
                          }))}
                        />
                        <Input.Search
                          allowClear placeholder="项目名称或编号" style={{ width: 240 }}
                          onSearch={setKeyword}
                        />
                        <Space size={4}>
                          <Switch checked={showArchived} onChange={setShowArchived} size="small" />
                          <Text type="secondary">含已归档</Text>
                        </Space>
                      </Space>
                      <Table
                        rowKey="id" size="small" loading={loading}
                        dataSource={rows} columns={columns}
                        pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 个项目` }}
                      />
                    </>
                  ),
                },
                {
                  key: 'contracts',
                  label: `合同（${contracts.length}）`,
                  children: (
                    <>
                      <Alert
                        type="info" showIcon style={{ marginBottom: 12 }}
                        message="报销时需要的合同信息在这里：合同编号、供应商、金额、签订日期、服务期。"
                      />
                      <Table
                        rowKey="id" size="small" dataSource={contracts}
                        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 份合同` }}
                        columns={[
                          { title: '合同编号', dataIndex: 'contract_number', width: 170,
                            render: (v: string) => v || '—' },
                          { title: '合同名称', dataIndex: 'contract_name',
                            render: (v: string, r: DeptContract) => v || r.project_name },
                          { title: '包号', dataIndex: 'package_no', width: 70,
                            render: (v: string) => v || '—' },
                          { title: '供应商', dataIndex: 'supplier_name', width: 200,
                            render: (v: string) => v || '—' },
                          { title: '金额', dataIndex: 'amount', width: 120,
                            render: (v: number | null, r: DeptContract) => r.amount_text || money(v) },
                          { title: '签订日期', dataIndex: 'sign_date', width: 110,
                            render: (v: string) => v || '—' },
                          { title: '服务期', width: 180,
                            render: (_: unknown, r: DeptContract) =>
                              r.service_start ? `${r.service_start} ~ ${r.service_end || '—'}` : '—' },
                          { title: '对应项目', dataIndex: 'project_number', width: 180,
                            render: (v: string, r: DeptContract) => (
                              <a onClick={() => openProject(r.project_id)}>{v || r.project_name}</a>
                            ) },
                        ]}
                      />
                    </>
                  ),
                },
                {
                  key: 'plans',
                  label: `年度计划（${plans.length}）`,
                  children: (
                    <Table
                      rowKey="id" size="small" dataSource={plans}
                      pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条计划` }}
                      columns={[
                        { title: '年度', dataIndex: 'year', width: 70 },
                        { title: '计划名称', dataIndex: 'name' },
                        { title: '需求科室', dataIndex: 'demand_dept', width: 160,
                          render: (v: string) => v || '—' },
                        { title: '预算', dataIndex: 'budget', width: 120,
                          render: (v: number | null) => money(v) },
                        { title: '状态', dataIndex: 'status', width: 110,
                          render: (v: string) => v || '—' },
                        { title: '已立项', width: 200,
                          render: (_: unknown, r: DeptPlan) => r.project
                            ? <a onClick={() => openProject(r.project!.id)}>{r.project.number}</a>
                            : <Text type="secondary">尚未立项</Text> },
                      ]}
                    />
                  ),
                },
              ]}
            />
          </>
        )}
      </Card>

      <Drawer
        width={720} open={!!openId} onClose={() => setOpenId(null)}
        title={detail ? `${detail.number}　${detail.name}` : '项目详情'}
      >
        {drawerLoading ? <Spin /> : !detail ? <Empty /> : (
          <>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}><Statistic title="预算金额" value={money(detail.amount)} valueStyle={{ fontSize: 16 }} /></Col>
              <Col span={8}><Statistic title="采购方式" value={detail.method || '—'} valueStyle={{ fontSize: 16 }} /></Col>
              <Col span={8}><Statistic title="第几次采购" value={`第 ${detail.round} 次`} valueStyle={{ fontSize: 16 }} /></Col>
            </Row>

            {pending ? (
              <Alert
                type="warning" showIcon icon={<ClockCircleOutlined />} style={{ marginBottom: 16 }}
                message={pending.label}
                description={`当前在 ${pending.role_label}「${pending.owner_name}」处，已等待 ${pending.waiting_days} 天`}
              />
            ) : (
              <Alert type="success" showIcon icon={<CheckCircleOutlined />}
                style={{ marginBottom: 16 }} message="当前没有待办环节" />
            )}

            <Title level={5}>办理进度</Title>
            {(progress?.rounds || []).map((rd) => (
              <div key={rd.round_number} style={{ marginBottom: 16 }}>
                <Text strong>第 {rd.round_number} 次采购</Text>
                <Tag style={{ marginLeft: 8 }} color={rd.status === '进行中' ? 'blue' : 'default'}>
                  {rd.status}
                </Tag>
                <Timeline
                  style={{ marginTop: 12 }}
                  items={rd.nodes.map((n) => ({
                    color: n.done ? 'green' : 'gray',
                    children: (
                      <Space direction="vertical" size={0}>
                        <Text>{n.label}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {n.done ? `${n.by || '—'}　${(n.at || '').replace('T', ' ').slice(0, 16)}` : '未完成'}
                        </Text>
                      </Space>
                    ),
                  }))}
                />
              </div>
            ))}

            <Title level={5}>项目资料</Title>
            {tree.length === 0 ? (
              <Empty description="暂无可查看的资料" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : tree.map((f) => (
              <List
                key={f.folder} size="small" header={<Text strong>{f.folder}</Text>}
                dataSource={f.items} style={{ marginBottom: 12 }}
                renderItem={(it) => (
                  <List.Item
                    actions={[
                      <Button key="p" type="link" size="small" icon={<EyeOutlined />}
                        href={it.preview_url} target="_blank">预览</Button>,
                      <Button key="d" type="link" size="small" icon={<DownloadOutlined />}
                        href={it.url}>下载</Button>,
                    ]}
                  >
                    <Space><FileTextOutlined /><Text>{it.name}</Text></Space>
                  </List.Item>
                )}
              />
            ))}

            {detail.contracts.length > 0 && (
              <>
                <Title level={5}>合同</Title>
                <List
                  size="small" dataSource={detail.contracts}
                  renderItem={(c) => (
                    <List.Item>
                      <Space direction="vertical" size={0}>
                        <Text strong>{c.contract_name || c.contract_number || '合同'}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {c.supplier_name || '—'}　{c.amount_text || money(c.amount)}
                          {c.sign_date ? `　签订于 ${c.sign_date}` : ''}
                        </Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </>
            )}

            {detail.content && (
              <>
                <Title level={5}>采购内容</Title>
                <Paragraph type="secondary" style={{ whiteSpace: 'pre-wrap' }}>{detail.content}</Paragraph>
              </>
            )}
          </>
        )}
      </Drawer>
    </div>
  )
}
