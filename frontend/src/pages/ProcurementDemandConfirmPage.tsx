import { useState, useEffect, useMemo, useCallback } from 'react'
import axios from 'axios'
import {
  Card, Table, Button, Space, Tag, Input, App, Typography, Tooltip, Popconfirm,
  Modal, Upload, List,
} from 'antd'
import {
  AuditOutlined, CheckCircleOutlined, UploadOutlined, PaperClipOutlined,
  DownloadOutlined, DeleteOutlined,
} from '@ant-design/icons'
import { getProjects, type Project } from '../services/project'
import {
  setDocConfirm, listDocAttachments, deleteDocAttachment, downloadDocAttachment,
  uploadDocAttachmentUrl, type DocAttachment,
} from '../services/procurementDoc'

const { Title, Text } = Typography
// antd 自定义上传选项类型较繁琐，这里用 any 简化
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type UploadRequestOption = any

function ConfirmTag({ confirmed, by, at }: { confirmed: boolean; by: string; at: string }) {
  if (!confirmed) return <Tag>未确认</Tag>
  return (
    <Tooltip title={`${by || ''}${at ? ` · ${at.replace('T', ' ')}` : ''}`}>
      <Tag color="green" icon={<CheckCircleOutlined />}>已确认</Tag>
    </Tooltip>
  )
}

function fmtSize(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

/** 采购需求文件上传/管理弹窗 */
function AttachmentsModal({
  project, open, onClose,
}: { project: Project | null; open: boolean; onClose: () => void }) {
  const { message } = App.useApp()
  const [files, setFiles] = useState<DocAttachment[]>([])
  const [uploading, setUploading] = useState(false)

  const load = useCallback(async () => {
    if (!project) return
    try {
      const res = await listDocAttachments(project.id, 'demand')
      setFiles(res.data.data || [])
    } catch { /* ignore */ }
  }, [project])

  useEffect(() => { if (open) load() }, [open, load])

  const customUpload = async (options: UploadRequestOption) => {
    if (!project) return
    const { file, onSuccess, onError } = options
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file as Blob)
    try {
      const res = await axios.post(uploadDocAttachmentUrl(project.id, 'demand'), formData, {
        withCredentials: true,
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      onSuccess?.(res.data)
      message.success('上传成功')
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      onError?.(err as Error)
      message.error(e.response?.data?.error || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleDownload = async (f: DocAttachment) => {
    if (!project) return
    try {
      const res = await downloadDocAttachment(project.id, f.id)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = f.original_name
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('下载失败')
    }
  }

  const handleDelete = async (f: DocAttachment) => {
    if (!project) return
    try {
      await deleteDocAttachment(project.id, f.id)
      message.success('已删除')
      load()
    } catch {
      message.error('删除失败')
    }
  }

  return (
    <Modal
      title={`采购需求文件 — ${project?.name || ''}`}
      open={open}
      onCancel={onClose}
      footer={<Button onClick={onClose}>关闭</Button>}
      width={600}
      destroyOnHidden
    >
      <Upload
        customRequest={customUpload}
        showUploadList={false}
        multiple
        accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar"
        disabled={uploading}
      >
        <Button icon={<UploadOutlined />} loading={uploading}>
          上传需求文件 / 附件（PDF / Word / Excel / 图片 / 压缩包）
        </Button>
      </Upload>

      <List
        size="small"
        style={{ marginTop: 12 }}
        locale={{ emptyText: '暂无上传文件' }}
        dataSource={files}
        renderItem={(f) => (
          <List.Item
            actions={[
              <Button key="dl" type="link" size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(f)}>下载</Button>,
              <Popconfirm key="del" title="删除该文件？" onConfirm={() => handleDelete(f)} okText="删除" cancelText="取消">
                <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              avatar={<PaperClipOutlined />}
              title={f.original_name}
              description={`${fmtSize(f.file_size)} · ${f.uploaded_by || ''} ${f.uploaded_at ? f.uploaded_at.replace('T', ' ') : ''}`}
            />
          </List.Item>
        )}
      />
    </Modal>
  )
}

export default function ProcurementDemandConfirmPage() {
  const { message } = App.useApp()
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
          {r.demand_confirmed ? (
            <Popconfirm title="撤销采购需求确认？" onConfirm={() => toggleConfirm(r)} okText="撤销" cancelText="取消">
              <Button type="link" size="small" danger>撤销确认</Button>
            </Popconfirm>
          ) : (
            <Button type="link" size="small" onClick={() => toggleConfirm(r)}>确认</Button>
          )}
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

      <AttachmentsModal
        project={attachProject}
        open={!!attachProject}
        onClose={() => setAttachProject(null)}
      />
    </Card>
  )
}
