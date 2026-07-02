import { useEffect, useState } from 'react'
import { Button, Tag, Card, App, Tooltip, Alert, Popconfirm, Modal, Input, Tabs } from 'antd'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import {
  FileDoneOutlined, CheckCircleOutlined, StopOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import { getBidList, markCanOpen, proposeBidFail, confirmBidFail, revokeBidFail } from '../services/bid'
import type { Project } from '../services/project'
import { useAuth } from '../hooks/useAuth'
import { useNavigate } from 'react-router-dom'
import { useFocusTarget, flashRow } from '../hooks/useFocusRow'

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

// 解析中文日期时间，判断开标时间是否临近/已过
function getBidTimeStatus(bidTime: string): { color: string; tip: string } {
  if (!bidTime) return { color: '#ccc', tip: '未设置开标时间' }
  const m = bidTime.match(/(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})[：:](\d{2})/)
  let d: Date
  if (m) {
    d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5])
  } else {
    d = new Date(bidTime)
    if (isNaN(d.getTime())) return { color: '#1677ff', tip: bidTime }
  }
  const diff = d.getTime() - Date.now()
  if (diff < 0)        return { color: '#aaa',    tip: '已过开标时间' }
  if (diff < 86400000) return { color: '#ff4d4f', tip: '24小时内开标' }
  if (diff < 259200000)return { color: '#fa8c16', tip: '3天内开标' }
  return { color: '#52c41a', tip: '开标时间正常' }
}

export default function BidManagePage() {
  const [projects, setProjects] = useState<BidProject[]>([])
  const [loading, setLoading] = useState(true)
  const { user } = useAuth()
  const { message } = App.useApp()
  const navigate = useNavigate()

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
        : <Tag color="orange" style={{ marginInlineEnd: 0 }}>第{'一二三四五'[rn - 1]}次</Tag>,
      fields: [
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

  const activeProjects = projects.filter(p => (p.bucket || 'active') === 'active')
  const openedProjects = projects.filter(p => p.bucket === 'opened')

  // 待办「去处理」跳转：高亮该项目（默认即「进行中」页签，行 rowKey=项目id）
  useFocusTarget(!loading && projects.length > 0, (id) => flashRow(id))

  return (
    <Card>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50', marginBottom: 8 }}>
        开标管理
      </div>
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
                  message="显示已发布公告、本轮尚未判定开标结果的项目（不受开标时间限制，截止后仍可操作）。可开标单击即生效；标记后开标当天仍留在此处，开标时间过后次日移入「已开标」。流标需代理机构提交原因、经办人确认后才结束本轮并开启下一次采购。"
                />
                <RecordCards
                  dataSource={activeProjects}
                  loading={loading}
                  emptyText="暂无正在挂网进行中的项目"
                  toCard={(r) => bidToCard(r, true)}
                />
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
                  message="已标记可开标且开标时间已过的项目（归档查看）。"
                />
                <RecordCards
                  dataSource={openedProjects}
                  loading={loading}
                  emptyText="暂无已开标项目"
                  toCard={(r) => bidToCard(r, false)}
                />
              </>
            ),
          },
        ]}
      />

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
