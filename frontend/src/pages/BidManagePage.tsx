import { useEffect, useMemo, useState } from 'react'
import {
  Button, Tag, Card, App, Tooltip, Alert, Popconfirm, Modal, Input, Tabs,
  Select, Space, Segmented,
} from 'antd'
import RecordCards, { RecordCard, useIsMobile, type RecordCardData } from '../components/RecordCards'
import {
  FileDoneOutlined, CheckCircleOutlined, StopOutlined,
  ClockCircleOutlined, CalendarOutlined, BarsOutlined,
  LeftOutlined, RightOutlined,
} from '@ant-design/icons'
import { getBidList, markCanOpen, proposeBidFail, confirmBidFail, revokeBidFail } from '../services/bid'
import type { Project } from '../services/project'
import PendingOwnerTag from '../components/PendingOwnerTag'
import { useAuth } from '../hooks/useAuth'
import { useNavigate } from 'react-router-dom'
import { useFocusTarget, flashRow } from '../hooks/useFocusRow'
import { cnOrdinal } from '../utils/ordinal'

// 扩展 Project 类型，包含开标管理附加字段
interface BidProject extends Project {
  ann_id?: number
  ann_round_number?: number
  ann_deadline?: string
  bucket?: string                 // active=进行中 | opened=已开标
  can_open_status?: string        // ''|待确认|已确认
  can_open_reason?: string        // 流标原因
  can_open_by?: string
  can_open_confirmed_by?: string
}

// 中文/ISO 开标时间串 → Date（解析不出返回 null）
function parseBidTime(bidTime: string): Date | null {
  if (!bidTime) return null
  const m = bidTime.match(/(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})?[：:]?(\d{2})?/)
  if (m) return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0))
  const d = new Date(bidTime)
  return isNaN(d.getTime()) ? null : d
}

// 解析中文日期时间，判断开标时间是否临近/已过
function getBidTimeStatus(bidTime: string): { color: string; tip: string } {
  if (!bidTime) return { color: '#ccc', tip: '未设置开标时间' }
  const d = parseBidTime(bidTime)
  if (!d) return { color: '#1677ff', tip: bidTime }
  const diff = d.getTime() - Date.now()
  if (diff < 0)        return { color: '#aaa',    tip: '已过开标时间' }
  if (diff < 86400000) return { color: '#ff4d4f', tip: '24小时内开标' }
  if (diff < 259200000)return { color: '#fa8c16', tip: '3天内开标' }
  return { color: '#52c41a', tip: '开标时间正常' }
}

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
const WEEK_HEAD = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const VIEW_KEY = 'pms_bid_view'
const SPAN_KEY = 'pms_bid_span'   // 日历跨度：month=本月（默认）| week=本周

