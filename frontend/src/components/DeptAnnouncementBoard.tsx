/**
 * 采购部公告和相关文件（分流页区块）。
 * 已发布=全员可见可下载；经办人可上传（进待审核）；陈梦霞审核发布/驳回。
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Card, List, Button, Tag, Space, Typography, Modal, Form, Input, Upload, App,
  Popconfirm, Tabs,
} from 'antd'
import {
  NotificationOutlined, UploadOutlined, PaperClipOutlined, DeleteOutlined,
  CheckOutlined, CloseOutlined, InboxOutlined,
} from '@ant-design/icons'
import {
  listDeptAnnouncements, createDeptAnnouncement, reviewDeptAnnouncement,
  deleteDeptAnnouncement, deptAnnouncementDownloadUrl, type DeptAnnouncement,
} from '../services/deptAnnouncement'

const { Text } = Typography

const STATUS_COLOR: Record<string, string> = {
  已发布: 'green', 待审核: 'orange', 已驳回: 'red',
}

export default function DeptAnnouncementBoard() {
  const { message, modal } = App.useApp()
  const [rows, setRows] = useState<DeptAnnouncement[]>([])
  const [isReviewer, setIsReviewer] = useState(false)
  const [canUpload, setCanUpload] = useState(false)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'published' | 'mine'>('published')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [file, setFile] = useState<File>()
  const [form] = Form.useForm()

  const load = useCallback(() => {
    setLoading(true)
    listDeptAnnouncements()
      .then(res => {
        setRows(res.data.data || [])
        setIsReviewer(res.data.is_reviewer)
        setCanUpload(res.data.can_upload)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const published = rows.filter(r => r.status === '已发布')
  const pendingMine = rows.filter(r => r.status !== '已发布')
  const pendingCount = rows.filter(r => r.status === '待审核').length

  const submit = async () => {
    const v = await form.validateFields()
    setSubmitting(true)
    try {
      const res = await createDeptAnnouncement(v.title.trim(), (v.note || '').trim(), file)
      message.success(res.data.message)
      setUploadOpen(false)
      form.resetFields()
      setFile(undefined)
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const doReview = (r: DeptAnnouncement, action: 'approve' | 'reject') => {
    if (action === 'reject') {
      let reason = ''
      modal.confirm({
        title: `驳回「${r.title}」`,
        content: <Input placeholder="驳回原因（选填）" onChange={e => { reason = e.target.value }} />,
        okText: '驳回', okButtonProps: { danger: true },
        onOk: async () => {
          await reviewDeptAnnouncement(r.id, 'reject', reason)
          message.success('已驳回')
          load()
        },
      })
    } else {
      modal.confirm({
        title: `发布「${r.title}」？`,
        content: '发布后全员可见可下载。',
        onOk: async () => {
          await reviewDeptAnnouncement(r.id, 'approve')
          message.success('已发布')
          load()
        },
      })
    }
  }

  const item = (r: DeptAnnouncement) => (
    <List.Item
      key={r.id}
      actions={[
        r.filename && (
          <Button key="dl" size="small" type="link" icon={<PaperClipOutlined />}
            href={deptAnnouncementDownloadUrl(r.id)} target="_blank">
            {r.filename.length > 24 ? r.filename.slice(0, 22) + '…' : r.filename}
          </Button>
        ),
        isReviewer && r.status === '待审核' && (
          <Space key="review">
            <Button size="small" type="primary" icon={<CheckOutlined />}
              onClick={() => doReview(r, 'approve')}>发布</Button>
            <Button size="small" danger icon={<CloseOutlined />}
              onClick={() => doReview(r, 'reject')}>驳回</Button>
          </Space>
        ),
        (isReviewer || r.status !== '已发布') && (
          <Popconfirm key="del" title="删除该条？"
            onConfirm={async () => { await deleteDeptAnnouncement(r.id); message.success('已删除'); load() }}>
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        ),
      ].filter(Boolean)}
    >
      <List.Item.Meta
        title={
          <Space>
            {r.title}
            <Tag color={STATUS_COLOR[r.status]}>{r.status}</Tag>
            {r.status === '已驳回' && r.reject_reason && (
              <Text type="danger" style={{ fontSize: 12 }}>（{r.reject_reason}）</Text>
            )}
          </Space>
        }
        description={
          <Text type="secondary" style={{ fontSize: 12 }}>
            {r.uploaded_by} · {(r.uploaded_at || '').replace('T', ' ').slice(0, 16)}
            {r.note ? ` · ${r.note}` : ''}
          </Text>
        }
      />
    </List.Item>
  )

  return (
    <Card
      title={
        <span>
          <NotificationOutlined style={{ color: '#fa8c16' }} /> 采购部公告和相关文件
          {isReviewer && pendingCount > 0 && (
            <Tag color="red" style={{ marginLeft: 8 }}>{pendingCount} 条待审核</Tag>
          )}
        </span>
      }
      extra={canUpload && (
        <Button size="small" type="primary" ghost icon={<UploadOutlined />}
          onClick={() => setUploadOpen(true)}>
          上传公告/文件
        </Button>
      )}
      style={{ marginTop: 20 }}
    >
      {(canUpload || isReviewer) && pendingMine.length > 0 && (
        <Tabs
          size="small"
          activeKey={tab}
          onChange={k => setTab(k as 'published' | 'mine')}
          items={[
            { key: 'published', label: `已发布 (${published.length})` },
            { key: 'mine', label: isReviewer ? `待审核/驳回 (${pendingMine.length})` : `我的待审/驳回 (${pendingMine.length})` },
          ]}
        />
      )}
      <List
        size="small"
        loading={loading}
        dataSource={tab === 'mine' && pendingMine.length > 0 ? pendingMine : published}
        locale={{ emptyText: '暂无公告' }}
        renderItem={item}
      />

      <Modal
        title="上传采购部公告 / 相关文件"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={submit}
        okText="提交审核"
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请填写标题' }]}>
            <Input placeholder="如：2026年采购工作安排通知" maxLength={100} />
          </Form.Item>
          <Form.Item label="说明（选填）" name="note">
            <Input.TextArea rows={2} maxLength={300} />
          </Form.Item>
          <Form.Item label="附件（选填）">
            <Upload.Dragger
              maxCount={1}
              beforeUpload={f => { setFile(f as unknown as File); return false }}
              onRemove={() => setFile(undefined)}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.zip,.rar,.txt,.md"
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">点击或拖拽文件</p>
            </Upload.Dragger>
          </Form.Item>
        </Form>
        <Text type="secondary" style={{ fontSize: 12 }}>
          提交后须经陈梦霞审核，通过后全员可见。
        </Text>
      </Modal>
    </Card>
  )
}
