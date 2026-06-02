import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Table, Button, Space, Tag, Input, App, Typography, Tooltip, Popconfirm,
} from 'antd'
import { AuditOutlined, CheckCircleOutlined, PaperClipOutlined } from '@ant-design/icons'
import { getProjects, type Project } from '../services/project'
import { setDocConfirm } from '../services/procurementDoc'
import DocAttachmentsModal from '../components/DocAttachmentsModal'
import { useAuth } from '../hooks/useAuth'

const { Title, Text } = Typography

function ConfirmTag({ confirmed, by, at }: { confirmed: boolean; by: string; at: string }) {
  if (!confirmed) return <Tag>未确认</Tag>
  return (
    <Tooltip title={`${by || ''}${at ? ` · ${at.replace('T', ' ')}` : ''}`}>
      <Tag color="green" icon={<CheckCircleOutlined />}>已确认</Tag>
    </Tooltip>
  )
}

export default function ProcurementDemandConfirmPage() {
  const { message } = App.useApp()
  const { user } = useAuth()
  // 确认由采购人方审核，代理机构只能上传，不显示确认按钮
  const canConfirm = ['officer', 'assistant', 'leader'].includes(user?.role || '')
  const [loading, setLoading] = useState(true)
  const [projects, setProjects] = useState<Project[]>([])
  const [keyword, setKeyword] = useState('')
  const [attachProject, setAttachProject] = useState<Project | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    getProjects()
      .then(res => {
        const list = (res.data.data || []).filter(p => p.agency_code && !p.is_draft)
        setProjects(list)
      })
      .catch(() => message.error('加载项目失败'))
      .finally(() => setLoading(false))
  }, [message])
  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    const kw = keyword.trim()
    if (!kw) return projects
    return projects.filter(
      p =>
        (p.name || '').includes(kw) ||
        (p.number || '').includes(kw) ||
        (p.agency_name || '').includes(kw),
    )
  }, [projects, keyword])

  const toggleConfirm = async (p: Project) => {
    try {
      await setDocConfirm(p.id, 'demand', !p.demand_confirmed)
      message.success(p.demand_confirmed ? '已撤销采购需求确认' : '采购需求已确认')
      load()
    } catch {
      message.error('操作失败')
    }
  }

  const columns = [
    {
      title: '项目编号',
      dataIndex: 'number',
      width: 180,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    { title: '项目名称', dataIndex: 'name', ellipsis: true },
    {
      title: '代理机构',
      dataIndex: 'agency_name',
      width: 200,
      render: (v: string, r: Project) =>
        v ? <Tag color="blue">{v}</Tag> : <Tag>{r.agency_code}</Tag>,
    },
    {
      title: '采购需求确认',
      width: 110,
      render: (_: unknown, r: Project) => (
        <ConfirmTag confirmed={r.demand_confirmed} by={r.demand_confirmed_by} at={r.demand_confirmed_at} />
      ),
    },
    {
      title: '操作',
      width: 280,
      render: (_: unknown, r: Project) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<PaperClipOutlined />} onClick={() => setAttachProject(r)}>
            需求文件
          </Button>
          {canConfirm && (r.demand_confirmed ? (
            <Popconfirm title="撤销采购需求确认？" onConfirm={() => toggleConfirm(r)} okText="撤销" cancelText="取消">
              <Button type="link" size="small" danger>撤销确认</Button>
            </Popconfirm>
          ) : (
            <Button type="link" size="small" onClick={() => toggleConfirm(r)}>确认</Button>
          ))}
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <AuditOutlined /> 5.1 采购需求确认
          </Title>
          <Text type="secondary">
            经办人上传采购需求文件及附件，采购人核对后点击「确认」。
          </Text>
        </div>

        <Input.Search
          placeholder="搜索项目名称 / 编号 / 代理机构"
          allowClear
          style={{ maxWidth: 360 }}
          onChange={e => setKeyword(e.target.value)}
        />

        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={filtered}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          size="middle"
        />
      </Space>

      <DocAttachmentsModal
        project={attachProject}
        kind="demand"
        title="采购需求文件"
        locked={!!attachProject?.demand_confirmed}
        open={!!attachProject}
        onClose={() => setAttachProject(null)}
      />
    </Card>
  )
}
