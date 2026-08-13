import { useEffect, useState } from 'react'
import { Layout, Menu, Card, Spin, Typography, Tag, Empty, Alert, message } from 'antd'
import { BookOutlined, HistoryOutlined } from '@ant-design/icons'
import axios from 'axios'
import { useAuth } from '../hooks/useAuth'

/**
 * 系统说明书 + 更新日志。
 *
 * 内容来源 = 服务器上的 markdown 文件（~/pms/docs/*.md），后端用 pandoc 渲染成 HTML。
 * 所以**加一篇文档 / 改一段内容都不用动前端代码、不用重新构建**，改完刷新页面即可。
 */

type DocItem = { slug: string; title: string; summary: string; order: number; updated_at: number }
type DocBody = { slug: string; title: string; summary: string; updated_at: number; html: string }

const fmt = (ts: number) => new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false })

export default function SysDocsPage() {
  const { user } = useAuth()
  const authorized = !!user && user.username === '黄新博'   // 说明书仅限本人
  const [docs, setDocs] = useState<DocItem[]>([])
  const [cur, setCur] = useState<string>('')
  const [body, setBody] = useState<DocBody | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!authorized) return
    axios.get('/api/sysdocs').then(r => {
      if (!r.data?.ok) return
      const list: DocItem[] = r.data.docs || []
      setDocs(list)
      if (list.length) setCur(list[0].slug)
    }).catch(() => message.error('文档目录加载失败'))
  }, [authorized])

  useEffect(() => {
    if (!cur || !authorized) return
    setLoading(true)
    axios.get(`/api/sysdocs/${encodeURIComponent(cur)}`)
      .then(r => setBody(r.data?.ok ? r.data : null))
      .catch(() => message.error('文档加载失败'))
      .finally(() => setLoading(false))
  }, [cur, authorized])

  if (!authorized) {
    return (
      <Card>
        <Alert type="warning" showIcon message="无权访问"
          description="系统说明书仅对指定账号开放。" />
      </Card>
    )
  }

  return (
    <Layout style={{ background: 'transparent' }}>
      <Layout.Sider width={248} style={{ background: 'var(--pms-surface, #fff)', borderRadius: 8, marginRight: 16 }}>
        <div style={{ padding: '14px 16px 6px', fontWeight: 600, color: '#5f6368', fontSize: 13 }}>
          <BookOutlined style={{ marginRight: 6 }} />系统说明书
        </div>
        <Menu
          mode="inline"
          selectedKeys={[cur]}
          style={{ borderInlineEnd: 'none', background: 'transparent' }}
          onClick={e => setCur(e.key)}
          items={docs.map(d => ({
            key: d.slug,
            icon: d.slug.startsWith('99') ? <HistoryOutlined /> : <BookOutlined />,
            label: d.title,
          }))}
        />
      </Layout.Sider>

      <Layout.Content>
        <Card styles={{ body: { padding: '20px 28px' } }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
          ) : body ? (
            <>
              <Typography.Title level={3} style={{ marginTop: 0, marginBottom: 4 }}>{body.title}</Typography.Title>
              <div style={{ marginBottom: 16 }}>
                {body.summary && <Typography.Text type="secondary">{body.summary}</Typography.Text>}
                <Tag style={{ marginLeft: 10 }}>更新于 {fmt(body.updated_at)}</Tag>
              </div>
              <div className="sysdoc" dangerouslySetInnerHTML={{ __html: body.html }} />
            </>
          ) : <Empty description="暂无文档" />}
        </Card>
      </Layout.Content>

      <style>{`
        .sysdoc { line-height: 1.85; font-size: 14.5px; color: #1f2733; }
        .sysdoc h1 { font-size: 24px; margin: 26px 0 12px; padding-bottom: 8px; border-bottom: 2px solid #1a73e8; }
        .sysdoc h2 { font-size: 19px; margin: 26px 0 10px; color: #1a3f8f; }
        .sysdoc h3 { font-size: 16px; margin: 20px 0 8px; }
        .sysdoc p { margin: 10px 0; }
        .sysdoc ul, .sysdoc ol { padding-left: 24px; margin: 10px 0; }
        .sysdoc li { margin: 4px 0; }
        .sysdoc code { background: #f2f4f8; padding: 1px 6px; border-radius: 4px;
          font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; color: #c0341d; }
        .sysdoc pre { background: #1f2733; color: #e6e9ef; padding: 14px 16px; border-radius: 8px;
          overflow-x: auto; margin: 14px 0; }
        .sysdoc pre code { background: transparent; color: inherit; padding: 0; font-size: 13px; }
        .sysdoc table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 13.5px; display: block; overflow-x: auto; }
        .sysdoc th, .sysdoc td { border: 1px solid #dfe3ea; padding: 7px 11px; text-align: left; vertical-align: top; }
        .sysdoc th { background: #eef2fd; font-weight: 600; }
        .sysdoc blockquote { margin: 14px 0; padding: 10px 16px; background: #fff8e6;
          border-left: 4px solid #f0a020; color: #614700; }
        .sysdoc blockquote p { margin: 4px 0; }
        .sysdoc hr { border: 0; border-top: 1px solid #e4e8ee; margin: 26px 0; }
        .sysdoc a { color: #1a73e8; }
      `}</style>
    </Layout>
  )
}