const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`

export default function BidManagePage() {
  const [projects, setProjects] = useState<BidProject[]>([])
  const [loading, setLoading] = useState(true)
  const { user } = useAuth()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const isMobile = useIsMobile()

  // 筛选 / 搜索 / 视图
  const [officerFilter, setOfficerFilter] = useState<string>()
  const [agencyFilter, setAgencyFilter] = useState<string>()
  const [keyword, setKeyword] = useState('')
  const [view, setView] = useState<'list' | 'calendar'>(
    () => (localStorage.getItem(VIEW_KEY) === 'calendar' ? 'calendar' : 'list'),
  )
  // 日历跨度：默认本月，可切回本周。offset 的单位随跨度走（月视图=月，周视图=周）
  const [span, setSpan] = useState<'week' | 'month'>(
    () => (localStorage.getItem(SPAN_KEY) === 'week' ? 'week' : 'month'),
  )
  const [offset, setOffset] = useState(0)                  // 0=本月/本周，-1 上一个，+1 下一个
  // 已开标页签独立记偏移：已开标的项目基本都在过去，周视图默认落在上一周更顺手
  const [openedOffset, setOpenedOffset] = useState(
    () => (localStorage.getItem(SPAN_KEY) === 'week' ? -1 : 0),
  )
  const switchSpan = (s: 'week' | 'month') => {
    setSpan(s)
    localStorage.setItem(SPAN_KEY, s)
    // 单位变了，偏移必须归零，否则会跳到莫名其妙的日期
    setOffset(0)
    setOpenedOffset(s === 'week' ? -1 : 0)
  }
  const [dayDetail, setDayDetail] = useState<BidProject | null>(null)  // 日历里点开的项目
  const switchView = (v: 'list' | 'calendar') => {
    setView(v)
    localStorage.setItem(VIEW_KEY, v)
  }

  const isAgency = user?.role === 'agency'
  const isOfficer = user?.role === 'officer'
  const canMark = isOfficer || isAgency
  const canAuthLetter = isOfficer || isAgency
  // 流标提交弹窗（代理填写原因）
  const [failRow, setFailRow] = useState<BidProject | null>(null)
  const [failReason, setFailReason] = useState('')
  const [submitting, setSubmitting] = useState(false)

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

  const runAction = async (fn: () => Promise<{ data: { message?: string } }>) => {
    try {
      const res = await fn()
      message.success(res.data.message || '操作成功')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '操作失败')
    }
  }

  // 代理提交流标（弹窗填原因后调用）
  const submitFail = async () => {
    if (!failRow) return
    if (!failReason.trim()) { message.warning('请填写流标原因'); return }
    setSubmitting(true)
    try {
      const res = await proposeBidFail(failRow.id, failReason.trim())
      message.success(res.data.message || '已提交')
      setFailRow(null); setFailReason('')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const canOpenInfo = (row: BidProject): { text: string; color: string } => {
    if (row.can_open === '可开标') return { text: '可开标', color: 'green' }
    if (row.can_open === '流标' && row.can_open_status === '待确认') return { text: '流标待确认', color: 'orange' }
    if (row.can_open === '流标') return { text: '流标', color: 'red' }
    return { text: '未判定', color: 'default' }
  }
  const ACCENT: Record<string, string> = { green: '#34a853', red: '#d93025', orange: '#f9ab00', default: '#9aa0a6' }

  const bidToCard = (row: BidProject, withActions: boolean): RecordCardData => {
    const st = canOpenInfo(row)
    const rn = row.ann_round_number
    const deadline = row.ann_deadline || row.bid_time
    const tcolor = getBidTimeStatus(deadline).color
    const status = row.can_open_status || ''
    const pending = row.can_open === '流标' && status === '待确认'
    return {
      key: row.id,
      accent: ACCENT[st.color] || '#1a73e8',
      title: row.name,
      subtitle: row.number,
      statusText: st.text,
      statusColor: st.color,
      tags: !rn || rn === 1
        ? <Tag color="blue" style={{ marginInlineEnd: 0 }}>第一次</Tag>
        : <Tag color="orange" style={{ marginInlineEnd: 0 }}>第{cnOrdinal(rn)}次</Tag>,
      fields: [
        { label: '当前处理人', value: <PendingOwnerTag p={row.pending} compact /> },
        { label: '经办人', value: row.officer || '—' },
        { label: '代理', value: row.agency_name },
        { label: '开标时间', value: deadline ? <span style={{ color: tcolor, fontWeight: 500 }}><ClockCircleOutlined style={{ marginRight: 4 }} />{deadline}</span> : '' },
      ],
      actions: withActions ? (
        <>
          {canAuthLetter && (
            <Button size="small" icon={<FileDoneOutlined />} type="primary" ghost
              onClick={() => navigate(`/auth-letter?project_id=${row.id}&round=${row.ann_round_number || 1}&bid_time=${encodeURIComponent(row.ann_deadline || row.bid_time || '')}`)}>
              生成授权函
            </Button>
          )}
          {pending && isOfficer && (
            <>
              <Popconfirm title="确认流标？"
                description={<div style={{ maxWidth: 240 }}>原因：{row.can_open_reason || '—'}<br />确认后本轮结束，系统将自动开启下一次采购。</div>}
                okText="确认流标" okButtonProps={{ danger: true }} cancelText="取消"
                onConfirm={() => runAction(() => confirmBidFail(row.id))}>
                <Button size="small" danger icon={<StopOutlined />}>确认流标</Button>
              </Popconfirm>
              <Popconfirm title="退回该流标提交？" okText="退回" cancelText="取消" onConfirm={() => runAction(() => revokeBidFail(row.id))}>
                <Button size="small">退回</Button>
              </Popconfirm>
            </>
          )}
          {pending && isAgency && (
            <Popconfirm title="撤回流标提交？" okText="撤回" cancelText="取消" onConfirm={() => runAction(() => revokeBidFail(row.id))}>
              <Button size="small">撤回流标</Button>
            </Popconfirm>
          )}
          {canMark && status === '' && (
            <Popconfirm title="标记为可开标？" okText="确认" cancelText="取消" onConfirm={() => runAction(() => markCanOpen(row.id))}>
              <Button size="small" ghost icon={<CheckCircleOutlined />} style={{ color: '#52c41a', borderColor: '#52c41a' }}>可开标</Button>
            </Popconfirm>
          )}
          {isAgency && status === '' && (
            <Button size="small" danger ghost icon={<StopOutlined />} onClick={() => { setFailRow(row); setFailReason('') }}>提交流标</Button>
          )}
          {isOfficer && status === '' && (
            <Tooltip title="流标由代理机构提交（报名/供应商数量由代理机构掌握），提交后由经办人确认生效">
              <Button size="small" disabled icon={<StopOutlined />}>提交流标（由代理机构提交）</Button>
            </Tooltip>
          )}
        </>
      ) : undefined,
    }
  }

  // ── 筛选项：经办人 / 代理公司，取自当前数据 ──────────────────────
  const officerOptions = useMemo(
    () => Array.from(new Set(projects.map(p => p.officer).filter(Boolean)))
      .sort().map(v => ({ value: v as string, label: v as string })),
    [projects],
  )
  const agencyOptions = useMemo(
    () => Array.from(new Set(projects.map(p => p.agency_name).filter(Boolean)))
      .sort().map(v => ({ value: v as string, label: v as string })),
    [projects],
  )

  // 筛选 + 搜索 + 按开标时间升序（越早越靠前，无时间的排最后）
  const applyFilter = (list: BidProject[]) => {
    const kw = keyword.trim()
    return list
      .filter(p => !officerFilter || p.officer === officerFilter)
      .filter(p => !agencyFilter || p.agency_name === agencyFilter)
      .filter(p => !kw
        || (p.name || '').includes(kw)
        || (p.number || '').includes(kw)
        || (p.officer || '').includes(kw)
        || (p.agency_name || '').includes(kw))
      .sort((a, b) => {
        const ta = parseBidTime(a.ann_deadline || a.bid_time || '')?.getTime() ?? Infinity
        const tb = parseBidTime(b.ann_deadline || b.bid_time || '')?.getTime() ?? Infinity
        return ta - tb
      })
  }

  const activeProjects = applyFilter(projects.filter(p => (p.bucket || 'active') === 'active'))
  const openedProjects = applyFilter(projects.filter(p => p.bucket === 'opened'))
  const filteredCount = activeProjects.length + openedProjects.length
  const rawCount = projects.length

  // ── 日历模式：真正的周视图，周一~周日 7 列横向排开 ────────────────
  // 每个日格里一行一个项目，项目名称是主角（可换行看全），时间和状态做辅助信息。
  // 按开标日分组。待开标与已开标各自分组，同一套日历渲染给两边用。
  const groupByDay = (list: BidProject[]) => {
    const m = new Map<string, BidProject[]>()
    const noTime: BidProject[] = []
    for (const p of list) {
      const d = parseBidTime(p.ann_deadline || p.bid_time || '')
      if (!d) { noTime.push(p); continue }
      const k = dayKey(d)
      const arr = m.get(k)
      if (arr) arr.push(p)
      else m.set(k, [p])
    }
    return { map: m, noTime }
  }
  const activeByDay = useMemo(() => groupByDay(activeProjects), [activeProjects])
  const openedByDay = useMemo(() => groupByDay(openedProjects), [openedProjects])

  // offset 对应要铺的那些日子：周视图=周一~周日 7 天；月视图=整月并补齐首尾整周
  // month 返回当前月份（0-11），月视图里用来把补齐的上/下月日期画淡；周视图为 null
  const rangeOf = (offset: number): { days: Date[]; title: string; month: number | null } => {
    const base = new Date()
    base.setHours(0, 0, 0, 0)
    const fill = (start: Date, n: number) =>
      Array.from({ length: n }, (_, i) => {
        const d = new Date(start)
        d.setDate(start.getDate() + i)
        return d
      })
    if (span === 'week') {
      const dow = base.getDay()                  // 0=周日
      base.setDate(base.getDate() - (dow === 0 ? 6 : dow - 1) + offset * 7)
      const days = fill(base, 7)
      const title = `${days[0].getFullYear()}年${days[0].getMonth() + 1}月${days[0].getDate()}日`
        + ` — ${days[6].getMonth() + 1}月${days[6].getDate()}日`
      return { days, title, month: null }
    }
    const mStart = new Date(base.getFullYear(), base.getMonth() + offset, 1)
    const dim = new Date(mStart.getFullYear(), mStart.getMonth() + 1, 0).getDate()
    const lead = mStart.getDay() === 0 ? 6 : mStart.getDay() - 1   // 月初前面要补几天
    const gridStart = new Date(mStart)
    gridStart.setDate(1 - lead)
    const days = fill(gridStart, Math.ceil((lead + dim) / 7) * 7)
    return {
      days,
      title: `${mStart.getFullYear()}年${mStart.getMonth() + 1}月`,
      month: mStart.getMonth(),
    }
  }

  const todayKey = dayKey(new Date())

  /** 日历。跨度按 span 走（本月/本周），待开标与已开标共用，只是数据源与文案不同。 */
  const renderCalendar = (
    grouped: { map: Map<string, BidProject[]>; noTime: BidProject[] },
    offset: number,
    setOffset: (fn: (w: number) => number) => void,
    opts: { withActions: boolean; emptyWord: string },
  ) => {
    const { days, title, month } = rangeOf(offset)
    const unit = span === 'week' ? '周' : '月'
    const thisWord = span === 'week' ? '本周' : '本月'
    const keys = new Set(days.map(dayKey))
    let outsideCount = 0
    for (const [k, arr] of grouped.map) if (!keys.has(k)) outsideCount += arr.length
    return (
    <>
      <Space wrap style={{ marginBottom: 12 }}>
        <Button icon={<LeftOutlined />} onClick={() => setOffset(w => w - 1)}>
          {span === 'week' ? '上一周' : '上个月'}
        </Button>
        <Button onClick={() => setOffset(() => 0)} type={offset === 0 ? 'primary' : 'default'}>
          {thisWord}
        </Button>
        <Button onClick={() => setOffset(w => w + 1)}>
          {span === 'week' ? '下一周' : '下个月'}<RightOutlined />
        </Button>
        <span style={{ fontWeight: 600, fontSize: 15, marginLeft: 6 }}>{title}</span>
        {outsideCount > 0 && (
          <Tag color="orange">
            {thisWord}以外还有 {outsideCount} 个{opts.emptyWord}项目，可翻{unit}查看
          </Tag>
        )}
      </Space>

      <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
        {/* 月视图有好几行，顶上补一排星期表头，不然认不出是哪一列 */}
        {span === 'month' && !isMobile && (
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(7, minmax(150px, 1fr))',
            gap: 8, minWidth: 1100, marginBottom: 6,
          }}>
            {WEEK_HEAD.map(w => (
              <div key={w} style={{ textAlign: 'center', fontSize: 12, fontWeight: 600, color: '#5f6368' }}>
                {w}
              </div>
            ))}
          </div>
        )}
        <div style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr' : 'repeat(7, minmax(150px, 1fr))',
          gap: 8,
          minWidth: isMobile ? undefined : 1100,
        }}>
          {days.map(d => {
            const k = dayKey(d)
            const items = grouped.map.get(k) || []
            const isToday = k === todayKey
            const isWeekend = d.getDay() === 0 || d.getDay() === 6
            const outMonth = month !== null && d.getMonth() !== month   // 月视图里补齐的上/下月日期
            if (isMobile && !items.length) return null      // 手机上不占地方
            return (
              <div key={k} style={{
                border: isToday ? '2px solid #1a73e8' : '1px solid #d4d7dc',
                borderRadius: 8,
                background: isToday ? '#f0f6ff' : outMonth ? '#f7f8f9' : isWeekend ? '#fafafa' : '#fff',
                opacity: outMonth && items.length === 0 ? 0.55 : 1,
                minHeight: isMobile ? undefined : span === 'month' ? 118 : 150,
                display: 'flex', flexDirection: 'column',
              }}>
                <div style={{
                  padding: '6px 10px',
                  borderBottom: '1px solid #e8eaed',
                  background: isToday ? '#e3edff' : '#f5f6f8',
                  borderRadius: '6px 6px 0 0',
                  display: 'flex', alignItems: 'baseline', gap: 6,
                }}>
                  <span style={{ fontWeight: 700, fontSize: 13, color: isToday ? '#1a73e8' : '#3c4043' }}>
                    {WEEKDAYS[d.getDay()]}
                  </span>
                  <span style={{ fontSize: 12, color: '#5f6368' }}>
                    {d.getMonth() + 1}/{d.getDate()}
                  </span>
                  {isToday && <Tag color="blue" style={{ marginInlineEnd: 0, fontSize: 10, lineHeight: '16px', padding: '0 5px' }}>今天</Tag>}
                  <span style={{ flex: 1 }} />
                  {items.length > 0 && (
                    <span style={{ fontSize: 11, color: '#5f6368', fontWeight: 600 }}>{items.length}</span>
                  )}
                </div>
                <div style={{
                  padding: 6, display: 'flex', flexDirection: 'column', gap: 6, flex: 1,
                  maxHeight: !isMobile && span === 'month' ? 280 : undefined,
                  overflowY: !isMobile && span === 'month' ? 'auto' : undefined,
                }}>
                  {items.length === 0
                    ? <div style={{ color: '#c0c4c9', fontSize: 12, textAlign: 'center', paddingTop: 16 }}>—</div>
                    : items.map(p => {
                      const st = canOpenInfo(p)
                      const t = parseBidTime(p.ann_deadline || p.bid_time || '')
                      return (
                        <div
                          key={p.id}
                          onClick={() => setDayDetail(p)}
                          style={{
                            border: '1px solid #e0e3e7',
                            borderLeft: `3px solid ${ACCENT[st.color] || '#1a73e8'}`,
                            borderRadius: 6, padding: '6px 8px', cursor: 'pointer',
                            background: '#fff',
                          }}
                        >
                          {/* 项目名称是主角：允许换行，最多三行，看得清 */}
                          <div style={{
                            fontSize: 13, fontWeight: 600, color: '#202124', lineHeight: 1.35,
                            display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical',
                            overflow: 'hidden', wordBreak: 'break-all',
                          }}>
                            {p.name}
                          </div>
                          <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
                            <Tag color={st.color} style={{ marginInlineEnd: 0, fontSize: 10, lineHeight: '16px', padding: '0 5px' }}>
                              {st.text}
                            </Tag>
                            {t && (
                              <span style={{ fontSize: 11, color: '#d93025', fontWeight: 600 }}>
                                {String(t.getHours()).padStart(2, '0')}:{String(t.getMinutes()).padStart(2, '0')}
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: 11, color: '#5f6368', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {p.number}
                          </div>
                          <div style={{ fontSize: 11, color: '#5f6368', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {p.officer || '—'}｜{p.agency_name || '—'}
                          </div>
                        </div>
                      )
                    })}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {grouped.noTime.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontWeight: 600, marginBottom: 8, color: '#5f6368' }}>
            未排期（未设置开标时间）· {grouped.noTime.length} 个
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {grouped.noTime.map(p => (
              <RecordCard key={p.id} data={bidToCard(p, opts.withActions)} isMobile={isMobile} roomy={false} />
            ))}
          </div>
        </div>
      )}
    </>
    )
  }

  const toolbar = (
    <Space wrap style={{ marginBottom: 12 }}>
      <Segmented
        value={view}
        onChange={v => switchView(v as 'list' | 'calendar')}
        options={[
          { label: '列表', value: 'list', icon: <BarsOutlined /> },
          { label: '日历', value: 'calendar', icon: <CalendarOutlined /> },
        ]}
      />
      {view === 'calendar' && (
        <Segmented
          value={span}
          onChange={v => switchSpan(v as 'week' | 'month')}
          options={[
            { label: '本月', value: 'month' },
            { label: '本周', value: 'week' },
          ]}
        />
      )}
      <Select
        allowClear showSearch placeholder="按经办人筛选" style={{ width: 170 }}
        value={officerFilter} onChange={setOfficerFilter} options={officerOptions}
      />
      <Select
        allowClear showSearch placeholder="按代理公司筛选" style={{ width: 210 }}
        value={agencyFilter} onChange={setAgencyFilter} options={agencyOptions}
      />
      <Input.Search
        allowClear placeholder="搜索项目名称 / 编号 / 经办人 / 代理"
        style={{ width: 300 }}
        onChange={e => setKeyword(e.target.value)}
      />
      {(officerFilter || agencyFilter || keyword.trim()) && (
        <Tag color="blue">筛选后 {filteredCount} / 共 {rawCount}</Tag>
      )}
    </Space>
  )

  // 待办「去处理」跳转：高亮该项目（默认即「进行中」页签，行 rowKey=项目id）
  useFocusTarget(!loading && projects.length > 0, (id) => flashRow(id))

  return (
    <Card>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50', marginBottom: 8 }}>
        开标管理
      </div>
      {toolbar}
      <Tabs
        defaultActiveKey="active"
        items={[
          {
            key: 'active',
            label: `进行中（${activeProjects.length}）`,
            children: (
              <>
                <Alert
                  type="info" showIcon style={{ marginBottom: 16 }}
                  message={view === 'calendar'
                    ? '日历模式：默认铺本月，可在上方切成本周；同一天的项目归在一个大框里，框头显示星期与日期。'
                    : '列表模式：按开标时间升序排列，越早开标的排在越前面。可开标单击即生效；标记后开标当天仍留在此处，开标时间过后次日移入「已开标」。流标需代理机构提交原因、经办人确认后才结束本轮并开启下一次采购。'}
                />
                {view === 'calendar'
                  ? renderCalendar(activeByDay, offset, setOffset,
                      { withActions: true, emptyWord: '待开标' })
                  : (
                    <RecordCards
                      dataSource={activeProjects}
                      loading={loading}
                      emptyText="暂无正在挂网进行中的项目"
                      toCard={(r) => bidToCard(r, true)}
                    />
                  )}
              </>
            ),
          },
          {
            key: 'opened',
            label: `已开标（${openedProjects.length}）`,
            children: (
              <>
                <Alert
                  type="success" showIcon style={{ marginBottom: 16 }}
                  message={view === 'calendar'
                    ? '日历模式：按已开标日期铺排，默认本月。已开标的多在过去，用「上个月／上一周」继续往回翻。'
                    : '已标记可开标且开标时间已过的项目（归档查看），按开标时间升序排列。'}
                />
                {view === 'calendar'
                  ? renderCalendar(openedByDay, openedOffset, setOpenedOffset,
                      { withActions: false, emptyWord: '已开标' })
                  : (
                    <RecordCards
                      dataSource={openedProjects}
                      loading={loading}
                      emptyText="暂无已开标项目"
                      toCard={(r) => bidToCard(r, false)}
                    />
                  )}
              </>
            ),
          },
        ]}
      />

      {/* 日历里点一个项目 → 弹出完整卡片，操作按钮都在，不用切回列表 */}
      <Modal
        open={!!dayDetail}
        title="开标项目"
        footer={<Button onClick={() => setDayDetail(null)}>关闭</Button>}
        onCancel={() => setDayDetail(null)}
        width={720}
        destroyOnHidden
      >
        {dayDetail && (
          <RecordCard
            data={bidToCard(
              projects.find(p => p.id === dayDetail.id) || dayDetail, true)}
            isMobile={isMobile}
            roomy
          />
        )}
      </Modal>

      <Modal
        open={!!failRow}
        title="提交流标"
        okText="提交（待经办人确认）"
        okButtonProps={{ danger: true, loading: submitting }}
        cancelText="取消"
        onOk={submitFail}
        onCancel={() => { setFailRow(null); setFailReason('') }}
      >
        <p style={{ color: '#888', marginTop: 0 }}>
          项目：{failRow?.name}
        </p>
        <Input.TextArea
          rows={3}
          placeholder="请填写流标原因（如：有效供应商不足三家、报价均超预算等）"
          value={failReason}
          onChange={e => setFailReason(e.target.value)}
          maxLength={500}
          showCount
        />
        <p style={{ color: '#fa8c16', marginBottom: 0, marginTop: 8 }}>
          提交后状态变为「流标待确认」，需经办人确认后本轮才结束并开启下一次采购。
        </p>
      </Modal>
    </Card>
  )
}
