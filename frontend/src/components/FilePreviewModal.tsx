import { useEffect, useRef, useState } from 'react'
import { Modal, Button, Image, Spin, Result } from 'antd'
import { DownloadOutlined, PrinterOutlined } from '@ant-design/icons'

/** 取文件扩展名（小写，不含点） */
export function fileExt(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}

const IMAGE_EXT = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg']
const TEXT_EXT = ['txt', 'csv', 'log', 'md', 'json', 'xml']

/** 是否支持在线预览（其余类型只能下载） */
export function isPreviewable(name: string): boolean {
  const e = fileExt(name)
  return (
    IMAGE_EXT.includes(e) ||
    e === 'pdf' ||
    e === 'docx' ||
    e === 'xlsx' ||
    e === 'xls' ||
    e === 'html' ||
    e === 'htm' ||
    TEXT_EXT.includes(e)
  )
}

type Props = {
  open: boolean
  url: string          // 后端内联预览地址（as_attachment=False）
  filename: string
  downloadUrl?: string // 下载地址，兜底/工具栏使用，默认同 url
  showPrint?: boolean  // 显示「打印」按钮（docx/html 预览，新窗口打印）
  compactDocx?: boolean // docx 预览收紧行距（模板用 EXACTLY 大行距时浏览器渲染过松）
  onClose: () => void
}

/** 把预览区渲染好的内容拷到新窗口直接打印（保留 docx-preview 的版式样式）。 */
function printPreview(filename: string) {
  const node =
    (document.querySelector('.docx-wrapper') as HTMLElement | null) ||
    (document.querySelector('.file-preview-html') as HTMLElement | null)
  if (!node) return
  const win = window.open('', '_blank', 'width=900,height=1200')
  if (!win) return
  const styles = Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
    .map((s) => s.outerHTML)
    .join('')
  win.document.write(
    `<html><head><title>${filename}</title>${styles}` +
      '<style>@page{margin:0}body{margin:0;background:#fff}.docx-wrapper{background:#fff!important;padding:0!important}</style>' +
      `</head><body>${node.outerHTML}</body></html>`,
  )
  win.document.close()
  win.focus()
  const fire = () => { try { win.print() } catch { /* ignore */ } }
  win.onload = fire
  setTimeout(fire, 600)
}

/**
 * 通用在线预览弹窗。按扩展名选择渲染方式：
 * - 图片：antd Image 预览
 * - PDF：浏览器原生 iframe
 * - docx：docx-preview 前端渲染
 * - xls/xlsx：SheetJS 渲染成表格
 * - 文本：<pre> 展示
 * - 其它：提示下载
 */
export default function FilePreviewModal({ open, url, filename, downloadUrl, showPrint, compactDocx, onClose }: Props) {
  const ext = fileExt(filename)
  const isImage = IMAGE_EXT.includes(ext)
  const dl = downloadUrl || url
  const canPrint = !!showPrint && (ext === 'docx' || ext === 'html' || ext === 'htm')

  // 图片走 antd 的 Image 预览组件（独立处理，不渲染 Modal）
  if (isImage) {
    return (
      <Image
        style={{ display: 'none' }}
        preview={{ visible: open, src: url, onVisibleChange: (v) => { if (!v) onClose() } }}
      />
    )
  }

  return (
    <Modal
      open={open}
      title={filename}
      onCancel={onClose}
      width="80%"
      style={{ top: 20 }}
      styles={{ body: { padding: 0, height: '75vh', overflow: 'auto', background: '#f5f5f5' } }}
      footer={[
        canPrint && (
          <Button key="print" type="primary" icon={<PrinterOutlined />} onClick={() => printPreview(filename)}>
            打印
          </Button>
        ),
        <Button key="dl" icon={<DownloadOutlined />} href={dl} download={filename}>
          下载
        </Button>,
        <Button key="close" onClick={onClose}>关闭</Button>,
      ]}
      destroyOnHidden
    >
      {open && <PreviewBody url={url} filename={filename} ext={ext} dl={dl} compactDocx={compactDocx} />}
    </Modal>
  )
}


function PreviewBody({ url, filename, ext, dl, compactDocx }: { url: string; filename: string; ext: string; dl: string; compactDocx?: boolean }) {
  if (ext === 'pdf') {
    return <iframe src={url} title={filename} style={{ width: '100%', height: '75vh', border: 'none' }} />
  }
  if (ext === 'html' || ext === 'htm') return <HtmlView url={url} dl={dl} />
  if (ext === 'docx') return <DocxView url={url} dl={dl} compact={compactDocx} />
  if (ext === 'xlsx' || ext === 'xls') return <ExcelView url={url} dl={dl} />
  if (TEXT_EXT.includes(ext)) return <TextView url={url} />
  return <Unsupported dl={dl} filename={filename} />
}

