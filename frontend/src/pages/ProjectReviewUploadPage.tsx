import { useState, useEffect, useCallback } from 'react'
import { Card, Button, Drawer, Space, App, Upload, Popconfirm, Tooltip, Typography, Alert } from 'antd'
import { PaperClipOutlined, EyeOutlined, DownloadOutlined, DeleteOutlined } from '@ant-design/icons'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'
import { useAuth } from '../hooks/useAuth'
import {
  listReviewProjects, uploadReviewFile, deleteReviewFile,
  reviewPreviewUrl, reviewDownloadUrl, type ReviewProject,
} from '../services/projectReview'

const { Text } = Typography

function fmtSize(n: number) {
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

export default function ProjectReviewUploadPage() {
  const { message } = App.useApp()
  const { user } = useAuth()
  const role = user?.role || ''
  const canUpload = ['agency', 'officer', 'assistant', 'pd_assistant', 'leader'].includes(role) || !!user?.is_admin

  const [rows, setRows] = useState<ReviewProject[]>([])
  const [loading, setLoading] = useState(false)
  const [cur, setCur] = useState<ReviewProject | null>(null)
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listReviewProjects()
      setRows(res.data.data || [])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])
  useEffect(() => { load() }, [load])

  // 打开的抽屉同步最新数据
  useEffect(() => {
    if (cur) {
      const fresh = rows.find(r => r.id === cur.id)
      if (fresh && fresh !== cur) setCur(fresh)
    }
  }, [rows]) // eslint-disable-line react-hooks/exhaustive-deps

  const doUpload = async (file: File) => {
    if (!cur) return
    setUploading(true)
    try { await uploadReviewFile(cur.id, file); message.success('已上传'); await load() }
    catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '上传失败')
    } finally { setUploading(false) }
  }

  const toCard = (p: ReviewProject): RecordCardData => {
    const n = p.attachments?.length || 0
    return {
      key: p.id,
      accent: n > 0 ? '#34a853' : '#f9ab00',
      title: <span style={{ fontWeight: 600 }}>{p.name}</span>,
      subtitle: <Text type="secondary">{p.number}</Text>,
      statusText: n > 0 ? '已上传评审结果' : '待上传评审结果',
      statusColor: n > 0 ? 'green' : 'orange',
      fields: [
        { label: '采购方式', value: p.method },
        { label: '代理机构', value: p.agency_name || p.agency_code || '—' },
        { label: '轮次', value: `第 ${p.current_round} 轮` },
        { label: '评审结果', value: n > 0 ? `${n} 个文件` : <Text type="warning">未上传</Text> },
      ],
      actions: (
        <Button size="small" type={n > 0 ? 'default' : 'primary'} icon={<PaperClipOutlined />} onClick={() => setCur(p)}>
          {canUpload ? '上传/查看评审结果' : '查看评审结果'}
        </Button>
      ),
    }
  }

  return (
    <Card title="8.5 项目评审资料上传">
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="院内竞选 / 单一来源采购：代理机构完成可开标判定、线下开标评审后，在此上传「签字的评审结果」，之后方可在「9. 采购结果确认」草拟采购结果确认函。"
      />
      <RecordCards dataSource={rows} toCard={toCard} loading={loading} emptyText="暂无待上传评审结果的项目" />

      <Drawer title={`评审结果 — ${cur?.name || ''}`} open={!!cur} onClose={() => setCur(null)} width={520}>
        {cur && (
          <div>
            {(cur.attachments || []).length === 0 ? (
              <Text type="secondary">暂无评审结果文件</Text>
            ) : (
              (cur.attachments || []).map(att => (
                <div key={att.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 10px', borderRadius: 6, marginBottom: 4,
                  background: '#fafafa', border: '1px solid #f0f0f0',
                }}>
                  <Tooltip title={att.original_name}>
                    <span style={{ fontSize: 13, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {att.original_name}
                    </span>
                  </Tooltip>
                  <Space size={2}>
                    <Text type="secondary" style={{ fontSize: 11 }}>{fmtSize(att.file_size)}</Text>
                    {isPreviewable(att.original_name) && (
                      <Button size="small" type="link" icon={<EyeOutlined />}
                        onClick={() => setPreview({ open: true, url: reviewPreviewUrl(cur.id, att.id), name: att.original_name })} />
                    )}
                    <Button size="small" type="link" icon={<DownloadOutlined />}
                      href={reviewDownloadUrl(cur.id, att.id)} download={att.original_name} />
                    {canUpload && (
                      <Popconfirm title="删除该文件？" onConfirm={async () => {
                        try { await deleteReviewFile(cur.id, att.id); message.success('已删除'); await load() }
                        catch { message.error('删除失败') }
                      }}>
                        <Button size="small" type="link" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    )}
                  </Space>
                </div>
              ))
            )}
            {canUpload && (
              <>
                <Upload showUploadList={false} beforeUpload={(f) => { doUpload(f as File); return false }}>
                  <Button icon={<PaperClipOutlined />} loading={uploading} type="primary" style={{ marginTop: 10 }}>
                    上传评审结果
                  </Button>
                </Upload>
                <div style={{ color: '#aaa', fontSize: 12, marginTop: 6 }}>
                  上传签字盖章的评审结果（PDF / Word / 图片等）。上传后即可草拟采购结果确认函。
                </div>
              </>
            )}
          </div>
        )}
      </Drawer>

      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />
    </Card>
  )
}
