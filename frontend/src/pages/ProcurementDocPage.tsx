import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Button, Space, Tag, Input, Modal, Form, InputNumber, App, Typography, Alert,
  Tooltip, Popconfirm, Tabs,
} from 'antd'
import { FileWordOutlined, FileTextOutlined, CheckCircleOutlined, PaperClipOutlined, ContactsOutlined, RobotOutlined } from '@ant-design/icons'
import { getProjects, type Project } from '../services/project'
import PendingOwnerTag from '../components/PendingOwnerTag'
import RdwebPushButton from '../components/RdwebPushButton'
import { autoPushText } from '../services/rdwebApproval'
import {
  generateBidCover, generateContentConfirm, setDocConfirm, saveDocContact,
  getDocConfirmations, type DemandConfirmation,
} from '../services/procurementDoc'
import DocAttachmentsModal from '../components/DocAttachmentsModal'
import AiReviewModal from '../components/AiReviewModal'
import AiGenerateDocModal from '../components/AiGenerateDocModal'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import FilePreviewModal from '../components/FilePreviewModal'
import { useAuth } from '../hooks/useAuth'
import { cnOrdinal } from '../utils/ordinal'
import { useFocusTarget, flashRow } from '../hooks/useFocusRow'
import ProjectListToolbar, { useProjectListFilter, PROJECT_ACCESSORS } from '../components/ProjectListToolbar'

const { Title, Text } = Typography

