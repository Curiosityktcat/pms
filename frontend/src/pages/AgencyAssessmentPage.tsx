/**
 * 代理机构服务质量考核（按客户《招标代理机构服务质量考核评价表》）
 *
 * 三个页签：
 *   待考核  —— 已到合同/归档阶段、还没打过分的项目，点进去填表
 *   已考核  —— 打过分的项目，可查看/撤回重打
 *   机构汇总 —— 各代理机构近 3 个月的累计分与处置建议（暂停拟派/提前拟派/暂停资格）
 *
 * 填表时系统会对 6 个可量化项给出建议分（时效算天数、规范性数驳回次数），
 * 每个建议分都写清依据；采购部对接人可直接改，改了以人填的为准。
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Card, Tabs, Table, Button, App, Tag, Typography, Space, Modal, Input,
  InputNumber, Radio, Checkbox, Alert, Descriptions, Select, Empty, DatePicker,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import {
  AuditOutlined, WarningOutlined, ThunderboltOutlined, ReloadOutlined,
} from '@ant-design/icons'
import {
  getAssessMeta, listAssessments, listPendingProjects, getAssessment,
  saveAssessment, revokeAssessment, getAgencySummary,
  type Assessment, type AssessMeta, type AgencySummary, type PendingProject,
} from '../services/agencyAssessment'

const { Text, Paragraph } = Typography

export default function AgencyAssessmentPage() {
  const { message, modal } = App.useApp()
  const [tab, setTab] = useState<'pending' | 'done' | 'summary'>('pending')
  const [meta, setMeta] = useState<AssessMeta | null>(null)
  const [pending, setPending] = useState<PendingProject[]>([])
  const [done, setDone] = useState<Assessment[]>([])
  const [summary, setSummary] = useState<AgencySummary[]>([])
  const [loading, setLoading] = useState(false)
  // 机构汇总的统计区间。默认「本年 1 月 ~ 本月」——历史考核按项目所属月份记，
  // 用考核办法默认的「近 3 个月」会几乎全空，看不了「2026 年以来」的账。
  const [range, setRange] = useState<[Dayjs, Dayjs]>(
    () => [dayjs().startOf('year'), dayjs()])
  const [keyword, setKeyword] = useState('')
  const [agencyFilter, setAgencyFilter] = useState<string>()

  // 填表弹窗
  const [cur, setCur] = useState<Assessment | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [ms, me] = [range[0].format('YYYY-MM'), range[1].format('YYYY-MM')]
      const [m, p, d, s] = await Promise.all([
        getAssessMeta(), listPendingProjects(),
        listAssessments({ start: ms, end: me }), getAgencySummary(ms, me),
      ])
      setMeta(m.data.data)
      setPending(p.data.data || [])
      setDone(d.data.data || [])
      setSummary(s.data.data || [])
    } catch {
      message.error('加载考核数据失败')
    } finally {
      setLoading(false)
    }
  }, [message, range])
  useEffect(() => { load() }, [load])

  const openForm = useCallback(async (pid: number) => {
    try {
      const res = await getAssessment(pid)
      setCur(res.data.data)
    } catch {
      message.error('打开考核表失败')
    }
  }, [message])

  // 待办「去处理」跳来时（?focus=项目id）直接把考核表打开，省得再翻列表找
  const focusId = Number(new URLSearchParams(window.location.search).get('focus') || 0)
  const [focusDone, setFocusDone] = useState(false)
  useEffect(() => {
    if (focusId && !focusDone && !loading && (pending.length || done.length)) {
      setFocusDone(true)
      openForm(focusId)
    }
  }, [focusId, focusDone, loading, pending.length, done.length, openForm])

  const patchItem = (key: string, field: 'score' | 'note', v: unknown) => {
    setCur(c => c && ({
      ...c,
      items: c.items.map(i => i.key === key ? { ...i, [field]: v } : i),
    }))
  }

  // 代理机构只能看不能改：后端已挡写操作，前端把输入控件一并禁用，避免白改一场
  const readonly = !meta?.can_assess || !!(cur as { readonly?: boolean } | null)?.readonly

  const liveTotal = useMemo(
    () => cur ? Math.round((100 + cur.items.reduce((s, i) => s + (Number(i.score) || 0), 0)) * 100) / 100 : 100,
    [cur],
  )

  const doSave = async (submit: boolean) => {
    if (!cur) return
    if (submit && !cur.subj_timeliness) {
      message.warning('请先完成「综合评价」三项勾选')
      return
    }
    setSaving(true)
    try {
      const res = await saveAssessment(cur.project_id, cur, submit)
      message.success(res.data.message || '已保存')
      if (submit) setCur(null)
      else setCur(c => c && ({ ...c, ...res.data.data, items: c.items }))
      load()
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const doRevoke = (a: Assessment) => {
    modal.confirm({
      title: '撤回考核',
      content: `撤回「${a.project_name}」的考核？撤回后可重新打分，撤回期间不计入机构累计分。`,
      onOk: async () => {
        await revokeAssessment(a.id!)
        message.success('已撤回')
        load()
      },
    })
  }

  const kw = keyword.trim()
  const filterPending = pending.filter(p =>
    (!agencyFilter || p.agency_name === agencyFilter) &&
    (!kw || p.name.includes(kw) || p.number.includes(kw) || (p.agency_name || '').includes(kw)))
  const filterDone = done.filter(a =>
    (!agencyFilter || a.agency_name === agencyFilter) &&
    (!kw || a.project_name.includes(kw) || a.project_number.includes(kw) || (a.agency_name || '').includes(kw)))

  const agencyOptions = Array.from(new Set([
    ...pending.map(p => p.agency_name), ...done.map(d => d.agency_name),
  ].filter(Boolean))).sort().map(v => ({ value: v, label: v }))

  const scoreTag = (n: number) => {
    const pass = meta?.thresholds.pass_line ?? 90
    return <Tag color={n >= pass ? 'green' : n >= 80 ? 'orange' : 'red'} style={{ fontWeight: 600 }}>{n} 分</Tag>
  }

  const toolbar = (
    <Space wrap style={{ marginBottom: 12 }}>
      <Input.Search allowClear placeholder="搜索项目名称 / 编号 / 代理机构"
        style={{ width: 280 }} onChange={e => setKeyword(e.target.value)} />
      <Select allowClear showSearch placeholder="按代理机构筛选" style={{ width: 200 }}
        value={agencyFilter} onChange={setAgencyFilter} options={agencyOptions} />
      <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
    </Space>
  )

  const periodText = range[0].isSame(range[1], 'month')
    ? range[0].format('YYYY年M月')
    : `${range[0].format('YYYY年M月')} ~ ${range[1].format('YYYY年M月')}`

  // 快捷区间：最常用的就是「今年以来」和「去年全年」，省得每次点两下日历
  const quick = (label: string, from: Dayjs, to: Dayjs) => (
    <Button size="small" onClick={() => setRange([from, to])}>{label}</Button>
  )
  const rangeBar = (
    <Space wrap style={{ marginBottom: 12 }}>
      <Text type="secondary">统计区间</Text>
      <DatePicker.RangePicker
        picker="month" allowClear={false} value={range}
        onChange={v => { if (v && v[0] && v[1]) setRange([v[0], v[1]]) }}
      />
      {quick('今年以来', dayjs().startOf('year'), dayjs())}
      {quick('近3个月', dayjs().subtract(2, 'month'), dayjs())}
      {quick('去年全年', dayjs().subtract(1, 'year').startOf('year'),
             dayjs().subtract(1, 'year').endOf('year'))}
      <Text type="secondary" style={{ fontSize: 12 }}>
        含起含止，按月计；考核归期取项目编号里的年月
      </Text>
    </Space>
  )

  return (
    <Card title={<span><AuditOutlined /> 代理机构服务质量考核</span>}>
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        message={`一个项目一份考核表，由该项目的经办人完成（对应考核表末尾「采购部对接人签字」）。项目走到定标/签约/归档后，系统会自动给经办人派一条「待完成代理机构服务质量考核」待办，点「去处理」直接打开本表，提交后待办自动消除。满分 100 分，得分 = 100 + 各项加扣分之和。系统对 6 个可量化项自动给出建议分（编制/拟合同/归档三项时效按天算，采购文件与公告的规范性按驳回和更正次数算），每个建议分都注明依据，可直接改。低于 ${meta?.thresholds.pass_line ?? 90} 分暂停下一轮拟派；近 ${meta?.thresholds.valid_months ?? 3} 个月累计扣分达 ${meta?.thresholds.suspend_line ?? 30} 分暂停资格 3 个月；累计加分达 ${meta?.thresholds.bonus_line ?? 10} 分可提前一轮拟派。`}
      />

      <Tabs
        activeKey={tab}
        onChange={k => setTab(k as typeof tab)}
        items={[
          { key: 'pending', label: `待考核 (${pending.length})` },
          { key: 'done', label: `已考核 (${done.length})` },
          { key: 'summary', label: '机构汇总' },
        ]}
      />

      {tab !== 'summary' && toolbar}
      {tab === 'done' && rangeBar}

      {tab === 'pending' && (
        <Table
          rowKey="id" loading={loading} dataSource={filterPending} size="middle"
          locale={{ emptyText: '没有待考核的项目（项目需推进到定标/合同/归档阶段才可考核）' }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          columns={[
            { title: '项目名称', dataIndex: 'name', render: (v: string) => <Text strong>{v}</Text> },
            { title: '项目编号', dataIndex: 'number', width: 170 },
            { title: '代理机构', dataIndex: 'agency_name', width: 180 },
            { title: '采购方式', dataIndex: 'method', width: 130 },
            { title: '经办人', dataIndex: 'officer', width: 100 },
            { title: '阶段', dataIndex: 'status', width: 100, render: (v: string) => <Tag>{v}</Tag> },
            {
              title: '操作', width: 110, fixed: 'right',
              render: (_: unknown, r: PendingProject) => (
                <Button size="small" type="primary" onClick={() => openForm(r.id)}>去考核</Button>
              ),
            },
          ]}
        />
      )}

      {tab === 'done' && (
        <Table
          rowKey="id" loading={loading} dataSource={filterDone} size="middle"
          locale={{ emptyText: '暂无已考核项目' }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          columns={[
            { title: '项目名称', dataIndex: 'project_name', render: (v: string) => <Text strong>{v}</Text> },
            { title: '项目编号', dataIndex: 'project_number', width: 170 },
            { title: '代理机构', dataIndex: 'agency_name', width: 180 },
            {
              title: '得分', dataIndex: 'total_score', width: 110,
              sorter: (a: Assessment, b: Assessment) => a.total_score - b.total_score,
              render: (v: number, r: Assessment) => (
                <Space size={4}>
                  {scoreTag(v)}
                  {!!r.veto_hit && <Tag color="red" icon={<WarningOutlined />}>一票否决</Tag>}
                </Space>
              ),
            },
            { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag color={v === '已提交' ? 'green' : 'default'}>{v}</Tag> },
            { title: '考核人', dataIndex: 'assessor', width: 100 },
            { title: '考核时间', dataIndex: 'assessed_at', width: 160, render: (v: string) => (v || '').replace('T', ' ').slice(0, 16) },
            {
              title: '操作', width: 160, fixed: 'right',
              render: (_: unknown, r: Assessment) => (
                <Space size={4}>
                  <Button size="small" onClick={() => openForm(r.project_id)}>查看</Button>
                  {r.status === '已提交' && meta?.can_assess && (
                    <Button size="small" danger onClick={() => doRevoke(r)}>撤回</Button>
                  )}
                </Space>
              ),
            },
          ]}
        />
      )}

      {tab === 'summary' && (
        <>
          {rangeBar}
          <Alert type="warning" showIcon style={{ marginBottom: 12 }}
            message={`按考核办法：日常考核扣分有效期 3 个月，在日常工作中累加计算。下表为各代理机构在 ${periodText} 已提交考核的汇总与对应处置建议。历史考核按项目编号里的年月归期，不是导入日期。`} />
          {summary.length === 0
            ? <Empty description="暂无考核数据" />
            : (
              <Table
                rowKey="agency_code" loading={loading} dataSource={summary} size="middle"
                pagination={false}
                columns={[
                  { title: '代理机构', dataIndex: 'agency_name', render: (v: string) => <Text strong>{v}</Text> },
                  { title: `${periodText} 考核数`, dataIndex: 'count', width: 130 },
                  {
                    title: '平均分', dataIndex: 'avg', width: 110,
                    render: (v: number | null) => v == null ? '—' : scoreTag(v),
                  },
                  {
                    title: '累计加扣分', dataIndex: 'net', width: 120,
                    render: (v: number) => (
                      <Text type={v < 0 ? 'danger' : v > 0 ? 'success' : undefined} strong>
                        {v > 0 ? `+${v}` : v}
                      </Text>
                    ),
                  },
                  {
                    title: '一票否决', dataIndex: 'veto', width: 100,
                    render: (v: number) => v ? <Tag color="red">{v} 次</Tag> : '—',
                  },
                  {
                    title: '处置建议', dataIndex: 'advice',
                    render: (v: string, r: AgencySummary) => (
                      <Space direction="vertical" size={2}>
                        <span>{v}</span>
                        {r.flags.length > 0 && (
                          <Space size={4} wrap>
                            {r.flags.map(f => (
                              <Tag key={f} color={f.includes('加分') ? 'green' : 'red'}
                                icon={f.includes('加分') ? <ThunderboltOutlined /> : <WarningOutlined />}>
                                {f}
                              </Tag>
                            ))}
                          </Space>
                        )}
                      </Space>
                    ),
                  },
                ]}
              />
            )}
        </>
      )}

      {/* ── 考核表填写弹窗 ─────────────────────────────────────── */}
      <Modal
        open={!!cur}
        title={`服务质量考核 — ${cur?.project_name || ''}`}
        width={1000}
        onCancel={() => setCur(null)}
        footer={readonly ? (
          <Button onClick={() => setCur(null)}>关闭</Button>
        ) : [
          <Button key="c" onClick={() => setCur(null)}>取消</Button>,
          <Button key="s" loading={saving} onClick={() => doSave(false)}>保存草稿</Button>,
          <Button key="t" type="primary" loading={saving} onClick={() => doSave(true)}>提交考核</Button>,
        ]}
        destroyOnHidden
      >
        {cur && (
          <>
            <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }}>
              <Descriptions.Item label="项目名称及编号">
                {cur.project_name}　{cur.project_number}
              </Descriptions.Item>
              <Descriptions.Item label="代理机构名称">{cur.agency_name}</Descriptions.Item>
            </Descriptions>

            <div style={{
              position: 'sticky', top: 0, zIndex: 2, background: '#fff',
              padding: '8px 0', borderBottom: '1px solid #f0f0f0', marginBottom: 8,
            }}>
              <Space>
                <Text strong style={{ fontSize: 16 }}>本表合计：</Text>
                {scoreTag(liveTotal)}
                <Text type="secondary" style={{ fontSize: 12 }}>
                  （满分 100 + 各项加扣分之和；低于 {meta?.thresholds.pass_line ?? 90} 分将暂停下一轮拟派）
                </Text>
                {cur.veto.length > 0 && (
                  <Tag color="red" icon={<WarningOutlined />}>已勾选一票否决，本项目直接否决</Tag>
                )}
              </Space>
            </div>

            <Text strong>二、考核内容及评分标准</Text>
            <Table
              rowKey="key" size="small" pagination={false} style={{ marginTop: 8 }}
              dataSource={cur.items}
              columns={[
                {
                  title: '考核内容', dataIndex: 'name',
                  render: (v: string, r) => (
                    <div>
                      <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>{v}</div>
                      <div style={{ fontSize: 11, color: '#9aa0a6', marginTop: 3 }}>{r.standard}</div>
                    </div>
                  ),
                },
                {
                  title: '系统建议', width: 220,
                  render: (_: unknown, r) => r.auto_score == null && !r.auto_basis
                    ? <Text type="secondary" style={{ fontSize: 11 }}>需人工判断</Text>
                    : (
                      <div>
                        {r.auto_score != null && (
                          <Tag color={r.auto_score > 0 ? 'green' : r.auto_score < 0 ? 'red' : 'default'}>
                            {r.auto_score > 0 ? `+${r.auto_score}` : r.auto_score}
                          </Tag>
                        )}
                        <div style={{ fontSize: 11, color: '#5f6368', marginTop: 2, lineHeight: 1.45 }}>
                          {r.auto_basis}
                        </div>
                        {r.auto_score != null && r.score !== r.auto_score && (
                          <Button size="small" type="link" style={{ padding: 0, height: 18, fontSize: 11 }}
                            onClick={() => patchItem(r.key, 'score', r.auto_score)}>
                            用建议分
                          </Button>
                        )}
                      </div>
                    ),
                },
                {
                  title: '扣分/加分', width: 110,
                  render: (_: unknown, r) => (
                    <InputNumber
                      size="small" step={0.5} style={{ width: 90 }}
                      disabled={readonly}
                      value={r.score}
                      onChange={v => patchItem(r.key, 'score', v ?? 0)}
                    />
                  ),
                },
                {
                  title: '备注/说明', width: 200,
                  render: (_: unknown, r) => (
                    <Input.TextArea
                      size="small" autoSize={{ minRows: 1, maxRows: 3 }} maxLength={200}
                      disabled={readonly}
                      value={r.note}
                      onChange={e => patchItem(r.key, 'note', e.target.value)}
                    />
                  ),
                },
              ]}
            />

            <div style={{ marginTop: 16 }}>
              <Text strong>三、一票否决项目</Text>
              <Alert type="error" showIcon style={{ margin: '6px 0' }}
                message="勾选任意一条即触发一票否决——按考核办法暂停代理我院采购项目资格一年。请谨慎勾选并写明事实依据。" />
              <Checkbox.Group
                disabled={readonly}
                value={cur.veto}
                onChange={v => setCur(c => c && ({ ...c, veto: v as string[] }))}
                style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
              >
                {(meta?.veto_items || []).map(v => (
                  <Checkbox key={v.key} value={v.key} style={{ fontSize: 12.5 }}>{v.name}</Checkbox>
                ))}
              </Checkbox.Group>
              {cur.veto.length > 0 && (
                <Input.TextArea
                  style={{ marginTop: 8 }} rows={2} maxLength={500} showCount
                  placeholder="请写明一票否决的事实依据（必填）"
                  value={cur.veto_note}
                  onChange={e => setCur(c => c && ({ ...c, veto_note: e.target.value }))}
                />
              )}
            </div>

            <div style={{ marginTop: 16 }}>
              <Text strong>四、综合评价（非评分项）</Text>
              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {([
                  ['subj_timeliness', '经办人响应的及时性'],
                  ['subj_ability', '经办人水平和能力'],
                  ['subj_attitude', '经办人合作态度及协调能力'],
                ] as const).map(([field, label]) => (
                  <div key={field}>
                    <Text style={{ display: 'inline-block', width: 200, fontSize: 13 }}>{label}</Text>
                    <Radio.Group
                      disabled={readonly}
                      value={cur[field]}
                      onChange={e => setCur(c => c && ({ ...c, [field]: e.target.value }))}
                    >
                      {(meta?.subj_options || []).map(o => (
                        <Radio key={o} value={o}>{o}</Radio>
                      ))}
                    </Radio.Group>
                  </div>
                ))}
              </div>
              <Input.TextArea
                style={{ marginTop: 10 }} rows={3} maxLength={1000} showCount
                disabled={readonly}
                placeholder="建议或意见（选填）"
                value={cur.comment}
                onChange={e => setCur(c => c && ({ ...c, comment: e.target.value }))}
              />
            </div>

            <Paragraph type="secondary" style={{ fontSize: 11, marginTop: 12, marginBottom: 0 }}>
              注：本考核表得分低于 90 分，将暂停下一轮代理机构项目的拟派；多个项目考核加分累计满 10 分的，提前一轮代理机构项目拟派。
              日常考核扣分有效期为 3 个月，在日常工作中累加计算，但按年计入年度综合考核。
              日常考核有效期内累计加扣分达 30 分的，暂停采购代理资格 3 个月。
            </Paragraph>
          </>
        )}
      </Modal>
    </Card>
  )
}
