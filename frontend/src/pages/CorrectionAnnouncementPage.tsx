import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Button, Space, Tag, Input, App, Typography, Tooltip, Popconfirm,
  Modal, Form, Select, Checkbox, Switch, Tabs, Alert, Upload, List, DatePicker,
} from 'antd'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import {
  FileSearchOutlined, PlusOutlined, DeleteOutlined, FileWordOutlined,
  UploadOutlined, PaperClipOutlined, DownloadOutlined, MinusCircleOutlined,
} from '@ant-design/icons'
import axios from 'axios'
import {
  getAnnouncements, getEligibleProjects, createAnnouncement, updateAnnouncement,
  deleteAnnouncement, submitAnnouncement, confirmAnnouncement, revokeAnnouncement,
  generateAnnouncementWord, listFiles, deleteFile, downloadFileUrl,
  type Announcement, type AnnProject, type AnnAttachment,
} from '../services/announcement'
import { useAuth } from '../hooks/useAuth'
import { cnOrdinal } from '../utils/ordinal'
import { parseCnDate, fmtCnDateTime } from '../utils/cnDate'

const { Text, Title } = Typography

interface CorrItem { item: string; before: string; after: string }

const SCOPE_OPTIONS = ['采购公告', '采购文件']

export default function CorrectionAnnouncementPage() {
  const { message } = App.useApp()
  const { user } = useAuth()
  const isAgency = user?.role === 'agency'
  const canConfirm = ['officer', 'assistant', 'leader'].includes(user?.role || '')

  const [loading, setLoading] = useState(true)
  const [rows, setRows] = useState<Announcement[]>([])
  const [keyword, setKeyword] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | '草稿' | '待确认' | '已确认'>('all')

  // 编辑弹窗
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Announcement | null>(null)  // null=新建
  const [projects, setProjects] = useState<AnnProject[]>([])
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()
  const inAttachment = Form.useWatch('corr_in_attachment', form)
  const correctBidTime = Form.useWatch('correct_bid_time', form)

  // 附件管理（编辑已存在的更正公告时可上传）
  const [files, setFiles] = useState<AnnAttachment[]>([])
  const [uploading, setUploading] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    getAnnouncements('correction')
      .then(res => setRows(res.data.data || []))
      .catch(() => message.error('加载更正公告失败'))
      .finally(() => setLoading(false))
  }, [message])
  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    let list = rows
    if (activeTab !== 'all') list = list.filter(r => (r.status || '草稿') === activeTab)
    const kw = keyword.trim()
    if (!kw) return list
    return list.filter(r =>
      (r.project_name || '').includes(kw) ||
      (r.project_number || '').includes(kw) ||
      (r.agency_name || '').includes(kw))
  }, [rows, activeTab, keyword])

  const loadFiles = useCallback(async (annId: number) => {
    try {
      const res = await listFiles(annId)
      setFiles(res.data.data || [])
    } catch { /* ignore */ }
  }, [])

  // ── 新建 / 编辑 ──────────────────────────────────────────────
  const openCreate = async () => {
    setEditing(null)
    setFiles([])
    form.resetFields()
    form.setFieldsValue({
      scopes: ['采购公告'],
      corr_in_attachment: false,
      correct_bid_time: false,
      items: [{ item: '', before: '', after: '' }],
    })
    try {
      const res = await getEligibleProjects('correction')
      setProjects(res.data.data || [])
      if (!(res.data.data || []).length)
        message.warning('暂无可发布更正公告的项目（需本轮采购公告已发布且未开标）')
    } catch { message.error('加载项目失败') }
    setEditOpen(true)
  }

  const openEdit = (r: Announcement) => {
    setEditing(r)
    let items: CorrItem[] = []
    try { items = JSON.parse(r.corr_items_json || '[]') } catch { items = [] }
    if (!items.length) items = [{ item: '', before: '', after: '' }]
    form.setFieldsValue({
      project_id: r.project_id,
      scopes: (r.corr_scope || '采购公告').split('、'),
      corr_reason: r.corr_reason || '',
      corr_in_attachment: !!r.corr_in_attachment,
      items,
      correct_bid_time: !!r.response_deadline,
      response_deadline: parseCnDate(r.response_deadline),
      agency_contact: r.agency_contact || '',
      agency_contact_phone: r.agency_contact_phone || '',
      agency_address: r.agency_address || '',
    })
    loadFiles(r.id)
    setEditOpen(true)
  }

  const handleSave = async () => {
    const v = await form.validateFields()
    const payload = {
      ann_type: 'correction',
      project_id: v.project_id,
      round_number: editing?.round_number
        || projects.find(p => p.id === v.project_id)?.round || 1,
      corr_scope: (v.scopes || []).join('、'),
      corr_reason: (v.corr_reason || '').trim(),
      corr_in_attachment: v.corr_in_attachment ? 1 : 0,
      corr_items_json: JSON.stringify(
        (v.items || []).filter((it: CorrItem) => (it.before || '').trim() || (it.after || '').trim()),
      ),
      // 仅在「开标时间更正」开关打开时携带新时间；关闭即置空（不同步）。
      // 日历控件返回 dayjs，转回中文串存库（与采购公告一致，兼容各处开标时间抓取）
      response_deadline: v.correct_bid_time ? fmtCnDateTime(v.response_deadline) : '',
      agency_contact: (v.agency_contact || '').trim(),
      agency_contact_phone: (v.agency_contact_phone || '').trim(),
      agency_address: (v.agency_address || '').trim(),
    }
    if (!payload.corr_in_attachment && payload.corr_items_json === '[]') {
      message.warning('请至少填写一条更正内容，或勾选「内容较多，详见附件」')
      return
    }
    setSaving(true)
    try {
      if (editing) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await updateAnnouncement(editing.id, payload as any)
        message.success('已保存')
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const res = await createAnnouncement(payload as any)
        message.success('已保存草稿，可继续上传附件')
        setEditing(res.data.data)   // 留在弹窗里，便于上传附件
        load()
        setSaving(false)
        return
      }
      setEditOpen(false)
      load()
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '保存失败')
    } finally {
      setSaving(false)
    }
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

  const downloadWord = async (r: Announcement) => {
    try {
      const res = await generateAnnouncementWord(r.id)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `更正公告_${r.project_number || r.project_name}（第${cnOrdinal(r.corr_seq || 1)}次）.docx`
      a.click()
      URL.revokeObjectURL(url)
    } catch { message.error('生成失败') }
  }

  // 附件上传（编辑态）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const customUpload = async (options: any) => {
    if (!editing) return
    const { file, onSuccess, onError } = options
    setUploading(true)
    const fd = new FormData()
    fd.append('file', file as Blob)
    try {
      const res = await axios.post(`/api/announcements/${editing.id}/files`, fd, {
        withCredentials: true,
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      onSuccess?.(res.data)
      message.success('上传成功')
      loadFiles(editing.id)
    } catch (err: unknown) {
      onError?.(err as Error)
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const STATUS_META: Record<string, { text: string; color: string; accent: string }> = {
    '已确认': { text: '已发布', color: 'green', accent: '#34a853' },
    '待确认': { text: '待确认', color: 'orange', accent: '#f9ab00' },
    '草稿': { text: '草稿', color: 'default', accent: '#9aa0a6' },
  }
  const corrToCard = (r: Announcement): RecordCardData => {
    const meta = STATUS_META[r.status || '草稿'] || STATUS_META['草稿']
    return {
      key: r.id,
      accent: meta.accent,
      title: `${r.project_name || '—'}（更正·第${cnOrdinal(r.corr_seq || 1)}次）`,
      subtitle: r.project_number || '无编号',
      statusText: meta.text,
      statusColor: meta.color,
      tags: r.corr_scope
        ? r.corr_scope.split('、').map(s => <Tag key={s} color="purple" style={{ marginInlineEnd: 0 }}>{s}更正</Tag>)
        : undefined,
      fields: [
        { label: '发布时间', value: r.confirmed_at ? r.confirmed_at.replace('T', ' ') : '' },
      ],
      actions: (
        <>
          {r.status !== '已确认' && <Button size="small" onClick={() => openEdit(r)}>编辑</Button>}
          <Button size="small" icon={<FileWordOutlined />} onClick={() => downloadWord(r)}>Word</Button>
          {r.status === '草稿' && (
            <Button size="small" type="primary" ghost onClick={() => runAction(() => submitAnnouncement(r.id))}>提交确认</Button>
          )}
          {r.status === '待确认' && canConfirm && (
            <Popconfirm title="确认并发布该更正公告？发布后将在公告首页公开展示。" okText="发布" cancelText="取消"
              onConfirm={() => runAction(() => confirmAnnouncement(r.id))}>
              <Button size="small" type="primary">确认发布</Button>
            </Popconfirm>
          )}
          {r.status === '已确认' && canConfirm && (
            <Popconfirm title="撤回该更正公告？将从公告首页下架并恢复为草稿。" okText="撤回" cancelText="取消"
              onConfirm={() => runAction(() => revokeAnnouncement(r.id))}>
              <Button size="small" danger>撤回</Button>
            </Popconfirm>
          )}
          {r.status !== '已确认' && (
            <Popconfirm title="删除该更正公告？" okText="删除" cancelText="取消"
              onConfirm={() => runAction(() => deleteAnnouncement(r.id))}>
              <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
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
          <Title level={4} style={{ margin: 0 }}>
            <FileSearchOutlined /> 6.3 更正公告
          </Title>
          <Text type="secondary">
            采购公告发布后、开标前，对原采购公告或采购文件进行更正。写明更正事项、更正前与更正后；内容较多可注明「详见附件」并上传附件。
          </Text>
        </div>

        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建更正公告
          </Button>
          <Input.Search
            placeholder="搜索项目名称 / 编号 / 代理机构"
            allowClear
            style={{ width: 320 }}
            onChange={e => setKeyword(e.target.value)}
          />
        </Space>

        <Tabs
          activeKey={activeTab}
          onChange={k => setActiveTab(k as typeof activeTab)}
          items={[
            { key: 'all',  label: `全部 (${rows.length})` },
            { key: '草稿',  label: `草稿 (${tabCount('草稿')})` },
            { key: '待确认', label: `待确认 (${tabCount('待确认')})` },
            { key: '已确认', label: `已发布 (${tabCount('已确认')})` },
          ]}
        />

        <RecordCards dataSource={filtered} loading={loading} emptyText="暂无更正公告" toCard={corrToCard} />
      </Space>

      {/* 新建 / 编辑弹窗 */}
      <Modal
        title={editing ? `编辑更正公告 — ${editing.project_name || ''}（第${cnOrdinal(editing.corr_seq || 1)}次）` : '新建更正公告'}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleSave}
        okText={editing ? '保存' : '保存草稿'}
        confirmLoading={saving}
        width={760}
        destroyOnHidden
        maskClosable={false}
      >
        <Alert
          type="info" showIcon style={{ marginBottom: 12 }}
          message="更正公告须在采购公告发布后、开标前发布；同一项目可多次更正，系统自动编号「第N次」。"
        />
        <Form form={form} layout="vertical">
          <Form.Item
            label="项目" name="project_id"
            rules={[{ required: true, message: '请选择项目' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              disabled={!!editing}
              placeholder="选择已发布采购公告、尚未开标的项目"
              options={(editing
                ? [{ value: editing.project_id, label: `${editing.project_number || ''} ${editing.project_name || ''}` }]
                : projects.map(p => ({ value: p.id, label: `${p.number || ''} ${p.name}` })))}
            />
          </Form.Item>

          <Form.Item
            label="更正事项" name="scopes"
            rules={[{ required: true, message: '请选择更正事项' }]}
          >
            <Checkbox.Group options={SCOPE_OPTIONS} />
          </Form.Item>

          <Form.Item label="更正原因（简述，选填）" name="corr_reason">
            <Input placeholder="如：递交响应文件截止时间调整 / 技术参数修订" maxLength={200} />
          </Form.Item>

          <Form.Item
            label="开标时间（递交响应文件截止时间）是否更正"
            name="correct_bid_time"
            valuePropName="checked"
            tooltip="打开并填写新时间后，更正公告发布时系统自动同步项目开标时间、原采购公告截止时间及开标管理列表"
          >
            <Switch checkedChildren="更正" unCheckedChildren="不更正" />
          </Form.Item>

          {correctBidTime && (
            <Form.Item
              label="更正后的开标时间（递交响应文件截止时间）"
              name="response_deadline"
              rules={[{ required: true, message: '请选择更正后的开标时间' }]}
              extra="日历选择，精确到分钟；发布后自动同步项目开标时间与开标管理列表"
            >
              <DatePicker
                style={{ width: '100%' }}
                showTime={{ format: 'HH:mm', minuteStep: 5 }}
                format="YYYY年M月D日 HH:mm"
                placeholder="选择更正后的开标日期时间"
              />
            </Form.Item>
          )}

          <Form.Item
            label="更正内容较多，详见附件" name="corr_in_attachment"
            valuePropName="checked" tooltip="勾选后正文写「更正内容较多，详见本公告附件」，请在下方上传附件"
          >
            <Switch />
          </Form.Item>

          {!inAttachment && (
            <Form.List name="items">
              {(fields, { add, remove }) => (
                <div style={{ marginBottom: 12 }}>
                  <Text strong>更正内容（逐条填写更正前 / 更正后）</Text>
                  {fields.map(({ key, name }) => (
                    <Card key={key} size="small" style={{ marginTop: 8 }}
                      extra={fields.length > 1 && (
                        <Button type="text" danger size="small"
                          icon={<MinusCircleOutlined />} onClick={() => remove(name)}>删除本条</Button>
                      )}>
                      <Form.Item name={[name, 'item']} label="更正事项说明（选填，如：原竞选文件 第三章 3.2 技术要求）"
                        style={{ marginBottom: 8 }}>
                        <Input maxLength={200} />
                      </Form.Item>
                      <Form.Item name={[name, 'before']} label="更正前" style={{ marginBottom: 8 }}>
                        <Input.TextArea rows={2} maxLength={2000} />
                      </Form.Item>
                      <Form.Item name={[name, 'after']} label="更正后" style={{ marginBottom: 0 }}>
                        <Input.TextArea rows={2} maxLength={2000} />
                      </Form.Item>
                    </Card>
                  ))}
                  <Button type="dashed" block icon={<PlusOutlined />}
                    style={{ marginTop: 8 }} onClick={() => add({ item: '', before: '', after: '' })}>
                    添加一条更正内容
                  </Button>
                </div>
              )}
            </Form.List>
          )}

          <Space size="middle" style={{ width: '100%' }} wrap>
            <Form.Item label="代理机构联系人" name="agency_contact" style={{ minWidth: 180 }}>
              <Input maxLength={50} />
            </Form.Item>
            <Form.Item label="联系电话" name="agency_contact_phone" style={{ minWidth: 180 }}>
              <Input maxLength={50} />
            </Form.Item>
            <Form.Item label="代理机构地址" name="agency_address" style={{ minWidth: 280 }}>
              <Input maxLength={200} />
            </Form.Item>
          </Space>
        </Form>

        {/* 附件：保存草稿后可上传 */}
        <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
          <Space align="center">
            <Text strong><PaperClipOutlined /> 公告附件</Text>
            {editing ? (
              <Upload customRequest={customUpload} showUploadList={false} multiple
                accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar" disabled={uploading}>
                <Button size="small" icon={<UploadOutlined />} loading={uploading}>上传附件</Button>
              </Upload>
            ) : (
              <Text type="secondary">（先保存草稿后即可上传）</Text>
            )}
          </Space>
          {editing && (
            <List
              size="small" style={{ marginTop: 8 }}
              locale={{ emptyText: '暂无附件' }}
              dataSource={files}
              renderItem={f => (
                <List.Item
                  actions={[
                    <Button key="dl" type="link" size="small" icon={<DownloadOutlined />}
                      href={downloadFileUrl(editing.id, f.id)}>下载</Button>,
                    <Popconfirm key="del" title="删除该附件？" okText="删除" cancelText="取消"
                      onConfirm={async () => { await deleteFile(editing.id, f.id); loadFiles(editing.id) }}>
                      <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                    </Popconfirm>,
                  ]}
                >
                  <Tooltip title={`${f.uploaded_by || ''} ${f.uploaded_at ? f.uploaded_at.replace('T', ' ') : ''}`}>
                    {f.original_name}
                  </Tooltip>
                </List.Item>
              )}
            />
          )}
        </div>
        {isAgency && (
          <Alert type="warning" showIcon style={{ marginTop: 12 }}
            message="保存后请点击列表中的「提交确认」，经办人确认后才会挂网发布。" />
        )}
      </Modal>
    </Card>
  )
}
