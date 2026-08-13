/**
 * 6.2 调研公告 / 6.4 单一来源公示
 *
 * 两类公告的流程完全一样（草稿→待确认→已确认，可驳回、可传附件、可出 Word），
 * 只有中间那段正文字段不同，所以做成一个组件按 kind 参数化，避免两份几乎一样的代码。
 *
 * 体例来源：
 *   调研公告 —— 照医院官网已发布的市场调研公告（云算力、法律顾问两份实样）
 *   单一来源公示 —— 官网无先例，按财政部令第74号第38条的法定必备内容组织，
 *                   专家论证意见必须含姓名/工作单位/职称，公示期不少于5个工作日
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Button, Space, Input, App, Typography, Popconfirm,
  Modal, Form, Select, Tabs, Alert, Upload, List, DatePicker,
} from 'antd'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import {
  PlusOutlined, DeleteOutlined, FileWordOutlined, UploadOutlined,
  PaperClipOutlined, DownloadOutlined, MinusCircleOutlined, StopOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getAnnouncements, getEligibleProjects, createAnnouncement, updateAnnouncement,
  deleteAnnouncement, submitAnnouncement, confirmAnnouncement, revokeAnnouncement,
  rejectAnnouncement, generateAnnouncementWord, listFiles, deleteFile, downloadFileUrl,
  type Announcement, type AnnProject, type AnnAttachment,
} from '../services/announcement'
import { useAuth } from '../hooks/useAuth'
import { parseCnDate, fmtCnDay } from '../utils/cnDate'
import { smartUploadAbs } from '../services/upload'

const { Text, Title } = Typography

type Kind = 'survey' | 'single_source'

const META: Record<Kind, { no: string; name: string; desc: string }> = {
  survey: {
    no: '6.2', name: '调研公告',
    desc: '采购需求论证阶段发布，向市场了解技术方案、供应商资格与价格区间。调研结果与采购结果无必然联系，公告正文会自动带上这句说明。',
  },
  single_source: {
    no: '6.4', name: '单一来源公示',
    desc: '拟采用单一来源方式采购时发布。必备内容依《政府采购非招标采购方式管理办法》（财政部令第74号）第38条：拟采购说明、采用单一来源的原因、唯一供应商、专业人员论证意见（含姓名/工作单位/职称）、公示期（不少于5个工作日）、异议接收方式。',
  },
}

const SURVEY_NOTE_DEFAULT =
  '1.本次调研仅用于采购需求论证，医院不保证采纳任何单位提供的方案。\n' +
  '2.参与单位应保证所提交资料真实有效，弄虚作假的取消其参与资格。\n' +
  '3.本次调研结果与本项目的采购结果无任何必然联系。\n' +
  '4.本公告自发布之日起生效，医院保留对本公告的最终解释权。'

export default function SurveySingleSourcePage({ kind }: { kind: Kind }) {
  const { message } = App.useApp()
  const { user } = useAuth()
  const isAgency = user?.role === 'agency'
  const canConfirm = ['officer', 'assistant', 'leader'].includes(user?.role || '')
  const meta = META[kind]

  const [loading, setLoading] = useState(true)
  const [rows, setRows] = useState<Announcement[]>([])
  const [keyword, setKeyword] = useState('')
  const [activeTab, setActiveTab] = useState<'待确认' | '已驳回' | '草稿' | '已确认' | 'all'>('待确认')

  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Announcement | null>(null)
  const [projects, setProjects] = useState<AnnProject[]>([])
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()
  const [files, setFiles] = useState<AnnAttachment[]>([])
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [rejectRow, setRejectRow] = useState<Announcement | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    getAnnouncements(kind)
      .then(res => setRows(res.data.data || []))
      .catch(() => message.error(`加载${meta.name}失败`))
      .finally(() => setLoading(false))
  }, [message, kind, meta.name])
  useEffect(() => { load() }, [load])

  // 切换 6.2/6.4 时把上一类的残留状态清掉，避免串页
  useEffect(() => {
    setEditOpen(false); setEditing(null); setPendingFiles([]); setActiveTab('待确认')
  }, [kind])

  const filtered = useMemo(() => {
    let list = rows
    if (activeTab !== 'all') list = list.filter(r => (r.status || '草稿') === activeTab)
    const kw = keyword.trim()
    if (!kw) return list
    return list.filter(r =>
      (r.project_name || '').includes(kw) || (r.project_number || '').includes(kw))
  }, [rows, activeTab, keyword])

  const loadFiles = useCallback(async (id: number) => {
    try { setFiles((await listFiles(id)).data.data || []) } catch { /* ignore */ }
  }, [])

  const openCreate = async () => {
    setEditing(null); setFiles([]); setPendingFiles([])
    form.resetFields()
    form.setFieldsValue(kind === 'survey'
      ? { survey_note: SURVEY_NOTE_DEFAULT }
      : { experts: [{ name: '', org: '', title: '', opinion: '' }] })
    try {
      const res = await getEligibleProjects(kind)
      setProjects(res.data.data || [])
      if (!(res.data.data || []).length) {
        message.warning(kind === 'single_source'
          ? '暂无单一来源类项目可发公示'
          : '暂无可发调研公告的项目')
      }
    } catch { message.error('加载项目失败') }
    setEditOpen(true)
  }

  const openEdit = (r: Announcement) => {
    setEditing(r); setPendingFiles([])
    let experts: Record<string, string>[] = []
    try { experts = JSON.parse(r.ss_experts_json || '[]') } catch { experts = [] }
    if (!experts.length) experts = [{ name: '', org: '', title: '', opinion: '' }]
    form.setFieldsValue({
      project_id: r.project_id,
      project_intro: r.project_intro || '',
      agency_contact: r.agency_contact || '',
      agency_contact_phone: r.agency_contact_phone || '',
      agency_email: r.agency_email || '',
      survey_content: r.survey_content || '',
      survey_qualification: r.survey_qualification || '',
      survey_quote_req: r.survey_quote_req || '',
      survey_materials: r.survey_materials || '',
      survey_deadline: r.survey_deadline || '',
      survey_submit_way: r.survey_submit_way || '',
      survey_note: r.survey_note || SURVEY_NOTE_DEFAULT,
      ss_goods_desc: r.ss_goods_desc || '',
      ss_reason: r.ss_reason || '',
      ss_supplier_name: r.ss_supplier_name || '',
      ss_supplier_addr: r.ss_supplier_addr || '',
      // 存库是中文串（2026年8月1日），dayjs 直接吃中文会得到 Invalid Date，
      // 必须走 parseCnDate；解析不出来就留空，不要塞个坏值给控件
      ss_publicity: (() => {
        const a = parseCnDate(r.ss_publicity_start)
        const b = parseCnDate(r.ss_publicity_end)
        return a && b ? [a, b] : undefined
      })(),
      ss_objection_dept: r.ss_objection_dept || '',
      ss_objection_contact: r.ss_objection_contact || '',
      ss_objection_phone: r.ss_objection_phone || '',
      ss_objection_addr: r.ss_objection_addr || '',
      experts,
    })
    loadFiles(r.id)
    setEditOpen(true)
  }

  const uploadPending = async (id: number) => {
    let ok = 0
    for (const f of pendingFiles) {
      try {
        await smartUploadAbs(`/api/announcements/${id}/files`, f)
        ok += 1
      } catch { message.error(`附件「${f.name}」上传失败`) }
    }
    return ok
  }

  const handleSave = async (thenSubmit = false) => {
    const v = await form.validateFields()
    const payload: Record<string, unknown> = {
      ann_type: kind,
      project_id: v.project_id,
      round_number: 1,
      project_intro: (v.project_intro || '').trim(),
      agency_contact: (v.agency_contact || '').trim(),
      agency_contact_phone: (v.agency_contact_phone || '').trim(),
      agency_email: (v.agency_email || '').trim(),
    }
    if (kind === 'survey') {
      Object.assign(payload, {
        survey_content: (v.survey_content || '').trim(),
        survey_qualification: (v.survey_qualification || '').trim(),
        survey_quote_req: (v.survey_quote_req || '').trim(),
        survey_materials: (v.survey_materials || '').trim(),
        survey_deadline: (v.survey_deadline || '').trim(),
        survey_submit_way: (v.survey_submit_way || '').trim(),
        survey_note: (v.survey_note || SURVEY_NOTE_DEFAULT).trim(),
      })
    } else {
      const rng = v.ss_publicity as [dayjs.Dayjs, dayjs.Dayjs] | undefined
      Object.assign(payload, {
        ss_goods_desc: (v.ss_goods_desc || '').trim(),
        ss_reason: (v.ss_reason || '').trim(),
        ss_supplier_name: (v.ss_supplier_name || '').trim(),
        ss_supplier_addr: (v.ss_supplier_addr || '').trim(),
        // fmtCnDay 只接受合法 dayjs，非法值一律存空串——
        // 否则 format() 会返回字面量 "Invalid Date" 并被当成日期存进库
        ss_publicity_start: rng?.[0]?.isValid() ? fmtCnDay(rng[0]) : '',
        ss_publicity_end: rng?.[1]?.isValid() ? fmtCnDay(rng[1]) : '',
        ss_objection_dept: (v.ss_objection_dept || '').trim(),
        ss_objection_contact: (v.ss_objection_contact || '').trim(),
        ss_objection_phone: (v.ss_objection_phone || '').trim(),
        ss_objection_addr: (v.ss_objection_addr || '').trim(),
        ss_experts_json: JSON.stringify(
          (v.experts || []).filter((e: Record<string, string>) => (e?.name || '').trim())),
      })
    }

    setSaving(true)
    try {
      let id: number
      if (editing) {
        await updateAnnouncement(editing.id, payload as never)
        id = editing.id
      } else {
        const res = await createAnnouncement(payload as never)
        id = res.data.data.id
      }
      const n = pendingFiles.length ? await uploadPending(id) : 0
      setPendingFiles([])
      if (thenSubmit) {
        await submitAnnouncement(id)
        message.success(`已提交确认${n ? `（含 ${n} 个附件）` : ''}`)
        setEditOpen(false)
      } else {
        message.success(`已保存${n ? `，附件 ${n} 个已上传` : ''}`)
        setEditOpen(false)
      }
      load()
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '保存失败')
    } finally { setSaving(false) }
  }

  const runAction = async (fn: () => Promise<{ data: { message?: string } }>) => {
    try {
      const res = await fn()
      message.success(res.data.message || '操作成功')
      load()
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '操作失败')
    }
  }

  const doReject = async () => {
    if (!rejectRow) return
    if (!rejectReason.trim()) { message.warning('请填写驳回原因'); return }
    await runAction(() => rejectAnnouncement(rejectRow.id, rejectReason.trim()))
    setRejectRow(null); setRejectReason('')
  }

  const downloadWord = async (r: Announcement) => {
    try {
      const res = await generateAnnouncementWord(r.id)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `${meta.name}_${r.project_number || r.project_name}.docx`
      a.click()
      URL.revokeObjectURL(url)
    } catch { message.error('生成失败') }
  }

  const customUpload = async (options: { file: unknown; onSuccess?: (d: unknown) => void; onError?: (e: Error) => void }) => {
    if (!editing) return
    const { file, onSuccess, onError } = options
    setUploading(true)
    try {
      const res = await smartUploadAbs(`/api/announcements/${editing.id}/files`, file as File)
      onSuccess?.(res.data); message.success('上传成功'); loadFiles(editing.id)
    } catch (err: unknown) {
      onError?.(err as Error); message.error('上传失败')
    } finally { setUploading(false) }
  }

  const STATUS_META: Record<string, { text: string; color: string; accent: string }> = {
    '已确认': { text: '已发布', color: 'green', accent: '#34a853' },
    '待确认': { text: '待确认', color: 'orange', accent: '#f9ab00' },
    '已驳回': { text: '已驳回', color: 'red', accent: '#d93025' },
    '草稿': { text: '草稿', color: 'default', accent: '#9aa0a6' },
  }

  const toCard = (r: Announcement): RecordCardData => {
    const m = STATUS_META[r.status || '草稿'] || STATUS_META['草稿']
    return {
      key: r.id,
      accent: m.accent,
      title: `${r.project_name || '—'}（${meta.name}）`,
      subtitle: r.project_number || '无编号',
      statusText: m.text,
      statusColor: m.color,
      fields: [
        { label: '发布时间', value: r.confirmed_at ? r.confirmed_at.replace('T', ' ').slice(0, 16) : '' },
        ...(kind === 'survey' && r.survey_deadline
          ? [{ label: '提交截止', value: r.survey_deadline }] : []),
        ...(kind === 'single_source' && r.ss_supplier_name
          ? [{ label: '唯一供应商', value: r.ss_supplier_name }] : []),
        ...(kind === 'single_source'
            && r.ss_publicity_start && !r.ss_publicity_start.includes('Invalid')
          ? [{ label: '公示期', value: `${r.ss_publicity_start} 至 ${r.ss_publicity_end || ''}` }] : []),
        ...(r.status === '已驳回' && r.reject_reason
          ? [{
            label: `驳回原因${(r.reject_count || 0) > 1 ? `（第${r.reject_count}次）` : ''}`,
            value: <Text type="danger">{r.reject_reason}</Text>,
          }] : []),
      ],
      actions: (
        <>
          {r.status !== '已确认' && <Button size="small" onClick={() => openEdit(r)}>编辑</Button>}
          <Button size="small" icon={<FileWordOutlined />} onClick={() => downloadWord(r)}>Word</Button>
          {(r.status === '草稿' || r.status === '已驳回') && (
            <Button size="small" type="primary" ghost
              onClick={() => runAction(() => submitAnnouncement(r.id))}>
              {r.status === '已驳回' ? '修改后重新提交' : '提交确认'}
            </Button>
          )}
          {r.status === '待确认' && canConfirm && (
            <>
              <Popconfirm title={`确认并发布该${meta.name}？发布后将在公告首页公开展示。`}
                okText="发布" cancelText="取消"
                onConfirm={() => runAction(() => confirmAnnouncement(r.id))}>
                <Button size="small" type="primary">确认发布</Button>
              </Popconfirm>
              <Button size="small" danger icon={<StopOutlined />}
                onClick={() => { setRejectRow(r); setRejectReason('') }}>驳回</Button>
            </>
          )}
          {r.status === '已确认' && canConfirm && (
            <Popconfirm title="撤回后将从公告首页下架并恢复为草稿。" okText="撤回" cancelText="取消"
              onConfirm={() => runAction(() => revokeAnnouncement(r.id))}>
              <Button size="small" danger>撤回</Button>
            </Popconfirm>
          )}
          {r.status !== '已确认' && (
            <Popconfirm title="删除？" okText="删除" cancelText="取消"
              onConfirm={() => runAction(() => deleteAnnouncement(r.id))}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </>
      ),
    }
  }

  const tabCount = (s: string) => rows.filter(r => (r.status || '草稿') === s).length

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>{meta.no} {meta.name}</Title>
          <Text type="secondary">{meta.desc}</Text>
        </div>

        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建{meta.name}
          </Button>
          <Input.Search allowClear placeholder="搜索项目名称 / 编号"
            style={{ width: 300 }} onChange={e => setKeyword(e.target.value)} />
        </Space>

        <Tabs
          activeKey={activeTab}
          onChange={k => setActiveTab(k as typeof activeTab)}
          items={[
            { key: '待确认', label: `待确认 (${tabCount('待确认')})` },
            { key: '已驳回', label: `已驳回 (${tabCount('已驳回')})` },
            { key: '草稿', label: `草稿 (${tabCount('草稿')})` },
            { key: '已确认', label: `已发布 (${tabCount('已确认')})` },
            { key: 'all', label: `全部 (${rows.length})` },
          ]}
        />

        <RecordCards dataSource={filtered} loading={loading}
          emptyText={`暂无${meta.name}`} toCard={toCard} />
      </Space>

      <Modal
        title={editing ? `编辑${meta.name} — ${editing.project_name || ''}` : `新建${meta.name}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        width={820}
        destroyOnHidden
        maskClosable={false}
        footer={[
          <Button key="c" onClick={() => setEditOpen(false)}>取消</Button>,
          <Button key="s" loading={saving} onClick={() => handleSave(false)}>仅保存</Button>,
          <Button key="t" type="primary" loading={saving} onClick={() => handleSave(true)}>
            保存并提交确认
          </Button>,
        ]}
      >
        <Alert type="info" showIcon style={{ marginBottom: 12 }} message={meta.desc} />
        <Form form={form} layout="vertical">
          <Form.Item label="项目" name="project_id" rules={[{ required: true, message: '请选择项目' }]}>
            <Select showSearch optionFilterProp="label" disabled={!!editing}
              placeholder="选择项目"
              options={(editing
                ? [{ value: editing.project_id, label: `${editing.project_number || ''} ${editing.project_name || ''}` }]
                : projects.map(p => ({ value: p.id, label: `${p.number || ''} ${p.name}` })))} />
          </Form.Item>

          <Form.Item label="项目概况（选填，如服务期限、预算说明）" name="project_intro">
            <Input.TextArea rows={2} maxLength={1000} />
          </Form.Item>

          {kind === 'survey' ? (
            <>
              <Form.Item label="调研内容及要求" name="survey_content"
                rules={[{ required: true, message: '请填写调研内容' }]}
                extra="技术规格、服务内容与要求，一行一条">
                <Input.TextArea rows={6} maxLength={8000} showCount />
              </Form.Item>
              <Form.Item label="参与单位资格要求（选填）" name="survey_qualification">
                <Input.TextArea rows={3} maxLength={2000} />
              </Form.Item>
              <Form.Item label="报价要求（选填）" name="survey_quote_req">
                <Input.TextArea rows={3} maxLength={2000} />
              </Form.Item>
              <Form.Item label="需提交的资料" name="survey_materials"
                rules={[{ required: true, message: '请填写需提交的资料' }]}>
                <Input.TextArea rows={4} maxLength={2000} />
              </Form.Item>
              <Space wrap style={{ width: '100%' }}>
                <Form.Item label="提交截止时间" name="survey_deadline" style={{ minWidth: 260 }}
                  rules={[{ required: true, message: '请填写截止时间' }]}>
                  <Input placeholder="如：2026年7月24日17:00" />
                </Form.Item>
              </Space>
              <Form.Item label="提交方式" name="survey_submit_way"
                rules={[{ required: true, message: '请填写提交方式' }]}
                extra="电子版邮箱、纸质版递交地址等">
                <Input.TextArea rows={3} maxLength={1000} />
              </Form.Item>
              <Form.Item label="特别说明" name="survey_note"
                extra="默认已含「调研结果与采购结果无必然联系」，可按需增删">
                <Input.TextArea rows={4} maxLength={2000} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item label="拟采购的货物或服务说明" name="ss_goods_desc"
                rules={[{ required: true, message: '此项为法定必备内容' }]}>
                <Input.TextArea rows={4} maxLength={4000} showCount />
              </Form.Item>
              <Form.Item label="采用单一来源采购方式的原因及说明" name="ss_reason"
                rules={[{ required: true, message: '此项为法定必备内容' }]}
                extra="如：因专利、专有技术、原有采购项目后续扩充等原因具有唯一性">
                <Input.TextArea rows={4} maxLength={4000} showCount />
              </Form.Item>
              <Space wrap style={{ width: '100%' }}>
                <Form.Item label="拟定的唯一供应商名称" name="ss_supplier_name"
                  style={{ minWidth: 320 }} rules={[{ required: true, message: '此项为法定必备内容' }]}>
                  <Input maxLength={200} />
                </Form.Item>
                <Form.Item label="供应商地址" name="ss_supplier_addr" style={{ minWidth: 380 }}>
                  <Input maxLength={300} />
                </Form.Item>
              </Space>

              <Text strong>专业人员论证意见（法定必备：须含姓名、工作单位、职称）</Text>
              <Form.List name="experts">
                {(fields, { add, remove }) => (
                  <div style={{ marginBottom: 12 }}>
                    {fields.map(({ key, name }) => (
                      <Card key={key} size="small" style={{ marginTop: 8 }}
                        extra={fields.length > 1 && (
                          <Button type="text" danger size="small" icon={<MinusCircleOutlined />}
                            onClick={() => remove(name)}>删除</Button>
                        )}>
                        <Space wrap>
                          <Form.Item name={[name, 'name']} label="姓名" style={{ marginBottom: 8, minWidth: 140 }}>
                            <Input maxLength={30} />
                          </Form.Item>
                          <Form.Item name={[name, 'org']} label="工作单位" style={{ marginBottom: 8, minWidth: 240 }}>
                            <Input maxLength={100} />
                          </Form.Item>
                          <Form.Item name={[name, 'title']} label="职称" style={{ marginBottom: 8, minWidth: 140 }}>
                            <Input maxLength={50} />
                          </Form.Item>
                        </Space>
                        <Form.Item name={[name, 'opinion']} label="论证意见" style={{ marginBottom: 0 }}>
                          <Input.TextArea rows={2} maxLength={2000} />
                        </Form.Item>
                      </Card>
                    ))}
                    <Button type="dashed" block icon={<PlusOutlined />} style={{ marginTop: 8 }}
                      onClick={() => add({ name: '', org: '', title: '', opinion: '' })}>
                      添加一位专业人员
                    </Button>
                  </div>
                )}
              </Form.List>

              <Form.Item label="公示期" name="ss_publicity"
                rules={[{ required: true, message: '请选择公示期' }]}
                extra="法定不得少于 5 个工作日">
                <DatePicker.RangePicker style={{ width: '100%' }} format="YYYY年M月D日" />
              </Form.Item>

              <Text strong>异议的接收</Text>
              <Space wrap style={{ width: '100%', marginTop: 8 }}>
                <Form.Item label="接收部门" name="ss_objection_dept" style={{ minWidth: 240 }}>
                  <Input maxLength={120} placeholder="如：内江市第一人民医院采购部" />
                </Form.Item>
                <Form.Item label="联系人" name="ss_objection_contact" style={{ minWidth: 160 }}>
                  <Input maxLength={50} />
                </Form.Item>
                <Form.Item label="联系电话" name="ss_objection_phone" style={{ minWidth: 200 }}>
                  <Input maxLength={50} />
                </Form.Item>
              </Space>
              <Form.Item label="接收地址（留空用医院地址）" name="ss_objection_addr">
                <Input maxLength={300} />
              </Form.Item>
            </>
          )}

          <Text strong>公告联系方式</Text>
          <Space wrap style={{ width: '100%', marginTop: 8 }}>
            <Form.Item label="联系人" name="agency_contact" style={{ minWidth: 180 }}>
              <Input maxLength={50} placeholder="如：王老师" />
            </Form.Item>
            <Form.Item label="联系电话" name="agency_contact_phone" style={{ minWidth: 200 }}>
              <Input maxLength={50} />
            </Form.Item>
            <Form.Item label="电子邮箱" name="agency_email" style={{ minWidth: 260 }}>
              <Input maxLength={100} />
            </Form.Item>
          </Space>
        </Form>

        <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
          <Space align="center">
            <Text strong><PaperClipOutlined /> 公告附件</Text>
            {editing ? (
              <Upload customRequest={customUpload as never} showUploadList={false} multiple
                accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar" disabled={uploading}>
                <Button size="small" icon={<UploadOutlined />} loading={uploading}>上传附件</Button>
              </Upload>
            ) : (
              <Upload multiple showUploadList={false}
                accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar"
                beforeUpload={(f) => { setPendingFiles(p => [...p, f as unknown as File]); return false }}>
                <Button size="small" icon={<UploadOutlined />}>选择附件</Button>
              </Upload>
            )}
            {!editing && pendingFiles.length > 0 && (
              <Text type="secondary">已选 {pendingFiles.length} 个，保存时自动上传</Text>
            )}
          </Space>
          {!editing && pendingFiles.length > 0 && (
            <List size="small" style={{ marginTop: 8 }} dataSource={pendingFiles}
              renderItem={(f, i) => (
                <List.Item actions={[
                  <Button key="rm" type="link" size="small" danger
                    onClick={() => setPendingFiles(p => p.filter((_, j) => j !== i))}>移除</Button>,
                ]}>{f.name}</List.Item>
              )} />
          )}
          {editing && (
            <List size="small" style={{ marginTop: 8 }} locale={{ emptyText: '暂无附件' }}
              dataSource={files}
              renderItem={f => (
                <List.Item actions={[
                  <Button key="dl" type="link" size="small" icon={<DownloadOutlined />}
                    href={downloadFileUrl(editing.id, f.id)}>下载</Button>,
                  <Popconfirm key="del" title="删除该附件？" okText="删除" cancelText="取消"
                    onConfirm={async () => { await deleteFile(editing.id, f.id); loadFiles(editing.id) }}>
                    <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                  </Popconfirm>,
                ]}>{f.original_name}</List.Item>
              )} />
          )}
        </div>
        {isAgency && (
          <Alert type="info" showIcon style={{ marginTop: 12 }}
            message="点「保存并提交确认」即可一次完成：保存内容、上传附件、提交给经办人。" />
        )}
      </Modal>

      <Modal
        open={!!rejectRow}
        title={`驳回${meta.name} — ${rejectRow?.project_name || ''}`}
        okText="确认驳回" okButtonProps={{ danger: true }} cancelText="取消"
        onOk={doReject}
        onCancel={() => { setRejectRow(null); setRejectReason('') }}
      >
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message="驳回后退回编制方修改，驳回原因会记入审批过程记录并随项目归档。" />
        <Input.TextArea rows={4} maxLength={500} showCount
          placeholder="请写明需要修改的具体内容"
          value={rejectReason} onChange={e => setRejectReason(e.target.value)} />
      </Modal>
    </Card>
  )
}
