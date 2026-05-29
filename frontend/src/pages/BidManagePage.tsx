import { useEffect, useState } from 'react'
import { Table, Button, Tag, Space, Card, Typography, App, Tooltip, Alert } from 'antd'
import {
  FileDoneOutlined, CheckCircleOutlined, StopOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import { getBidList, markBid } from '../services/bid'
import type { Project } from '../services/project'
import { useAuth } from '../hooks/useAuth'
import { useNavigate } from 'react-router-dom'

// 扩展 Project 类型，包含开标管理附加字段
interface BidProject extends Project {
  ann_id?: number
  ann_round_number?: number
  ann_deadline?: string
}

const { Text } = Typography

const CAN_OPEN_TAG: Record<string, { color: string; label: string }> = {
  '可开标': { color: 'green', label: '可开标' },
  '流标':   { color: 'red',   label: '流标' },
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

  const canMark = user?.role === 'officer' || user?.role === 'agency'
  const canAuthLetter = user?.role === 'officer' || user?.role === 'agency'

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
      width: 185,
      render: (val: string) => <Text code style={{ fontSize: 12 }}>{val}</Text>,
    },
    {
      title: '项目名称',
      dataIndex: 'name',
      ellipsis: true,
    },
    {
      title: '代理机构',
      dataIndex: 'agency_name',
      width: 150,
      ellipsis: true,
      render: (val: string) => val || <Text type="secondary">—</Text>,
    },
    {
      title: '开标次数',
      dataIndex: 'ann_round_number',
      width: 90,
      render: (val: number) => {
        if (!val || val === 1) return <Tag color="blue">第一次</Tag>
        return <Tag color="orange">第{'一二三四五'[val - 1]}次</Tag>
      },
    },
    {
      title: '开标时间（响应截止）',
      dataIndex: 'ann_deadline',
      width: 195,
      render: (val: string, row: BidProject) => {
        const deadline = val || row.bid_time
        if (!deadline) return <Text type="secondary">—</Text>
        const { color, tip } = getBidTimeStatus(deadline)
        return (
          <Tooltip title={tip}>
            <span style={{ color, fontWeight: 500 }}>
              <ClockCircleOutlined style={{ marginRight: 4 }} />
              {deadline}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: '能否开标',
      dataIndex: 'can_open',
      width: 90,
      render: (val: string) => {
        const t = CAN_OPEN_TAG[val]
        return t ? <Tag color={t.color}>{t.label}</Tag> : <Tag color="default">未判定</Tag>
      },
    },
    {
      title: '操作',
      width: 240,
      render: (_: unknown, row: BidProject) => (
        <Space size={4} wrap>
          {/* 授权函：携带项目ID和轮次跳转 */}
          {canAuthLetter && (
            <Button
              size="small"
              icon={<FileDoneOutlined />}
              type="primary"
              onClick={() => navigate(
                `/auth-letter?project_id=${row.id}&round=${row.ann_round_number || 1}&bid_time=${encodeURIComponent(row.ann_deadline || row.bid_time || '')}`
              )}
            >
              生成授权函
            </Button>
          )}
          {/* 标记能否开标 */}
          {canMark && (
            <>
              <Button
                size="small"
                icon={<CheckCircleOutlined />}
                style={{ color: '#52c41a', borderColor: '#52c41a' }}
                ghost
                onClick={() => handleMark(row.id, '可开标')}
              >
                可开标
              </Button>
              <Button
                size="small"
                icon={<StopOutlined />}
                danger
                ghost
                onClick={() => handleMark(row.id, '流标')}
              >
                流标
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50', marginBottom: 8 }}>
        开标管理
      </div>
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="只显示已发布公告且开标时间未到的项目。点击「生成授权函」直接跳转并自动导入项目信息。"
      />
      <Table
        rowKey="id"
        columns={columns}
        dataSource={projects}
        loading={loading}
        size="small"
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
        locale={{ emptyText: '暂无正在挂网进行中的项目' }}
      />
    </Card>
  )
}
