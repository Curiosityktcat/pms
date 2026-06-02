import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { Modal, Upload, Button, List, Popconfirm, Typography, Alert } from 'antd'
import {
  UploadOutlined, PaperClipOutlined, DownloadOutlined, DeleteOutlined,
} from '@ant-design/icons'
import { App } from 'antd'
import type { Project } from '../services/project'
import {
  listDocAttachments, deleteDocAttachment, downloadDocAttachment,
  uploadDocAttachmentUrl, type DocAttachment, type ConfirmKind,
} from '../services/procurementDoc'

const { Text } = Typography
// antd 自定义上传选项类型较繁琐，这里用 any 简化
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type UploadRequestOption = any

function fmtSize(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

/** 采购文件编制阶段的附件上传/管理弹窗（采购需求确认 / 采购文件确认通用）。 */
export default function DocAttachmentsModal({
  project, kind, title, showHash = false, locked = false, open, onClose,
}: {
  project: Project | null
  kind: ConfirmKind
  title: string
  showHash?: boolean
  locked?: boolean
  open: boolean
  onClose: () => void
}) {
  const { message } = App.useApp()
  const [files, setFiles] = useState<DocAttachment[]>([])
  const [uploading, setUploading] = useState(false)

  const load = useCallback(async () => {
    if (!project) return
    try {
      const res = await listDocAttachments(project.id, kind)
      setFiles(res.data.data || [])
    } catch { /* ignore */ }
  }, [project, kind])

  useEffect(() => { if (open) load() }, [open, load])

  const customUpload = async (options: UploadRequestOption) => {
    if (!project) return
    const { file, onSuccess, onError } = options
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file as Blob)
    try {
      const res = await axios.post(uploadDocAttachmentUrl(project.id, kind), formData, {
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
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      message.error(e.response?.data?.error || '删除失败')
    }
  }

  return (
    <Modal
      title={`${title} — ${project?.name || ''}`}
      open={open}
      onCancel={onClose}
      footer={<Button onClick={onClose}>关闭</Button>}
      width={640}
      destroyOnHidden
    >
      {locked ? (
        <Alert type="success" showIcon style={{ marginBottom: 12 }}
          message="该环节已确认，文件已锁定；如需增删请先撤销确认。" />
      ) : (
        <Upload
          customRequest={customUpload}
          showUploadList={false}
          multiple
          accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.zip,.rar"
          disabled={uploading}
        >
          <Button icon={<UploadOutlined />} loading={uploading}>
            上传文件 / 附件（PDF / Word / Excel / 图片 / 压缩包）
          </Button>
        </Upload>
      )}

      <List
        size="small"
        style={{ marginTop: 12 }}
        locale={{ emptyText: '暂无上传文件' }}
        dataSource={files}
        renderItem={(f) => (
          <List.Item
            actions={[
              <Button key="dl" type="link" size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(f)}>下载</Button>,
              ...(locked ? [] : [
                <Popconfirm key="del" title="删除该文件？" onConfirm={() => handleDelete(f)} okText="删除" cancelText="取消">
                  <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                </Popconfirm>,
              ]),
            ]}
          >
            <List.Item.Meta
              avatar={<PaperClipOutlined />}
              title={f.original_name}
              description={
                <>
                  <div>{`${fmtSize(f.file_size)} · ${f.uploaded_by || ''} ${f.uploaded_at ? f.uploaded_at.replace('T', ' ') : ''}`}</div>
                  {showHash && f.sha256 && (
                    <Text code copyable={{ text: f.sha256 }} style={{ fontSize: 12 }}>
                      SHA256: {f.sha256}
                    </Text>
                  )}
                </>
              }
            />
          </List.Item>
        )}
      />
    </Modal>
  )
}