function todayCN() {
  const d = new Date()
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

// ISO 时间 → 中文「YYYY年M月D日」（用于把封面/确认表日期默认成确认采购文件当天）
function dateCN(iso?: string) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

function ConfirmTag({ confirmed, by, at }: { confirmed: boolean; by: string; at: string }) {
  if (!confirmed) return <Tag>未确认</Tag>
  return (
    <Tooltip title={`${by || ''}${at ? ` · ${at.replace('T', ' ')}` : ''}`}>
      <Tag color="green" icon={<CheckCircleOutlined />}>已确认</Tag>
    </Tooltip>
  )
}

export default function ProcurementDocPage() {
  const { message } = App.useApp()
  const { user } = useAuth()
  // 采购文件确认由采购人方审核，代理机构只能上传，不显示确认按钮
  const canConfirm = ['officer', 'assistant', 'leader'].includes(user?.role || '')
  const [loading, setLoading] = useState(true)
  const [projects, setProjects] = useState<Project[]>([])
  const [confirmations, setConfirmations] = useState<DemandConfirmation[]>([])
  // 已确认历史里「查看采购文件」：round=确认轮次（标题用），filesRound=文件实际所属轮次（取文件用）
  const [viewDoc, setViewDoc] = useState<{ project: Project; round: number; filesRound: number } | null>(null)
  // 内容确认表在线预览（点「内容确认表」即生成并预览，弹窗内可下载/打印）
  const [ccPreview, setCcPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })

  const [modalOpen, setModalOpen] = useState(false)
  const [current, setCurrent] = useState<Project | null>(null)
  const [generating, setGenerating] = useState(false)
  const [genId, setGenId] = useState<number | null>(null)
  const [attachProject, setAttachProject] = useState<Project | null>(null)
  const [aiProject, setAiProject] = useState<Project | null>(null)
  const [aiGenProject, setAiGenProject] = useState<Project | null>(null)
  const [form] = Form.useForm()
  // 内容确认表所需的联系人信息（代理机构填写）
  const [contactProject, setContactProject] = useState<Project | null>(null)
  const [contactSaving, setContactSaving] = useState(false)
  const [contactForm] = Form.useForm()
  const [activeTab, setActiveTab] = useState<'pending' | 'confirmed' | 'archived'>('pending')

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([getProjects(), getDocConfirmations()])
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

  // 未确认/已归档来自项目（按当前 stage 过滤）；已确认来自轮次确认历史（每次一行）。
  const grouped = useMemo(() => {
    const pending: Project[] = [], archived: Project[] = []
    for (const p of filtered) {
      if (p.status === '已归档') { archived.push(p); continue }
      if (p.current_stage === 'doc_confirm') pending.push(p)
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

  const openModal = (p: Project) => {
    setCurrent(p)
    form.setFieldsValue({
      agency_name: p.agency_name || '',
      round_number: p.round || 1,
      // 编制日期默认 = 经办人确认采购文件当天（未确认时回退今天）
      compile_date: dateCN(p.doc_confirmed_at) || todayCN(),
    })
    setModalOpen(true)
  }

  const handleGenerate = async () => {
    if (!current) return
    const values = await form.validateFields()
    setGenerating(true)
    try {
      const res = await generateBidCover(current.id, values)
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `招标文件封面_${current.number || current.name}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('招标文件封面已生成，正在下载')
      setModalOpen(false)
    } catch {
      message.error('生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const handleContentConfirm = async (p: Project) => {
    setGenId(p.id)
    try {
      const res = await generateContentConfirm(p.id, {})
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const url = URL.createObjectURL(blob)
      // 改为在线预览（弹窗内可下载/打印）；旧 url 在关闭时释放
      setCcPreview(prev => { if (prev.url) URL.revokeObjectURL(prev.url); return { open: true, url, name: `内容确认表_${p.number || p.name}.docx` } })
    } catch (err: unknown) {
      // 后端可能返回「尚未确认」等具体原因（blob 响应需手动解析）
      let msg = '生成失败'
      const resp = (err as { response?: { data?: unknown } })?.response?.data
      if (resp instanceof Blob) {
        try { msg = JSON.parse(await resp.text())?.error || msg } catch { /* ignore */ }
      } else if (resp && typeof resp === 'object' && 'error' in resp) {
        msg = String((resp as { error?: string }).error || msg)
      }
      message.error(msg)
    } finally {
      setGenId(null)
    }
  }

  const openContactModal = (p: Project) => {
    setContactProject(p)
    contactForm.setFieldsValue({
      contact_person: p.doc_agency_contact || '',
      contact_phone: p.doc_agency_phone || '',
    })
  }

  const handleSaveContact = async () => {
    if (!contactProject) return
    const values = await contactForm.validateFields()
    setContactSaving(true)
    try {
      await saveDocContact(contactProject.id, values)
      message.success('联系人信息已保存')
      setContactProject(null)
      load()
    } catch {
      message.error('保存失败')
    } finally {
      setContactSaving(false)
    }
  }

  const toggleConfirm = async (p: Project) => {
    try {
      const resp = await setDocConfirm(p.id, 'doc', !p.doc_confirmed)
      message.success(p.doc_confirmed ? '已撤销采购文件确认' : '采购文件已确认')
      // 确认即自动把采购文件确认函推去 rd-web 盖章，结果在卡片按钮上看
      const tip = autoPushText((resp.data as any)?.rdweb_push)
      if (tip) message.info(tip)
      load()
    } catch {
      message.error('操作失败')
    }
  }

  const projToCard = (r: Project): RecordCardData => ({
    key: r.id,
    accent: r.doc_confirmed ? '#34a853' : '#1a73e8',
    title: r.name,
    subtitle: r.number || '无编号',
    statusText: r.doc_confirmed ? '已确认' : '未确认',
    statusColor: r.doc_confirmed ? 'green' : 'orange',
    tags: r.agency_name
      ? <Tag color="blue" style={{ marginInlineEnd: 0 }}>{r.agency_name}</Tag>
      : (r.agency_code ? <Tag style={{ marginInlineEnd: 0 }}>{r.agency_code}</Tag> : undefined),
    fields: [
      { label: '采购文件确认', value: <ConfirmTag confirmed={r.doc_confirmed} by={r.doc_confirmed_by} at={r.doc_confirmed_at} /> },
      { label: '当前处理人', value: <PendingOwnerTag p={r.pending} compact /> },
    ],
    actions: (
      <>
        <Button size="small" icon={<PaperClipOutlined />} onClick={() => setAttachProject(r)}>采购文件</Button>
        <Button size="small" icon={<FileWordOutlined />} onClick={() => openModal(r)}>招标文件封面</Button>
        <Button size="small" icon={<ContactsOutlined />} onClick={() => openContactModal(r)}>联系人</Button>
        <Button size="small" icon={<RobotOutlined />} onClick={() => setAiProject(r)}>AI 编制建议</Button>
        {!r.doc_confirmed && (
          <Button size="small" type="primary" ghost icon={<RobotOutlined />}
            onClick={() => setAiGenProject(r)}>
            AI 生成采购文件
          </Button>
        )}
        <Tooltip title={r.doc_confirmed ? '' : '需经办人确认采购文件后才能生成'}>
          <Button size="small" icon={<FileWordOutlined />} loading={genId === r.id} disabled={!r.doc_confirmed} onClick={() => handleContentConfirm(r)}>
            内容确认表
          </Button>
        </Tooltip>
        {r.doc_confirmed && <RdwebPushButton projectId={r.id} kind="doc_confirm" />}
        {canConfirm && (r.doc_confirmed ? (
          <Popconfirm title="撤销采购文件确认？" onConfirm={() => toggleConfirm(r)} okText="撤销" cancelText="取消">
            <Button size="small" danger>撤销确认</Button>
          </Popconfirm>
        ) : (
          <Button size="small" type="primary" ghost onClick={() => toggleConfirm(r)}>确认</Button>
        ))}
      </>
    ),
  })

  // 已确认历史：打开「文件实际所属轮次」的采购文件（本轮无修改时回落到上一轮）
  const openViewDoc = (c: DemandConfirmation) => {
    const proj = projects.find(p => p.id === c.project_id)
      || ({ id: c.project_id, name: c.project_name } as Project)
    setViewDoc({ project: proj, round: c.round_number, filesRound: c.files_round })
  }

  // 撤回某次文件确认 → 该轮退回「未确认」，可重新修改后再次确认（仅最新轮、未发公告等后续时可用）
  const revokeConfirm = async (c: DemandConfirmation) => {
    try {
      await setDocConfirm(c.project_id, 'doc', false)
      message.success('已撤回，请在「未确认」修改采购文件后重新确认')
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
        {c.files_inherited && (
          <Tooltip title={`本次未修改，沿用第${cnOrdinal(c.files_round)}次的采购文件`}>
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
        <Button size="small" icon={<PaperClipOutlined />} onClick={() => openViewDoc(c)}>
          查看采购文件{c.files.length ? `（${c.files.length}）` : ''}
        </Button>
        {canConfirm && c.revocable && (
          <Popconfirm title="撤回本次文件确认？" description="该项目将退回「未确认」，可重新修改采购文件后再次确认。"
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
            <FileTextOutlined /> 5.2 采购文件确认
          </Title>
          <Text type="secondary">
            代理机构上传采购文件及附件，经办人审核确认后方可编制采购公告并挂网；确认后系统对每份文件留存 SHA256。
          </Text>
        </div>

        <Alert
          type="info"
          showIcon
          message="流程：代理机构上传采购文件并填写「联系人」→ 经办人「确认」采购文件 → 确认后即可生成《内容确认表》（自动填入文件 SHA256 哈希值与代理联系人）。"
        />

        <ProjectListToolbar f={listFilter} />

        <Tabs
          activeKey={activeTab}
          onChange={k => setActiveTab(k as 'pending' | 'confirmed' | 'archived')}
          items={[
            { key: 'pending',   label: `未确认 (${grouped.pending.length})` },
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
            emptyText={activeTab === 'pending' ? '暂无未确认项目' : '暂无已归档项目'}
            toCard={projToCard}
          />
        )}
      </Space>

      <Modal
        title={`生成招标文件封面${current ? ` — ${current.name}` : ''}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleGenerate}
        okText="生成并下载"
        confirmLoading={generating}
        destroyOnHidden
        width={520}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item
            label="代理机构全称"
            name="agency_name"
            rules={[{ required: true, message: '请填写代理机构全称' }]}
          >
            <Input placeholder="如：四川中锦招标代理有限公司" />
          </Form.Item>
          <Form.Item label="第几次" name="round_number">
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="编制日期" name="compile_date">
            <Input placeholder="如：2026年5月29日" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`内容确认表联系人${contactProject ? ` — ${contactProject.name}` : ''}`}
        open={!!contactProject}
        onCancel={() => setContactProject(null)}
        onOk={handleSaveContact}
        okText="保存"
        confirmLoading={contactSaving}
        destroyOnHidden
        width={480}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="由代理机构填写，将自动填入《内容确认表》的「代理机构联系人及联系方式」一栏。"
        />
        <Form form={contactForm} layout="vertical">
          <Form.Item
            label="联系人"
            name="contact_person"
            rules={[{ required: true, message: '请填写联系人' }]}
          >
            <Input placeholder="如：张三" />
          </Form.Item>
          <Form.Item
            label="联系方式"
            name="contact_phone"
            rules={[{ required: true, message: '请填写联系方式' }]}
          >
            <Input placeholder="如：138xxxxxxxx" />
          </Form.Item>
        </Form>
      </Modal>

      <DocAttachmentsModal
        project={attachProject}
        kind="doc"
        title="采购文件"
        showHash
        locked={!!attachProject?.doc_confirmed}
        open={!!attachProject}
        onClose={() => setAttachProject(null)}
      />

      {/* 已确认历史：只读查看「那一次确认」的采购文件（本轮无修改则取沿用的上一轮） */}
      <DocAttachmentsModal
        project={viewDoc?.project ?? null}
        kind="doc"
        title={`采购文件（第${cnOrdinal(viewDoc?.round ?? 1)}次确认）`}
        showHash
        roundNumber={viewDoc?.filesRound}
        locked
        open={!!viewDoc}
        onClose={() => setViewDoc(null)}
      />

      <AiReviewModal
        project={aiProject}
        open={!!aiProject}
        onClose={() => setAiProject(null)}
      />

      <AiGenerateDocModal
        project={aiGenProject}
        open={!!aiGenProject}
        onClose={() => setAiGenProject(null)}
        onGenerated={load}
      />

      {/* 内容确认表在线预览（弹窗内含下载/打印） */}
      <FilePreviewModal
        open={ccPreview.open}
        url={ccPreview.url}
        filename={ccPreview.name}
        showPrint
        compactDocx
        onClose={() => setCcPreview(p => { if (p.url) URL.revokeObjectURL(p.url); return { open: false, url: '', name: '' } })}
      />
    </Card>
  )
}
