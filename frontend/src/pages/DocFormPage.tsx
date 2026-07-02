/**
 * 在线文档编制页：列出项目 → 选一个进入 DocFormEditor 文档式编辑。
 * 路由 /doc-form/:tplkey （procurement_demand 采购需求 / procurement_doc 采购文件）。
 */
import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Table, Button, Input, App, Tag, Space, Typography, Progress } from 'antd'
import { EditOutlined, SearchOutlined, FileTextOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getProjects, type Project } from '../services/project'
import { getDocStatusMap, getDocTemplate, type DocStatus } from '../services/docForm'
import DocFormEditor from '../components/DocFormEditor'

const { Text } = Typography

const TITLES: Record<string, string> = {
  procurement_demand: '采购需求在线编制',
  procurement_doc: '采购文件在线编制',
  internal_demand: '院内采购需求在线编制',
}

export default function DocFormPage() {
  const { tplkey = 'procurement_demand' } = useParams()
  const { message } = App.useApp()
  const [projects, setProjects] = useState<Project[]>([])
  const [statusMap, setStatusMap] = useState<Record<string, DocStatus>>({})
  const [tplName, setTplName] = useState('')
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [pr, sm, tp] = await Promise.all([
        getProjects(false), getDocStatusMap(tplkey), getDocTemplate(tplkey),
      ])
      setProjects(pr.data.data.filter(p => !p.is_draft))
      setStatusMap(sm.data.data)
      setTplName(tp.data.data.name)
    } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [tplkey, message])

  useEffect(() => { if (selected === null) load() }, [selected, load])

  if (selected !== null) {
    return (
      <div style={{ margin: -24 }}>
        <DocFormEditor projectId={selected} templateKey={tplkey} onBack={() => setSelected(null)} />
      </div>
    )
  }

  const kw = keyword.trim()
  const rows = projects.filter(p => !kw || (p.name || '').includes(kw) || (p.number || '').includes(kw))

  const columns: ColumnsType<Project> = [
    { title: '项目名称', dataIndex: 'name', ellipsis: true },
    { title: '项目编号', dataIndex: 'number', width: 170, render: v => v || <Text type="secondary">—</Text> },
    { title: '经办人', dataIndex: 'officer', width: 90, render: v => v || '—' },
    {
      title: '编制状态', key: 'st', width: 220,
      render: (_: unknown, r) => {
        const s = statusMap[String(r.id)]
        if (!s) return <Tag>未开始</Tag>
        return (
          <Space>
            <Tag color={s.status === '已完成' ? 'green' : 'orange'}>{s.status}</Tag>
            <Progress percent={s.total ? Math.round(s.filled / s.total * 100) : 0}
              size="small" style={{ width: 90 }} />
          </Space>
        )
      },
    },
    {
      title: '操作', key: 'act', width: 120,
      render: (_: unknown, r) => (
        <Button type="primary" size="small" icon={<EditOutlined />} onClick={() => setSelected(r.id)}>
          在线编辑
        </Button>
      ),
    },
  ]

  return (
    <Card
      title={<span style={{ fontWeight: 700, fontSize: 16 }}><FileTextOutlined /> {TITLES[tplkey] || tplName}</span>}
      extra={
        <Input allowClear prefix={<SearchOutlined />} placeholder="搜索项目名称/编号"
          style={{ width: 280 }} value={keyword} onChange={e => setKeyword(e.target.value)} />
      }
    >
      <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={rows}
        pagination={{ pageSize: 15, showTotal: t => `共 ${t} 个项目` }} />
    </Card>
  )
}