function useFileBuffer(url: string) {
  const [state, setState] = useState<{ loading: boolean; error: string; buf: ArrayBuffer | null }>({
    loading: true, error: '', buf: null,
  })
  useEffect(() => {
    let alive = true
    setState({ loading: true, error: '', buf: null })
    fetch(url, { credentials: 'include' })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        // 后端正常返回文件流；若拿到 HTML/JSON，说明接口未命中或未登录，
        // 不能交给渲染器（会误报“渲染失败”）。
        const ct = r.headers.get('content-type') || ''
        if (ct.includes('text/html') || ct.includes('application/json')) {
          throw new Error('未获取到文件内容')
        }
        return r.arrayBuffer()
      })
      .then(buf => { if (alive) setState({ loading: false, error: '', buf }) })
      .catch(e => { if (alive) setState({ loading: false, error: String(e?.message || e), buf: null }) })
    return () => { alive = false }
  }, [url])
  return state
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div style={{ height: '75vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{children}</div>
}

function DocxView({ url, dl, compact }: { url: string; dl: string; compact?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const { loading, error, buf } = useFileBuffer(url)
  useEffect(() => {
    if (!buf || !ref.current) return
    ref.current.innerHTML = ''
    import('docx-preview')
      .then(({ renderAsync }) => renderAsync(buf, ref.current!, undefined, {
        className: 'docx', inWrapper: true, ignoreWidth: false,
      }))
      .catch(() => { if (ref.current) ref.current.innerHTML = '<p style="padding:24px;color:#999">渲染失败，请下载查看</p>' })
  }, [buf])
  if (loading) return <Centered><Spin tip="加载中…" /></Centered>
  if (error) return <LoadError dl={dl} />
  return <div ref={ref} className={compact ? 'docx-compact' : undefined} style={{ padding: 16, background: '#f5f5f5' }} />
}

function ExcelView({ url, dl }: { url: string; dl: string }) {
  const [html, setHtml] = useState('')
  const { loading, error, buf } = useFileBuffer(url)
  useEffect(() => {
    if (!buf) return
    import('xlsx').then(XLSX => {
      const wb = XLSX.read(buf, { type: 'array' })
      const parts = wb.SheetNames.map(name => {
        const table = XLSX.utils.sheet_to_html(wb.Sheets[name])
        return `<h4 style="margin:12px 8px 4px">${name}</h4>${table}`
      })
      setHtml(parts.join(''))
    }).catch(() => setHtml(''))
  }, [buf])
  if (loading) return <Centered><Spin tip="加载中…" /></Centered>
  if (error) return <LoadError dl={dl} />
  return (
    <div style={{ padding: 8, background: '#fff', minHeight: '100%' }} className="excel-preview">
      <style>{`
        .excel-preview table { border-collapse: collapse; font-size: 13px; }
        .excel-preview td, .excel-preview th { border: 1px solid #ddd; padding: 3px 8px; white-space: nowrap; }
      `}</style>
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  )
}

function HtmlView({ url, dl }: { url: string; dl: string }) {
  // 政府公告等 HTML：抓文本后渲染到 div（不走 iframe，避开 Chrome 对带防护脚本的
  // iframe 的屏蔽；注入的 <script> 不会执行，<style> 仅作用于本预览区）。
  const [htmlStr, setHtmlStr] = useState('')
  const [state, setState] = useState<'loading' | 'ok' | 'err'>('loading')
  useEffect(() => {
    let alive = true
    setState('loading')
    fetch(url, { credentials: 'include' })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
      .then(t => { if (alive) { setHtmlStr(t); setState('ok') } })
      .catch(() => { if (alive) setState('err') })
    return () => { alive = false }
  }, [url])
  if (state === 'loading') return <Centered><Spin tip="加载中…" /></Centered>
  if (state === 'err') return <LoadError dl={dl} />
  return (
    <div className="file-preview-html" style={{ padding: 16, background: '#fff', minHeight: '100%' }}>
      <div dangerouslySetInnerHTML={{ __html: htmlStr }} />
    </div>
  )
}

function TextView({ url }: { url: string }) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    setLoading(true)
    fetch(url, { credentials: 'include' })
      .then(r => r.text())
      .then(t => { if (alive) { setText(t); setLoading(false) } })
      .catch(() => { if (alive) setLoading(false) })
  }, [url])
  if (loading) return <Centered><Spin tip="加载中…" /></Centered>
  return (
    <pre style={{ padding: 16, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 13, background: '#fff', minHeight: '100%' }}>
      {text}
    </pre>
  )
}

function Unsupported({ dl, filename }: { dl: string; filename: string }) {
  return (
    <Centered>
      <Result
        status="info"
        title="该文件类型暂不支持在线预览"
        subTitle="请下载后查看"
        extra={<Button type="primary" icon={<DownloadOutlined />} href={dl} download={filename}>下载文件</Button>}
      />
    </Centered>
  )
}

function LoadError({ dl }: { dl: string }) {
  return (
    <Centered>
      <Result
        status="warning"
        title="文件加载失败"
        extra={<Button type="primary" icon={<DownloadOutlined />} href={dl}>下载文件</Button>}
      />
    </Centered>
  )
}
