import { useEffect, useRef, useState } from 'react'
import { Table, Button, Card, Typography, Space, Select, Tag, App } from 'antd'
import { ReloadOutlined, LinkOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getBoardData, setBoardSupervisor, refreshBoard, getBoardStatus,
} from '../services/bidBoard'
import type { BidBoardProject } from '../services/bidBoard'

const { Text } = Typography

function fmt(iso: string | null): string {
  if (!iso) return '尚无数据'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

// 剩余时间文案
function daysLeft(iso: string): string {
  if (!iso) return ''
  const ms = new Date(iso).getTime() - Date.now()
  if (isNaN(ms)) return ''
  const d = Math.floor(ms / 86400000)
  const h = Math.floor((ms % 86400000) / 3600000)
  if (d > 0) return `还剩${d}天`
  if (h > 0) return `还剩${h}小时`
  return '即将截止'
}

export default function BidBoardPage() {
  const { message } = App.useApp()
  const [items, setItems] = useState<BidBoardProject[]>([])
  const [supervisors, setSupervisors] = useState<string[]>([])
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const pollRef = useRef<number | null>(null)

  const load = async () => {
    try {
      const { data } = await getBoardData()
      setItems(data.items || [])
      setSupervisors(data.supervisors || [])
      setUpdatedAt(data.updated_at)
    } catch {
      message.error('加载看板数据失败')
    } finally {
      setLoading(false)
    }
  }

  // 首次加载 + 每60秒自动刷新看板数据（不触发抓取）
  useEffect(() => {
    load()
    const t = window.setInterval(load, 60000)
    return () => {
      window.clearInterval(t)
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 轮询抓取状态，结束后重新加载数据
  const pollStatus = () => {
    if (pollRef.current) window.clearInterval(pollRef.current)
    pollRef.current = window.setInterval(async () => {
      try {
        const { data } = await getBoardStatus()
        if (!data.running) {
          if (pollRef.current) window.clearInterval(pollRef.current)
          setRefreshing(false)
          message.success(data.last_msg || '抓取完成')
          load()
        }
      } catch {
        if (pollRef.current) window.clearInterval(pollRef.current)
        setRefreshing(false)
      }
    }, 3000)
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const { data } = await refreshBoard()
      if (data.status === 'started') {
        message.info('已开始抓取，约需几分钟…')
        pollStatus()
      } else if (data.status === 'running') {
        message.info('已有抓取任务进行中…')
        pollStatus()
      } else if (data.status === 'cooldown') {
        message.warning(`距上次抓取仅 ${data.mins_ago} 分钟，请 ${data.wait_mins} 分钟后再刷新`)
        setRefreshing(false)
      }
    } catch {
      message.error('刷新失败')
      setRefreshing(false)
    }
  }

  const handleSupervisor = async (number: string, name: string) => {
    try {
      await setBoardSupervisor(number, name)
      setItems(prev => prev.map(it => it.number === number ? { ...it, supervisor: name } : it))
      message.success('已保存监督人员')
    } catch {
      message.error('保存失败')
    }
  }

  const columns: ColumnsType<BidBoardProject> = [
    {
      title: '#', dataIndex: 'idx', width: 50,
      render: (_v, _r, i) => i + 1,
    },
    {
      title: '采购项目名称', dataIndex: 'name',
      render: (v: string) => <Text strong>{v || '—'}</Text>,
    },
    { title: '项目编号', dataIndex: 'number', width: 170 },
    { title: '代理公司', dataIndex: 'agency', width: 200, render: (v: string) => v || '—' },
    {
      title: '开标时间', dataIndex: 'deadline', width: 170,
      render: (v: string) => <Text type="danger" strong>{v || '—'}</Text>,
    },
    {
      title: '剩余', dataIndex: 'deadline_iso', width: 110,
      render: (iso: string) => {
        const ms = iso ? new Date(iso).getTime() - Date.now() : Infinity
        const urgent = ms < 3 * 86400000
        return <Tag color={urgent ? 'red' : 'default'}>{daysLeft(iso)}</Tag>
      },
    },
    {
      title: '监督人员', dataIndex: 'supervisor', width: 150,
      render: (v: string, r) => (
        <Select
          size="small"
          style={{ width: 130 }}
          placeholder="--未指定--"
          allowClear
          showSearch
          value={v || undefined}
          onChange={(val) => handleSupervisor(r.number, val || '')}
          options={supervisors.map(n => ({ label: n, value: n }))}
        />
      ),
    },
    {
      title: '链接', dataIndex: 'url', width: 70,
      render: (url: string) => url
        ? <a href={url} target="_blank" rel="noreferrer"><LinkOutlined /> 原文</a>
        : '—',
    },
  ]

  return (
    <Card
      title="🏥 未来14天开标看板"
      extra={
        <Space size="middle">
          <Text type="secondary">数据更新于：{fmt(updatedAt)}</Text>
          <Text type="secondary">共 {items.length} 条</Text>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={refreshing}
            onClick={handleRefresh}
          >
            手动刷新
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="number"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={false}
        locale={{ emptyText: '未来14天内暂无开标项目' }}
        onRow={(r) => {
          const ms = r.deadline_iso ? new Date(r.deadline_iso).getTime() - Date.now() : Infinity
          return ms < 3 * 86400000 ? { style: { background: '#fff3f3' } } : {}
        }}
      />
    </Card>
  )
}
