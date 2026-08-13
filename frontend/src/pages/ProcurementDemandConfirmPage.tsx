import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Button, Space, Tag, App, Typography, Tooltip, Popconfirm,
  Modal, InputNumber, Alert, Tabs,
} from 'antd'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import { AuditOutlined, CheckCircleOutlined, PaperClipOutlined, AppstoreOutlined } from '@ant-design/icons'
import { getProjects, type Project } from '../services/project'
import PendingOwnerTag from '../components/PendingOwnerTag'
import {
  setDocConfirm, setPackageCount, getDemandConfirmations, type DemandConfirmation,
} from '../services/procurementDoc'
import DocAttachmentsModal from '../components/DocAttachmentsModal'
import { useAuth } from '../hooks/useAuth'
import { cnOrdinal } from '../utils/ordinal'
import { useFocusTarget, flashRow } from '../hooks/useFocusRow'
import ProjectListToolbar, { useProjectListFilter, PROJECT_ACCESSORS } from '../components/ProjectListToolbar'

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
  const [confirmations, setConfirmations] = useState<DemandConfirmation[]>([])
  const [attachProject, setAttachProject] = useState<Project | null>(null)
  // 已确认历史里「查看需求文件」：round=确认轮次（标题用），filesRound=文件实际所属轮次（取文件用）
  const [viewDemand, setViewDemand] = useState<{ project: Project; round: number; filesRound: number } | null>(null)
  // 包数量弹窗：mode='confirm' 确认时一并设置；mode='set' 仅设置/调整
  const [pkgModalProject, setPkgModalProject] = useState<Project | null>(null)
  const [pkgMode, setPkgMode] = useState<'confirm' | 'set'>('confirm')
  const [pkgCount, setPkgCount] = useState<number>(1)
  const [confirming, setConfirming] = useState(false)
  const [activeTab, setActiveTab] = useState<'pending' | 'confirmed' | 'archived'>('pending')

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([getProjects(), getDemandConfirmations()])
      .then(([projRes, confRes]) => {
        const list = (projRes.data.data || []).filter(p => p.agency_code && !p.is_draft)
        setProjects(list)
        setConfirmations(confRes.data.data || [])
      })
      .catch(() => message.error('加载项目失败'))
      .finally(() => setLoading(false))
  }, [message])
  useEffect(() => { load() }, [load])

  const listFilter = useProjectListFilter(projects, PROJECT_ACCESSORS)
  const filtered = listFilter.filtered
  const keyword = listFilter.kw

  // 待确认/已归档来自项目（按当前 stage 过滤）；已确认来自轮次确认历史（每次一行）。
  const grouped = useMemo(() => {
    const pending: Project[] = [], archived: Project[] = []
    for (const p of filtered) {
      if (p.status === '已归档') { archived.push(p); continue }
      if (p.current_stage === 'demand_confirm') pending.push(p)
    }
    return { pending, archived }
  }, [filtered])

  // 待办「去处理」跳转：定位到待确认页签并高亮该项目
  useFocusTarget(!loading && projects.length > 0, (id) => {
    setActiveTab('pending')
    flashRow(id)
  })

  // 已确认历史按同样的关键词过滤
  const filteredConfirmations = useMemo(() => {
    const kw = keyword.trim()
    if (!kw) return confirmations
    return confirmations.filter(
      c =>
        (c.project_name || '').includes(kw) ||
        (c.number || '').includes(kw) ||
        (c.agency_name || '').includes(kw),
    )
  }, [confirmations, keyword])

  // 撤销，或包已定义后的再次确认：直接切换
  const toggleConfirm = async (p: Project) => {
    try {
      await setDocConfirm(p.id, 'demand', !p.demand_confirmed)
      message.success(p.demand_confirmed ? '已撤销采购需求确认' : '采购需求已确认')
      load()
    } catch {
      message.error('操作失败')
    }
  }

  // 点击「确认」：包尚未定义则先弹窗录入包数量；否则直接确认
  const onClickConfirm = (p: Project) => {
    if (!p.package_count) {
      setPkgCount(1)
      setPkgMode('confirm')
      setPkgModalProject(p)
    } else {
      toggleConfirm(p)
    }
  }

  // 「分包设置」：单独调整包数量（不触发确认）
  const openPkgSetting = (p: Project) => {
    setPkgCount(p.package_count || 1)
    setPkgMode('set')
    setPkgModalProject(p)
  }

  const handlePkgModalOk = async () => {
    if (!pkgModalProject) return
    setConfirming(true)
    try {
      if (pkgMode === 'confirm') {
        await setDocConfirm(pkgModalProject.id, 'demand', true, pkgCount)
        message.success(`采购需求已确认，本项目分 ${pkgCount} 个包`)
      } else {
        await setPackageCount(pkgModalProject.id, pkgCount)
        message.success(`已设置为 ${pkgCount} 个包`)
      }
      setPkgModalProject(null)
      load()
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '操作失败')
    } finally {
      setConfirming(false)
    }
  }

  const projToCard = (r: Project): RecordCardData => ({
    key: r.id,
    accent: r.demand_confirmed ? '#34a853' : '#1a73e8',
    title: r.name,
    subtitle: r.number || '无编号',
    statusText: r.demand_confirmed ? '已确认' : '待确认',
    statusColor: r.demand_confirmed ? 'green' : 'orange',
    tags: (
      <>
        {r.agency_name ? <Tag color="blue" style={{ marginInlineEnd: 0 }}>{r.agency_name}</Tag> : (r.agency_code ? <Tag style={{ marginInlineEnd: 0 }}>{r.agency_code}</Tag> : null)}
        {r.package_count ? <Tag color="geekblue" style={{ marginInlineEnd: 0 }}>{r.package_count} 个包</Tag> : null}
        {r.current_round ? <Tag style={{ marginInlineEnd: 0 }}>第 {r.current_round} 次</Tag> : null}
      </>
    ),
    fields: [
      { label: '采购需求确认', value: <ConfirmTag confirmed={r.demand_confirmed} by={r.demand_confirmed_by} at={r.demand_confirmed_at} /> },
      { label: '当前处理人', value: <PendingOwnerTag p={r.pending} compact /> },
    ],
    actions: (
      <>
        <Button size="small" icon={<PaperClipOutlined />} onClick={() => setAttachProject(r)}>需求文件</Button>
        {canConfirm && (
          <Button size="small" icon={<AppstoreOutlined />} onClick={() => openPkgSetting(r)}>分包设置</Button>
        )}
        {canConfirm && (r.demand_confirmed ? (
          <Popconfirm title="撤销采购需求确认？" onConfirm={() => toggleConfirm(r)} okText="撤销" cancelText="取消">
            <Button size="small" danger>撤销确认</Button>
          </Popconfirm>
        ) : (
          <Button size="small" type="primary" ghost onClick={() => onClickConfirm(r)}>确认</Button>
        ))}
      </>
    ),
  })

  // 已确认历史：打开「文件实际所属轮次」的需求文件（本轮无修改时回落到上一轮）
  const openViewDemand = (c: DemandConfirmation) => {
    const proj = projects.find(p => p.id === c.project_id)
      || ({ id: c.project_id, name: c.project_name } as Project)
    setViewDemand({ project: proj, round: c.round_number, filesRound: c.files_round })
  }

  // 撤回某次需求确认 → 该轮退回「待确认」，可重新修改后再次确认（仅最新轮、未进入后续步骤时可用）
  const revokeConfirm = async (c: DemandConfirmation) => {
    try {
      await setDocConfirm(c.project_id, 'demand', false)
      message.success('已撤回，请在「待确认」修改需求后重新确认')
      load()
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '撤回失败')
    }
  }

  const confToCard = (c: DemandConfirmation): RecordCardData => ({
    key: `${c.project_id}-${c.round_number}`,
    accent: '#34a853',
    title: `${c.project_name}（第${cnOrdinal(c.round_number)}次）`,
    subtitle: c.number || '无编号',
    statusText: '已确认',
    statusColor: 'green',
    tags: (
      <>
        {c.agency_name && <Tag color="blue" style={{ marginInlineEnd: 0 }}>{c.agency_name}</Tag>}
        {c.package_count ? <Tag color="geekblue" style={{ marginInlineEnd: 0 }}>{c.package_count} 个包</Tag> : null}
        {c.files_inherited && (
          <Tooltip title={`本次未修改，沿用第${cnOrdinal(c.files_round)}次的需求`}>
            <Tag color="orange" style={{ marginInlineEnd: 0 }}>沿用</Tag>
          </Tooltip>
        )}
      </>
    ),
    fields: [
      { label: '确认人', value: c.confirmed_by },
      { label: '确认时间', value: c.confirmed_at ? c.confirmed_at.replace('T', ' ') : '' },
    ],
    actions: (
      <>
        <Button size="small" icon={<PaperClipOutlined />} onClick={() => openViewDemand(c)}>
          查看需求文件{c.files.length ? `（${c.files.length}）` : ''}
        </Button>
        {canConfirm && c.revocable && (
          <Popconfirm title="撤回本次需求确认？" description="该项目将退回「待确认」，可重新修改需求后再次确认。"
            onConfirm={() => revokeConfirm(c)} okText="撤回" cancelText="取消">
            <Button size="small" danger>撤回修改</Button>
          </Popconfirm>
        )}
      </>
    ),
  })

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

        <ProjectListToolbar f={listFilter} />

        <Tabs
          activeKey={activeTab}
          onChange={k => setActiveTab(k as 'pending' | 'confirmed' | 'archived')}
          items={[
            { key: 'pending',   label: `待确认 (${grouped.pending.length})` },
            { key: 'confirmed', label: `已确认 (${filteredConfirmations.length})` },
            { key: 'archived',  label: `已归档 (${grouped.archived.length})` },
          ]}
        />

        {activeTab === 'confirmed' ? (
          <RecordCards dataSource={filteredConfirmations} loading={loading} emptyText="暂无已确认记录" toCard={confToCard} />
        ) : (
          <RecordCards
            dataSource={activeTab === 'pending' ? grouped.pending : grouped.archived}
            loading={loading}
            emptyText={activeTab === 'pending' ? '暂无待确认项目' : '暂无已归档项目'}
            toCard={projToCard}
          />
        )}
      </Space>

      <Modal
        title={`${pkgMode === 'confirm' ? '确认采购需求' : '分包设置'} — ${pkgModalProject?.name || ''}`}
        open={!!pkgModalProject}
        onCancel={() => setPkgModalProject(null)}
        onOk={handlePkgModalOk}
        okText={pkgMode === 'confirm' ? '确认' : '保存'}
        confirmLoading={confirming}
        destroyOnHidden
        width={460}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="请确定本项目的分包数量。有包中标/签约、或本轮采购结果已确认后不可再调整；未中标前（含已流标进入下一轮）仍可在「项目流程」里改。后续按包分轮采购，请谨慎填写。"
        />
        <Space>
          <AppstoreOutlined />
          <span>包数量：</span>
          <InputNumber min={1} max={50} value={pkgCount} onChange={v => setPkgCount(Number(v) || 1)} />
          <Text type="secondary">个（不分包填 1）</Text>
        </Space>
      </Modal>

      <DocAttachmentsModal
        project={attachProject}
        kind="demand"
        title="采购需求文件"
        locked={!!attachProject?.demand_confirmed}
        open={!!attachProject}
        onClose={() => setAttachProject(null)}
      />

      {/* 已确认历史：只读查看「那一次确认」的需求文件（本轮无修改则取沿用的上一轮） */}
      <DocAttachmentsModal
        project={viewDemand?.project ?? null}
        kind="demand"
        title={`采购需求文件（第${cnOrdinal(viewDemand?.round ?? 1)}次确认）`}
        roundNumber={viewDemand?.filesRound}
        locked
        open={!!viewDemand}
        onClose={() => setViewDemand(null)}
      />
    </Card>
  )
}
