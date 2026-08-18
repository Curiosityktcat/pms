/**
 * 1.0 采购计划池 —— 归口科室报上来的年度采购计划。
 *
 * 与「项目」是两条命：计划年初就有、一个科室上百条，只有一部分会真的立项。
 * 所以这里不是项目列表，而是科室台账 + 与正式项目的挂钩关系。
 * 关联只认人工点选（错绑的清理代价远大于点一下），系统只按关键词给候选提示。
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Card, Table, Button, App, Tag, Typography, Space, Modal, Input, Select,
  Alert, Empty, Statistic, Row, Col, Upload, List, Popconfirm, Switch,
} from 'antd'
import {
  ProfileOutlined, LinkOutlined, DisconnectOutlined, PaperClipOutlined,
  ReloadOutlined, InboxOutlined, DeleteOutlined, DownloadOutlined,
  SearchOutlined, FileExcelOutlined, UploadOutlined,
} from '@ant-design/icons'
import {
  getPlanMeta, listPlans, getPlanStats, linkPlanProject, unlinkPlanProject,
  getPlanCandidates, listPlanAttachments, uploadPlanAttachments,
  deletePlanAttachment, planAttachmentUrl,
  planLinkSheetUrl, importPlanLinkSheet, type LinkImportResult,
  type PlanItem, type PlanMeta, type PlanStats, type PlanAttachment,
  type PlanCandidate,
} from '../services/procurementPlan'

const { Text, Paragraph } = Typography

const money = (n: number) =>
  !n ? '—' : n >= 10000 ? `${(n / 10000).toFixed(2)} 万元` : `${n.toFixed(2)} 元`

export default function ProcurementPlanPage() {
  const { message } = App.useApp()
  const [meta, setMeta] = useState<PlanMeta | null>(null)
  const [rows, setRows] = useState<PlanItem[]>([])
  const [stats, setStats] = useState<PlanStats | null>(null)
  const [loading, setLoading] = useState(false)

  const [year, setYear] = useState<string>('')
  const [dept, setDept] = useState<string>()
  const [category, setCategory] = useState<string>()
  const [method, setMethod] = useState<string>()
  const [linked, setLinked] = useState<string>()
  const [keyword, setKeyword] = useState('')
  // 「已合并 / 已集采 / 延期合并」的条目默认藏起来——它们不会走到采购部，
  // 混在待立项里会让人以为还有一堆活没干
  const [includeClosed, setIncludeClosed] = useState(false)

  const [linkRow, setLinkRow] = useState<PlanItem | null>(null)
  const [cands, setCands] = useState<PlanCandidate[]>([])
  const [candKw, setCandKw] = useState('')
  const [candLoading, setCandLoading] = useState(false)

  const [attRow, setAttRow] = useState<PlanItem | null>(null)
  const [atts, setAtts] = useState<PlanAttachment[]>([])
  const [attLoading, setAttLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (year) params.year = year
      if (dept) params.dept = dept
      if (category) params.category = category
      if (method) params.method = method
      if (linked) params.linked = linked
      if (keyword.trim()) params.keyword = keyword.trim()
      if (includeClosed) params.include_closed = '1'
      const [m, r, s] = await Promise.all([
        getPlanMeta(), listPlans(params), getPlanStats(year || undefined),
      ])
      setMeta(m.data.data)
      setRows(r.data.data || [])
      setStats(s.data.data)
      if (!year && m.data.data.years.length) setYear(String(m.data.data.years[0]))
    } catch {
      message.error('加载采购计划失败')
    } finally {
      setLoading(false)
    }
  }, [message, year, dept, category, method, linked, keyword, includeClosed])
  useEffect(() => { load() }, [load])

  // ── 关联采购项目 ───────────────────────────────────────────
  const openLink = async (row: PlanItem) => {
    setLinkRow(row); setCands([]); setCandKw('')
    setCandLoading(true)
    try {
      const res = await getPlanCandidates(row.id)
      setCands(res.data.data || [])
    } finally { setCandLoading(false) }
  }
  const searchCands = async () => {
    if (!linkRow) return
    setCandLoading(true)
    try {
      const res = await getPlanCandidates(linkRow.id, candKw.trim())
      setCands(res.data.data || [])
    } finally { setCandLoading(false) }
  }
  const doLink = async (projectId: number) => {
    if (!linkRow) return
    try {
      const res = await linkPlanProject(linkRow.id, { project_id: projectId })
      message.success(res.data.message || '已关联')
      setLinkRow(null); load()
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '关联失败')
    }
  }
  const doUnlink = async (row: PlanItem) => {
    await unlinkPlanProject(row.id)
    message.success('已解除关联')
    load()
  }

  // ── 附件 ───────────────────────────────────────────────────
  const openAtt = async (row: PlanItem) => {
    setAttRow(row); setAttLoading(true)
    try {
      const res = await listPlanAttachments(row.id)
      setAtts(res.data.data || [])
    } finally { setAttLoading(false) }
  }
  const doUpload = async (files: File[]) => {
    if (!attRow || !files.length) return
    try {
      await uploadPlanAttachments(attRow.id, files)
      message.success(`已上传 ${files.length} 个文件`)
      const res = await listPlanAttachments(attRow.id)
      setAtts(res.data.data || [])
      load()
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '上传失败')
    }
  }
  const doDeleteAtt = async (a: PlanAttachment) => {
    if (!attRow) return
    await deletePlanAttachment(attRow.id, a.id)
    message.success('已删除')
    const res = await listPlanAttachments(attRow.id)
    setAtts(res.data.data || [])
    load()
  }

  const canEdit = meta?.can_edit ?? false
  const deptOptions = useMemo(
    () => (meta?.depts || []).map(d => ({ label: d, value: d })), [meta])

  const columns = [
    {
      title: '计划项目名称', dataIndex: 'name', width: 300, fixed: 'left' as const,
      render: (v: string, r: PlanItem) => (
        <div>
          <Text strong>{v}</Text>
          {r.package_no && <Tag style={{ marginLeft: 6 }}>{r.package_no}</Tag>}
          {!r.will_procure && <Tag color="default" style={{ marginLeft: 6 }}>{r.status}</Tag>}
          {r.note && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.note}</Text></div>}
        </div>
      ),
    },
    { title: '归口科室', dataIndex: 'dept', width: 100 },
    { title: '需求科室', dataIndex: 'demand_dept', width: 100, render: (v: string) => v || '—' },
    {
      title: '分类', dataIndex: 'category', width: 110,
      render: (v: string, r: PlanItem) => (
        <Space size={4} wrap>
          {v && <Tag color="blue">{v}</Tag>}
          {r.category2 && <Tag>{r.category2}</Tag>}
        </Space>
      ),
    },
    { title: '组织形式', dataIndex: 'org_form', width: 100, render: (v: string) => v || '—' },
    { title: '采购方式', dataIndex: 'method', width: 100, render: (v: string) => v || '—' },
    {
      title: '预算', dataIndex: 'budget', width: 120,
      sorter: (a: PlanItem, b: PlanItem) => (a.budget || 0) - (b.budget || 0),
      render: (v: number) => money(v),
    },
    { title: '采购期限', dataIndex: 'deadline', width: 110, render: (v: string) => v || '—' },
    {
      title: '关联采购项目', dataIndex: 'project_id', width: 260,
      render: (_: unknown, r: PlanItem) => r.project_id ? (
        <Space direction="vertical" size={0}>
          <Text code>{r.project_number}</Text>
          <Text style={{ fontSize: 12 }}>{r.project_name}</Text>
          <Space size={4}>
            <Tag color="green">{r.project_status}</Tag>
            {canEdit && (
              <Popconfirm title="解除与该采购项目的关联？" onConfirm={() => doUnlink(r)}>
                <Button size="small" type="link" danger icon={<DisconnectOutlined />}>解除</Button>
              </Popconfirm>
            )}
          </Space>
        </Space>
      ) : (
        canEdit
          ? <Button size="small" icon={<LinkOutlined />} onClick={() => openLink(r)}>关联项目</Button>
          : <Text type="secondary">未关联</Text>
      ),
    },
    {
      title: '资料', dataIndex: 'attachment_count', width: 100, fixed: 'right' as const,
      render: (n: number, r: PlanItem) => (
        <Button size="small" icon={<PaperClipOutlined />} onClick={() => openAtt(r)}>
          {n > 0 ? `${n} 个` : '上传'}
        </Button>
      ),
    },
  ]

  // ── Excel 对照表：导出填编号 → 传回来批量关联 ──────────────────
  // 先出预览再落库：一次几百条，写错了回滚起来很痛苦。
  const [impOpen, setImpOpen] = useState(false)
  const [impFile, setImpFile] = useState<File | null>(null)
  const [impResult, setImpResult] = useState<LinkImportResult | null>(null)
  const [impBusy, setImpBusy] = useState(false)

  const doImport = async (file: File, dryRun: boolean) => {
    setImpBusy(true)
    try {
      const res = await importPlanLinkSheet(file, dryRun)
      setImpResult(res.data)
      if (!dryRun) {
        message.success(res.data.message || '已导入')
        load()
      }
    } catch (err: unknown) {
      const e = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(e || '导入失败')
      setImpResult(null)
    } finally { setImpBusy(false) }
  }

  return (
    <Card title={<span><ProfileOutlined /> 1.0 采购计划池</span>}
      extra={
        <Space>
          <Button icon={<FileExcelOutlined />} href={planLinkSheetUrl}>
            导出对照表
          </Button>
          <Button type="primary" ghost icon={<UploadOutlined />}
            onClick={() => { setImpOpen(true); setImpFile(null); setImpResult(null) }}>
            导入对照表
          </Button>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      }>
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        message="这里是归口科室报上来的年度采购计划，是采购项目的「前身」。一条计划真正立项后，用「关联项目」挂到对应的采购项目上，之后就能对着看计划预算与实际采购结果。「已合并 / 已集采 / 延期合并」的条目不会走到采购部，默认已隐藏。关联只支持人工点选，系统按关键词给候选提示但不自动绑定——科室的叫法和正式立项名往往对不上，错绑的清理代价比人工点一下大得多。条数多的时候用右上角「导出对照表」，在 Excel 里把项目编号填好再传回来，比一条条点快。"
      />

      {stats && (
        <Row gutter={12} style={{ marginBottom: 12 }}>
          <Col xs={12} sm={8} md={4}>
            <Card size="small"><Statistic title="有效计划" value={stats.live} suffix="条" /></Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small"><Statistic title="已立项关联" value={stats.linked} suffix="条"
              valueStyle={{ color: '#34a853' }} /></Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small"><Statistic title="尚未关联" value={stats.unlinked} suffix="条"
              valueStyle={{ color: '#f9ab00' }} /></Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small"><Statistic title="不进采购部" value={stats.closed} suffix="条"
              valueStyle={{ color: '#5f6368' }} /></Card>
          </Col>
          <Col xs={24} sm={16} md={8}>
            <Card size="small"><Statistic title="计划预算合计"
              value={stats.budget_sum / 10000} precision={2} suffix="万元" /></Card>
          </Col>
        </Row>
      )}

      <Space wrap style={{ marginBottom: 12 }}>
        <Select style={{ width: 110 }} placeholder="年度" value={year || undefined}
          onChange={v => setYear(v || '')} allowClear
          options={(meta?.years || []).map(y => ({ label: `${y} 年`, value: String(y) }))} />
        <Select style={{ width: 140 }} placeholder="归口科室" value={dept} allowClear
          onChange={setDept} options={deptOptions} showSearch />
        <Select style={{ width: 130 }} placeholder="分类" value={category} allowClear
          onChange={setCategory}
          options={(meta?.categories || []).map(c => ({ label: c, value: c }))} />
        <Select style={{ width: 130 }} placeholder="采购方式" value={method} allowClear
          onChange={setMethod}
          options={(meta?.methods || []).map(c => ({ label: c, value: c }))} />
        <Select style={{ width: 140 }} placeholder="关联状态" value={linked} allowClear
          onChange={setLinked} options={[
            { label: '已关联项目', value: '1' },
            { label: '尚未关联', value: '0' },
          ]} />
        <Input.Search allowClear style={{ width: 240 }} placeholder="搜项目名 / 编号 / 备注"
          value={keyword} onChange={e => setKeyword(e.target.value)} onSearch={load} />
        <Space size={6}>
          <Switch size="small" checked={includeClosed} onChange={setIncludeClosed} />
          <Text type="secondary">显示已合并/已集采/延期</Text>
        </Space>
      </Space>

      {rows.length === 0 && !loading
        ? <Empty description="没有符合条件的采购计划" />
        : (
          <Table
            rowKey="id" loading={loading} dataSource={rows} columns={columns}
            size="middle" scroll={{ x: 1500 }}
            pagination={{ pageSize: 30, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
            rowClassName={r => (r.will_procure ? '' : 'plan-row-closed')}
          />
        )}

      {/* ── 导入 Excel 对照表：先预览，确认无误再落库 ── */}
      <Modal
        open={impOpen}
        title={<span><FileExcelOutlined /> 导入对照表</span>}
        width={760}
        onCancel={() => setImpOpen(false)}
        footer={[
          <Button key="c" onClick={() => setImpOpen(false)}>关闭</Button>,
          <Button key="ok" type="primary" disabled={!impFile || !impResult?.will_link}
            loading={impBusy}
            onClick={async () => { if (impFile) { await doImport(impFile, false); setImpOpen(false) } }}>
            确认写入{impResult?.will_link ? `（${impResult.will_link} 条）` : ''}
          </Button>,
        ]}
      >
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="怎么用"
          description={<span>
            点右上角「导出对照表」下载 Excel → 在最后一列「项目编号（请填这里）」填上编号
            （编号在第二张工作表里查）→ 存好后传到这里。
            <b>空着的行一律不动</b>，先给你预览，确认无误再写入。
          </span>} />

        <Upload.Dragger
          multiple={false} showUploadList={false} accept=".xlsx,.xlsm"
          disabled={impBusy}
          beforeUpload={(file) => {
            setImpFile(file as File)
            doImport(file as File, true)     // 传上来先预览
            return false
          }}
          style={{ marginBottom: 12 }}
        >
          <p style={{ margin: 0, fontSize: 24, color: '#1a73e8' }}><InboxOutlined /></p>
          <p style={{ margin: '4px 0 0' }}>
            {impBusy ? '正在读取…' : impFile ? `已选：${impFile.name}（重新拖一个可替换）` : '把填好的 Excel 拖到这里'}
          </p>
        </Upload.Dragger>

        {impResult && (
          <>
            <Space wrap style={{ marginBottom: 8 }}>
              <Tag color="blue">可关联 {impResult.will_link} 条</Tag>
              <Tag>空着/无变化 {impResult.skipped} 条</Tag>
              {impResult.errors.length > 0 && <Tag color="red">有问题 {impResult.errors.length} 条</Tag>}
            </Space>

            {impResult.errors.length > 0 && (
              <Alert type="warning" showIcon style={{ marginBottom: 8 }}
                message="下面这些不会被写入，其余的照常"
                description={<div style={{ maxHeight: 130, overflowY: 'auto' }}>
                  {impResult.errors.map((e, i) => <div key={i} style={{ fontSize: 12 }}>{e}</div>)}
                </div>} />
            )}

            {impResult.will_link > 0 ? (
              <Table size="small" rowKey="row" pagination={false} scroll={{ y: 260 }}
                dataSource={impResult.data}
                columns={[
                  { title: '表格行', dataIndex: 'row', width: 70 },
                  { title: '计划', dataIndex: 'plan_name', ellipsis: true },
                  {
                    title: '要关联到', dataIndex: 'project_number', width: 300,
                    render: (v: string, r) => (
                      <span><Text code>{v}</Text>　
                        <Text type="secondary" style={{ fontSize: 12 }}>{r.project_name}</Text>
                        {r.was_linked && <Tag color="orange" style={{ marginInlineStart: 4 }}>会改掉原来的关联</Tag>}
                      </span>
                    ),
                  },
                ]} />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这份表里没有可写入的行" />
            )}
          </>
        )}
      </Modal>

      {/* ── 关联采购项目 ── */}
      <Modal
        open={!!linkRow} onCancel={() => setLinkRow(null)} footer={null} width={760}
        title={<span><LinkOutlined /> 关联采购项目</span>}
      >
        {linkRow && (
          <>
            <Paragraph>
              计划条目：<Text strong>{linkRow.name}</Text>
              {linkRow.dept && <Tag style={{ marginLeft: 8 }}>{linkRow.dept}</Tag>}
            </Paragraph>
            <Alert type="warning" showIcon style={{ marginBottom: 12 }}
              message="下面是按名称相近度给的候选，仅供参考。科室的叫法和正式立项名经常对不上，请自行确认后再点关联。" />
            <Space style={{ marginBottom: 12 }}>
              <Input placeholder="按项目名或编号搜索" value={candKw}
                onChange={e => setCandKw(e.target.value)} onPressEnter={searchCands}
                style={{ width: 320 }} />
              <Button icon={<SearchOutlined />} onClick={searchCands}>搜索</Button>
            </Space>
            <List
              loading={candLoading} dataSource={cands} size="small"
              locale={{ emptyText: '没有候选项目，试试用关键词搜索' }}
              style={{ maxHeight: 380, overflowY: 'auto' }}
              renderItem={c => (
                <List.Item actions={[
                  <Button key="k" type="primary" size="small"
                    onClick={() => doLink(c.id)}>关联</Button>,
                ]}>
                  <List.Item.Meta
                    title={<Space><Text code>{c.number}</Text><Text>{c.name}</Text></Space>}
                    description={<Space size={6}>
                      <Tag>{c.status}</Tag>
                      {c.officer && <Text type="secondary">经办 {c.officer}</Text>}
                    </Space>}
                  />
                </List.Item>
              )}
            />
          </>
        )}
      </Modal>

      {/* ── 附件 ── */}
      <Modal
        open={!!attRow} onCancel={() => setAttRow(null)} footer={null} width={720}
        title={<span><PaperClipOutlined /> 项目资料 —— {attRow?.name}</span>}
      >
        <Upload.Dragger
          multiple showUploadList={false} style={{ marginBottom: 12 }}
          beforeUpload={(_f, fileList) => { doUpload(fileList as File[]); return false }}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">把文件拖到这里，或点击选择</p>
          <p className="ant-upload-hint">
            支持 pdf / word / excel / 图片 / 压缩包。从 WPS 导入的原始资料不可删除文件本身，只能解除挂载。
          </p>
        </Upload.Dragger>
        <List
          loading={attLoading} dataSource={atts} size="small"
          locale={{ emptyText: '还没有资料' }}
          renderItem={a => (
            <List.Item actions={[
              <a key="v" href={planAttachmentUrl(attRow!.id, a.id)}
                target="_blank" rel="noreferrer">查看</a>,
              <a key="d" href={planAttachmentUrl(attRow!.id, a.id, true)}>
                <DownloadOutlined /> 下载</a>,
              canEdit ? (
                <Popconfirm key="x" title="删除这个资料？" onConfirm={() => doDeleteAtt(a)}>
                  <Button type="link" danger size="small" icon={<DeleteOutlined />} />
                </Popconfirm>
              ) : null,
            ].filter(Boolean)}>
              <List.Item.Meta
                title={<Space>
                  <Text>{a.filename}</Text>
                  {a.source === 'wps' && <Tag color="purple">WPS 导入</Tag>}
                  {a.exists === false && <Tag color="red">文件丢失</Tag>}
                </Space>}
                description={<Text type="secondary" style={{ fontSize: 12 }}>
                  {(a.size / 1024).toFixed(0)} KB · {a.uploaded_by} · {a.uploaded_at?.slice(0, 10)}
                </Text>}
              />
            </List.Item>
          )}
        />
      </Modal>
    </Card>
  )
}
