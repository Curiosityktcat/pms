import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Spin, Space, Tag } from 'antd'
import { ArrowLeftOutlined, DownloadOutlined, FileWordOutlined } from '@ant-design/icons'
import {
  getPublicAnnouncement, getPublicAnnouncementFiles,
  publicDownloadFileUrl, publicWordUrl, getPublicAnnouncementHtml,
} from '../services/announcement'
import type { Announcement, AnnAttachment } from '../services/announcement'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  if (['doc', 'docx'].includes(ext)) return '📄'
  if (['pdf'].includes(ext)) return '📕'
  if (['xls', 'xlsx'].includes(ext)) return '📊'
  if (['jpg', 'jpeg', 'png', 'gif'].includes(ext)) return '🖼️'
  if (['zip', 'rar', '7z'].includes(ext)) return '🗜️'
  return '📎'
}

export default function PublicAnnouncementDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [ann, setAnn] = useState<Announcement | null>(null)
  const [files, setFiles] = useState<AnnAttachment[]>([])
  const [docHtml, setDocHtml] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [htmlLoading, setHtmlLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    const annId = parseInt(id)

    setLoading(true)
    Promise.all([
      getPublicAnnouncement(annId),
      getPublicAnnouncementFiles(annId),
    ])
      .then(([annRes, filesRes]) => {
        setAnn(annRes.data.data)
        setFiles(filesRes.data.data)
      })
      .catch((err: any) => {
        setError(err.response?.data?.error || '公告不存在或未发布')
      })
      .finally(() => setLoading(false))

    // 拉取后端生成的精准 HTML（python-docx 提取格式）
    setHtmlLoading(true)
    getPublicAnnouncementHtml(annId)
      .then((res) => setDocHtml(res.data.html))
      .catch(() => setDocHtml('<p style="color:#aaa;text-align:center;padding:40px 0">内容加载失败，请下载 Word 文档查看</p>'))
      .finally(() => setHtmlLoading(false))
  }, [id])

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f4f8' }}>
        <Spin size="large" tip="加载公告..." />
      </div>
    )
  }

  if (error || !ann) {
    return (
      <div style={{ minHeight: '100vh', background: '#f0f4f8', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontSize: 52, marginBottom: 16 }}>😕</div>
        <div style={{ fontSize: 18, color: '#333', marginBottom: 20 }}>{error || '公告不存在'}</div>
        <Button type="primary" icon={<ArrowLeftOutlined />} onClick={() => navigate('/login')}>返回首页</Button>
      </div>
    )
  }

  const wordUrl = publicWordUrl(ann.id)

  return (
    <div style={{ minHeight: '100vh', background: '#f0f4f8' }}>

      {/* ══ 顶部导航 ══════════════════════════════════════════════ */}
      <div style={{
        background: 'linear-gradient(135deg, #0d2c5e 0%, #1a4a8a 60%, #1677ff 100%)',
        padding: '12px 40px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        boxShadow: '0 2px 12px rgba(0,0,0,.3)',
        position: 'sticky', top: 0, zIndex: 100,
      }}>
        <Space size={12}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/login')}
            style={{ background: 'rgba(255,255,255,.15)', border: '1px solid rgba(255,255,255,.3)', color: '#fff' }}
          >
            返回首页
          </Button>
          <span style={{ color: '#fff', fontSize: 15, fontWeight: 600 }}>
            🏥 自行采购管理信息系统 · 采购公告
          </span>
        </Space>
        <Button
          icon={<DownloadOutlined />}
          href={wordUrl}
          download
          style={{ background: 'rgba(255,255,255,.15)', border: '1px solid rgba(255,255,255,.3)', color: '#fff' }}
        >
          下载 Word 文档
        </Button>
      </div>

      {/* ══ 主体 ════════════════════════════════════════════════ */}
      <div style={{ maxWidth: 900, margin: '32px auto', padding: '0 24px' }}>

        {/* ── 公告正文（A4 纸风格） ────────────────────────────── */}
        <div style={{
          background: '#fff',
          borderRadius: 4,
          boxShadow: '0 2px 18px rgba(0,0,0,.12)',
          padding: '60px 72px',
          minHeight: 500,
          marginBottom: 16,
          fontFamily: '"仿宋", FangSong, "仿宋_GB2312", "STFangsong", serif',
        }}>
          {htmlLoading ? (
            <div style={{ textAlign: 'center', padding: '80px 0' }}>
              <Spin size="large" tip="正在渲染公告内容..." />
            </div>
          ) : (
            <div dangerouslySetInnerHTML={{ __html: docHtml }} />
          )}
        </div>

        {/* ── 相关附件 ──────────────────────────────────────────── */}
        {files.length > 0 && (
          <div style={{
            background: '#fff',
            borderRadius: 4,
            boxShadow: '0 2px 18px rgba(0,0,0,.12)',
            overflow: 'hidden',
            marginBottom: 16,
          }}>
            <div style={{
              background: '#f7f8fa',
              padding: '12px 24px',
              borderBottom: '1px solid #eee',
              display: 'flex', alignItems: 'center', gap: 8,
              fontWeight: 600, fontSize: 14, color: '#333',
            }}>
              📎 相关附件
              <Tag color="blue">{files.length} 个文件</Tag>
            </div>
            {files.map((f) => (
              <div key={f.id} style={{
                display: 'flex', alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 24px',
                borderBottom: '1px solid #f5f5f5',
              }}
                onMouseEnter={e => (e.currentTarget.style.background = '#f9fbff')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <Space size={10}>
                  <span style={{ fontSize: 20 }}>{fileIcon(f.original_name)}</span>
                  <div>
                    <div style={{ fontWeight: 500, fontSize: 14, color: '#1a2035' }}>{f.original_name}</div>
                    <div style={{ fontSize: 12, color: '#aaa', marginTop: 2 }}>
                      {formatSize(f.file_size)} · {f.uploaded_at?.replace('T', ' ').substring(0, 16) || '—'}
                    </div>
                  </div>
                </Space>
                <Button
                  type="primary" ghost size="small"
                  icon={<DownloadOutlined />}
                  href={publicDownloadFileUrl(ann.id, f.id)}
                  download={f.original_name}
                >
                  下载
                </Button>
              </div>
            ))}
          </div>
        )}

        {/* ── Word 下载条 ─────────────────────────────────────────── */}
        <div style={{
          background: '#fff',
          borderRadius: 4,
          boxShadow: '0 2px 18px rgba(0,0,0,.12)',
          padding: '14px 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 32,
        }}>
          <Space size={8}>
            <FileWordOutlined style={{ fontSize: 20, color: '#1677ff' }} />
            <span style={{ fontSize: 13, color: '#555' }}>如需打印或存档，请下载原始 Word 文档</span>
          </Space>
          <Button type="primary" icon={<DownloadOutlined />} href={wordUrl} download>
            下载 Word 文档
          </Button>
        </div>

        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <Button size="large" icon={<ArrowLeftOutlined />} onClick={() => navigate('/login')} style={{ minWidth: 160 }}>
            返回采购公告列表
          </Button>
        </div>
      </div>
    </div>
  )
}
