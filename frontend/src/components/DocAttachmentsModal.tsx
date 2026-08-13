import { useState, useEffect, useCallback } from 'react'
import { Modal, Upload, Button, List, Popconfirm, Typography, Alert, Space, Checkbox, Tag, Empty } from 'antd'
import {
  UploadOutlined, PaperClipOutlined, DownloadOutlined, DeleteOutlined, EyeOutlined,
  InboxOutlined,
} from '@ant-design/icons'
import { App } from 'antd'
import type { Project } from '../services/project'
import { useAuth } from '../hooks/useAuth'
import {
  listDocAttachments, deleteDocAttachment, downloadDocAttachment,
  uploadDocAttachmentUrl, docAttachmentPreviewUrl,
  listPoolAttachments, importPoolAttachments,
  type DocAttachment, type ConfirmKind, type PoolAttachment,
} from '../services/procurementDoc'
import FilePreviewModal, { isPreviewable } from './FilePreviewModal'
import { smartUploadAbs } from '../services/upload'

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
  project, kind, title, showHash = false, locked = false, roundNumber, open, onClose,
}: {
  project: Project | null
  kind: ConfirmKind
  title: string
  showHash?: boolean
  locked?: boolean
  /** 指定轮次只读查看历史（不传则为当前轮，可上传/删除）。 */
  roundNumber?: number
  open: boolean
  onClose: () => void
}) {
  const { message } = App.useApp()
  const { user } = useAuth()
  const [files, setFiles] = useState<DocAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })

  // 能预览的那几件，按列表顺序排好，交给面板做「上一件 / 下一件」。
  // 一批附件常常是十几份，一件件点开关掉太费手——尤其核对的时候要来回翻。
  const pvList = project
    ? files.filter(f => isPreviewable(f.original_name)).map(f => ({
        url: docAttachmentPreviewUrl(project.id, f.id),
        filename: f.original_name,
      }))
    : []
  const pvIdx = pvList.findIndex(x => x.url === preview.url)

  // 从项目池挑选采购需求文件（项目池不对代理机构开放）
  const canPickPool = kind === 'demand'
    && ['officer', 'assistant', 'pd_assistant', 'leader'].includes(user?.role || '')
  const [poolOpen, setPoolOpen] = useState(false)
  const [pool, setPool] = useState<PoolAttachment[]>([])
  const [poolSel, setPoolSel] = useState<number[]>([])
  const [importing, setImporting] = useState(false)

  const load = useCallback(async () => {
    if (!project) return
    try {
      const res = await listDocAttachments(project.id, kind, roundNumber)
      setFiles(res.data.data || [])
    } catch { /* ignore */ }
  }, [project, kind, roundNumber])

  useEffect(() => { if (open) load() }, [open, load])

  useEffect(() => {
    if (!poolOpen || !project) return
    setPoolSel([])
    listPoolAttachments(project.id)
      .then(r => setPool(r.data.data || []))
      .catch(() => { setPool([]); message.error('加载项目池附件失败') })
  }, [poolOpen, project, message])

  const doImport = async () => {
    if (!project || !poolSel.length) return
    setImporting(true)
    try {
      const r = await importPoolAttachments(project.id, poolSel)
      message.success(r.data.message || '已导入')
      setPoolOpen(false)
      load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      message.error(e.response?.data?.error || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const customUpload = async (options: UploadRequestOption) => {
    if (!project) return
    const { file, onSuccess, onError } = options
    setUploading(true)
    try {
      const res = await smartUploadAbs(uploadDocAttachmentUrl(project.id, kind), file as File)
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
        <Space wrap>
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
          {/* 项目池附件不再自动全量带入（内含医院内部文件），由经办人在此挑选 */}
          {canPickPool && (
            <Button icon={<InboxOutlined />} onClick={() => setPoolOpen(true)}>从项目池选择</Button>
          )}
        </Space>
      )}

      <List
        size="small"
        style={{ marginTop: 12 }}
        locale={{ emptyText: '暂无上传文件' }}
        dataSource={files}
        renderItem={(f) => (
          <List.Item
            actions={[
              ...(isPreviewable(f.original_name) ? [
                <Button key="pv" type="link" size="small" icon={<EyeOutlined />}
                  onClick={() => project && setPreview({ open: true, url: docAttachmentPreviewUrl(project.id, f.id), name: f.original_name })}>预览</Button>,
              ] : []),
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
      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        siblings={pvList}
        index={pvIdx}
        onNavigate={i => setPreview({ open: true, url: pvList[i].url, name: pvList[i].filename })}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />

      {/* ─── 从项目池挑选（只挑选中的，不再全量带入）───────────────────── */}
      <Modal
        title="从项目池选择采购需求文件"
        open={poolOpen}
        onCancel={() => setPoolOpen(false)}
        onOk={doImport}
        okText={`导入所选（${poolSel.length}）`}
        okButtonProps={{ disabled: !poolSel.length }}
        confirmLoading={importing}
        width={640}
        destroyOnHidden
      >
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message="只勾选可以给代理机构的文件"
          description="项目池里是 rd-web 审签表带来的原始材料，可能含医院内部文件。导入后会作为采购需求文件交给代理机构，请只挑选适合对外的。" />
        {pool.length === 0 ? (
          <Empty description="该项目没有关联的项目池附件" />
        ) : (
          <Checkbox.Group value={poolSel} onChange={v => setPoolSel(v as number[])} style={{ width: '100%' }}>
            <List
              size="small"
              style={{ width: '100%' }}
              dataSource={pool}
              renderItem={(p) => (
                <List.Item>
                  <Checkbox value={p.id} disabled={!p.exists}>
                    <Space size={6} wrap>
                      <PaperClipOutlined />
                      <span>{p.original_name}</span>
                      <Text type="secondary" style={{ fontSize: 12 }}>{fmtSize(p.file_size)}</Text>
                      {p.imported && <Tag color="green">已导入</Tag>}
                      {!p.exists && <Tag color="red">文件已丢失</Tag>}
                    </Space>
                  </Checkbox>
                </List.Item>
              )}
            />
          </Checkbox.Group>
        )}
      </Modal>
    </Modal>
  )
}
