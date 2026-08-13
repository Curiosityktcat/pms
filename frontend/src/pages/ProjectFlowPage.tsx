import { useEffect, useState } from 'react'
import { Button, Tag, Popconfirm, Tabs, Input, Select, App, Card, Segmented, Modal, InputNumber, Alert, Space, Typography } from 'antd'
import {
  PlusOutlined, SearchOutlined, RollbackOutlined,
  SortAscendingOutlined, SortDescendingOutlined, AppstoreOutlined,
} from '@ant-design/icons'
import WebAnnPanel from '../components/WebAnnPanel'
import { getWebAnnCounts } from '../services/webAnnouncement'
import PendingOwnerTag from '../components/PendingOwnerTag'
import { useNavigate } from 'react-router-dom'
import { getProjects, deleteProject, restoreProject } from '../services/project'
import { setPackageCount } from '../services/procurementDoc'
import ProjectProgressModal from '../components/ProjectProgressModal'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import type { Project } from '../services/project'
import { useAuth } from '../hooks/useAuth'

const STATUS_DONE = '已归档'
const METHODS = ['院内议价', '院内询价', '院内竞选', '院内单一来源采购', '医用耗材紧急采购', '政府采购']

export default function ProjectFlowPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [deleted, setDeleted] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'ongoing' | 'done' | 'deleted'>('ongoing')
  const [search, setSearch] = useState('')
  const [filterYear, setFilterYear] = useState<string | undefined>()
  const [filterMethod, setFilterMethod] = useState<string | undefined>()
  const [sortBy, setSortBy] = useState<'created' | 'number'>('created')
  const [sortAsc, setSortAsc] = useState(false)   // 默认倒序（新的/编号大的在前）
  const [progressId, setProgressId] = useState<number | null>(null)
  // 分包设置：项目全流程都可改（后端把关：有包已中标/签约、或本轮采购结果已确认才拒）
  const [pkgProject, setPkgProject] = useState<Project | null>(null)
  const [pkgCount, setPkgCount] = useState(1)
  const [pkgSaving, setPkgSaving] = useState(false)
  // 官网公告条数一次性取回，避免每张卡片各发一次请求
  const [annCounts, setAnnCounts] = useState<Record<string, number>>({})
  const [annProject, setAnnProject] = useState<Project | null>(null)
  useEffect(() => {
    getWebAnnCounts().then(r => setAnnCounts(r.data.data || {})).catch(() => {})
  }, [])
  const { user } = useAuth()
  const navigate = useNavigate()
  const { message } = App.useApp()

  const load = async () => {
    setLoading(true)
    try {
      const [res, resD] = await Promise.all([
        getProjects(false),
        getProjects(true),
      ])
      setProjects(res.data.data)
      setDeleted(resD.data.data)
    } catch {
      message.error('加载项目列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openPkgSetting = (p: Project) => {
    setPkgCount(p.package_count || 1)
    setPkgProject(p)
  }

  const handlePkgOk = async () => {
    if (!pkgProject) return
    setPkgSaving(true)
    try {
      const res = await setPackageCount(pkgProject.id, pkgCount)
      const warn = (res.data as { data?: { warn?: string } })?.data?.warn
      message.success('已设置为 ' + pkgCount + ' 个包')
      if (warn) message.warning(warn, 6)
      setPkgProject(null)
      load()
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '设置失败')
    } finally {
      setPkgSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteProject(id)
      message.success('已删除，可在「已删除」标签中恢复')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '删除失败')
    }
  }

  const handleRestore = async (id: number) => {
    try {
      await restoreProject(id)
      message.success('项目已恢复')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.error || '恢复失败')
    }
  }

  // 收集所有已有年度用于下拉
  const yearOptions = Array.from(
    new Set(projects.map(p => p.year).filter(Boolean))
  ).sort().reverse()

  // 过滤 + 排序（两种排序键都默认倒序，可按钮切正/倒序）
  const applyFilter = (list: Project[]) => {
    const q = search.trim().toLowerCase()
    const out = list.filter(p => {
      const matchSearch = !q ||
        p.name.toLowerCase().includes(q) ||
        (p.number || '').toLowerCase().includes(q)
      const matchYear = !filterYear || p.year === filterYear
      const matchMethod = !filterMethod || p.method === filterMethod
      return matchSearch && matchYear && matchMethod
    })
    return out.sort((a, b) => {
      const r = sortBy === 'number'
        ? (a.number || '').localeCompare(b.number || '')
        : (a.created_at || '').localeCompare(b.created_at || '')
      return sortAsc ? r : -r
    })
  }

  const ongoing = projects.filter(p => p.status !== STATUS_DONE)
  const done = projects.filter(p => p.status === STATUS_DONE)

  const filteredOngoing = applyFilter(ongoing)
  const filteredDone = applyFilter(done)
  const filteredDeleted = applyFilter(deleted)

  const canEdit = user?.role === 'officer'
  // 分包设置：采购人方（经办人/助理/负责人）可用，代理机构不可（后端同口径）
  const canSetPkg = ['officer', 'assistant', 'leader'].includes(user?.role || '')
  const canCreate = user?.role === 'officer'


  const currentData = tab === 'ongoing' ? filteredOngoing
    : tab === 'done' ? filteredDone
    : filteredDeleted

  const projectToCard = (p: Project): RecordCardData => {
    const isDone = p.status === STATUS_DONE
    const isDeleted = tab === 'deleted'
    const amount = p.amount && p.amount > 0 ? `${p.amount.toFixed(0)} 元` : '招单价'
    return {
      key: p.id,
      accent: isDeleted ? '#d93025' : isDone ? '#9aa0a6' : '#1a73e8',
      title: p.name,
      onTitleClick: () => navigate(`/project/${p.id}`),
      subtitle: `${p.number || '无编号'}${p.year ? ` · ${p.year}年` : ''}`,
      statusText: isDeleted ? '已删除' : p.status,
      statusColor: isDeleted ? 'error' : isDone ? 'default' : 'blue',
      tags: (
        <>
          {p.is_draft && <Tag color="orange" style={{ marginInlineEnd: 0 }}>草稿</Tag>}
          {p.category && <Tag bordered={false} color="geekblue" style={{ marginInlineEnd: 0 }}>{p.category}</Tag>}
          {p.contract_rdweb_submitted && <Tag bordered={false} color="green" style={{ marginInlineEnd: 0 }}>已推合同签</Tag>}
          {p.agency_rdweb_submitted && <Tag bordered={false} color="green" style={{ marginInlineEnd: 0 }}>已推代理协议签</Tag>}
        </>
      ),
      fields: [
        { label: '方式', value: p.method },
        { label: '预算', value: amount },
        { label: '代理', value: p.agency_name },
        { label: '经办人', value: p.officer },
        { label: '当前处理人', value: <PendingOwnerTag p={p.pending} compact /> },
        { label: isDeleted ? '删除时间' : '开标', value: isDeleted ? (p.deleted_at ? p.deleted_at.replace('T', ' ') : '') : p.bid_time },
        ...(annCounts[String(p.id)] ? [{
          label: '官网公告',
          value: (
            <a onClick={e => { e.stopPropagation(); setAnnProject(p) }}>
              {annCounts[String(p.id)]} 条
            </a>
          ),
        }] : []),
      ],
      actions: isDeleted
        ? (canEdit ? (
            <Popconfirm title="确定恢复该项目？" onConfirm={() => handleRestore(p.id)} okText="恢复" cancelText="取消">
              <Button size="small" icon={<RollbackOutlined />}>恢复</Button>
            </Popconfirm>
          ) : null)
        : canEdit ? (
            <>
              <Button size="small" disabled={p.is_draft} onClick={() => setProgressId(p.id)}>进展</Button>
              <Button size="small" type="primary" ghost onClick={() => navigate(`/project/${p.id}`)}>编辑</Button>
              {canSetPkg && !p.is_draft && !!p.agency_code && (
                <Button size="small" icon={<AppstoreOutlined />} onClick={() => openPkgSetting(p)}>
                  分包{p.package_count ? `(${p.package_count})` : ''}
                </Button>
              )}
              <Popconfirm title="删除后可在「已删除」中恢复" onConfirm={() => handleDelete(p.id)} okText="删除" okButtonProps={{ danger: true }} cancelText="取消">
                <Button size="small" danger>删除</Button>
              </Popconfirm>
            </>
          ) : (
            <>
              <Button size="small" disabled={p.is_draft} onClick={() => setProgressId(p.id)}>进展</Button>
              <Button size="small" type="primary" ghost onClick={() => navigate(`/project/${p.id}`)}>查看</Button>
              {canSetPkg && !p.is_draft && !!p.agency_code && (
                <Button size="small" icon={<AppstoreOutlined />} onClick={() => openPkgSetting(p)}>
                  分包{p.package_count ? `(${p.package_count})` : ''}
                </Button>
              )}
            </>
          ),
    }
  }

  return (
    <Card>
      {/* 顶部工具栏 */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12, gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50' }}>项目流程</span>
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索项目名称或编号"
          allowClear
          style={{ width: 220 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select
          placeholder="采购年度"
          allowClear
          style={{ width: 110 }}
          value={filterYear}
          onChange={setFilterYear}
          options={yearOptions.map(y => ({ value: y, label: y }))}
        />
        <Select
          placeholder="采购方式"
          allowClear
          style={{ width: 160 }}
          value={filterMethod}
          onChange={setFilterMethod}
          options={METHODS.map(m => ({ value: m, label: m }))}
        />
        <Segmented
          value={sortBy}
          onChange={v => setSortBy(v as 'created' | 'number')}
          options={[
            { value: 'created', label: '按新增时间' },
            { value: 'number', label: '按项目编号' },
          ]}
        />
        <Button
          icon={sortAsc ? <SortAscendingOutlined /> : <SortDescendingOutlined />}
          onClick={() => setSortAsc(v => !v)}
        >
          {sortAsc ? '正序' : '倒序'}
        </Button>
        {canCreate && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            style={{ marginLeft: 'auto' }}
            onClick={() => navigate('/new')}
          >
            项目立项
          </Button>
        )}
      </div>

      {/* 标签页 */}
      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as 'ongoing' | 'done' | 'deleted')}
        items={[
          { key: 'ongoing', label: `进行中（${ongoing.length}）` },
          { key: 'done', label: `已归档（${done.length}）` },
          {
            key: 'deleted',
            label: (
              <span style={{ color: deleted.length > 0 ? '#ff4d4f' : undefined }}>
                已删除{deleted.length > 0 ? `（${deleted.length}）` : ''}
              </span>
            ),
          },
        ]}
      />

      <RecordCards
        dataSource={currentData}
        loading={loading}
        emptyText={tab === 'deleted' ? '没有已删除的项目' : '暂无项目'}
        toCard={projectToCard}
      />

      <Modal
        title={`分包设置 — ${pkgProject?.name || ''}`}
        open={!!pkgProject}
        onCancel={() => setPkgProject(null)}
        onOk={handlePkgOk}
        okText="保存"
        confirmLoading={pkgSaving}
        destroyOnHidden
        width={480}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="包一旦有中标/签约，或本轮采购结果已确认，就不能再改。未中标前（含已流标进入下一轮）可以调整，新增的包会自动补挂到各轮次。"
        />
        <Space>
          <AppstoreOutlined />
          <span>包数量：</span>
          <InputNumber min={1} max={50} value={pkgCount} onChange={v => setPkgCount(Number(v) || 1)} />
          <Typography.Text type="secondary">个（不分包填 1）</Typography.Text>
        </Space>
      </Modal>

      <ProjectProgressModal
        projectId={progressId}
        open={progressId !== null}
        onClose={() => setProgressId(null)}
      />

      <WebAnnPanel
        projectId={annProject?.id ?? null}
        projectName={annProject?.name}
        open={annProject !== null}
        onClose={() => setAnnProject(null)}
      />
    </Card>
  )
}
