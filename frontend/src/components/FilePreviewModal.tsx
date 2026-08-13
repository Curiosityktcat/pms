import { useEffect, useRef, useState } from 'react'
import { Button, Spin, Result, Tooltip } from 'antd'
import {
  DownloadOutlined, PrinterOutlined, CloseOutlined,
  LeftOutlined, RightOutlined, ColumnWidthOutlined,
} from '@ant-design/icons'

/** 取文件扩展名（小写，不含点） */
export function fileExt(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}

const IMAGE_EXT = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg']
const TEXT_EXT = ['txt', 'csv', 'log', 'md', 'json', 'xml']
// 旧二进制 Office 格式：前端无渲染器，后端用 LibreOffice 转 PDF 预览
const LEGACY_OFFICE_EXT = ['doc', 'ppt', 'pptx', 'wps', 'et', 'dps', 'rtf']

/** 在 URL 上追加 pdf=1，请求后端把 Office 文档转 PDF 后返回 */
function withPdf(url: string): string {
  return url + (url.includes('?') ? '&' : '?') + 'pdf=1'
}

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
    LEGACY_OFFICE_EXT.includes(e) ||
    TEXT_EXT.includes(e)
  )
}

/** 面板里的一件文件。给 siblings 用，字段和单件预览一致。 */
export type PreviewItem = {
  url: string
  filename: string
  downloadUrl?: string
}

type Props = {
  open: boolean
  url: string          // 后端内联预览地址（as_attachment=False）
  filename: string
  downloadUrl?: string // 下载地址，兜底/工具栏使用，默认同 url
  showPrint?: boolean  // 显示「打印」按钮（docx/html 预览，新窗口打印）
  compactDocx?: boolean // docx 预览收紧行距（模板用 EXACTLY 大行距时浏览器渲染过松）
  onClose: () => void
  // ── 下面几个都是可选的，老调用点一行都不用改 ──
  siblings?: PreviewItem[]            // 同一批文件，给「上一件 / 下一件」用
  index?: number                      // 当前是第几件（siblings 里的下标）
  onNavigate?: (i: number) => void    // 翻到第几件；不给就不显示翻页
  extra?: React.ReactNode             // 塞在底栏左边的业务按钮（如合格 / 不合格）
}

// ── 面板宽度 ──────────────────────────────────────────────────────────
const W_KEY = 'pms-pv-w'
const W_MIN = 360
const W_DEF = 620
// 比这个窄的屏幕（手机、小笔记本分屏）没法左右分栏，面板铺满、不给主区留位。
const NARROW = 860

function clampW(w: number): number {
  return Math.min(Math.max(w, W_MIN), Math.max(window.innerWidth - 320, W_MIN))
}

function savedW(): number {
  const n = parseInt(localStorage.getItem(W_KEY) || '', 10)
  return clampW(Number.isFinite(n) && n > 0 ? n : W_DEF)
}

/**
 * 面板占了右边一条，主区得往左让，不然表格右半截被压住、看不见也点不着。
 *
 * 这里用一个全局 class + CSS 变量来让位，而不是去改 AppLayout：
 * 预览被 18 处地方调用，其中好几处是在弹窗**里面**开的，改布局组件管不到它们。
 * `.ant-modal-wrap` 也要一起让——antd 的弹窗是在那一层居中的，
 * 不给它加内边距，弹窗就会被面板压掉右半边。
 */
let openCount = 0
function holdRoom(w: number) {
  openCount += 1
  document.body.style.setProperty('--pms-pv-w', w + 'px')
  document.body.classList.add('pms-pv-open')
}
function setRoom(w: number) {
  document.body.style.setProperty('--pms-pv-w', w + 'px')
}
function freeRoom() {
  openCount = Math.max(0, openCount - 1)
  if (openCount === 0) document.body.classList.remove('pms-pv-open')
}

const CSS = `
.pms-pv{position:fixed;top:0;right:0;bottom:0;width:var(--pms-pv-w,620px);
  background:#fff;z-index:1200;display:flex;flex-direction:column;
  box-shadow:-4px 0 16px rgba(0,0,0,.12);border-left:1px solid var(--pms-border,#e8e8e8)}
.pms-pv.full{width:100vw}
.pms-pv-grip{position:absolute;left:0;top:0;bottom:0;width:6px;cursor:col-resize;
  z-index:3;touch-action:none;outline:none;background:transparent}
.pms-pv-grip:hover,.pms-pv-grip:focus-visible{background:#1a73e8;opacity:.35}
.pms-pv-head{flex:none;display:flex;align-items:center;gap:8px;padding:8px 10px 8px 14px;
  border-bottom:1px solid var(--pms-border,#e8e8e8);background:var(--pms-surface,#fff)}
.pms-pv-name{flex:1;min-width:0;font-size:13px;font-weight:500;color:#333;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pms-pv-body{flex:1;min-height:0;overflow:auto;background:#f5f5f5}
.pms-pv-foot{flex:none;display:flex;align-items:center;gap:8px;padding:8px 12px;
  border-top:1px solid var(--pms-border,#e8e8e8);background:var(--pms-surface,#fff)}
/* 拖动那几百毫秒盖住整屏：面板里装着 iframe（PDF 预览），
   不盖住的话鼠标一进 iframe，抬手的事件就被它自己的文档吃掉了。 */
.pms-pv-shield{display:none}
.pms-pv-shield.on{display:block;position:fixed;inset:0;z-index:1300;cursor:col-resize}
/* 让位：主区和 antd 弹窗都往左缩一条。
   内边距加在 #root 上，不加在 .ant-layout 上——后者要赌「#root 的第一个孩子
   一定是 ant-layout」，将来外面套个 Provider 或 div 就悄悄失效了，
   而且 /admin 走的是另一套布局组件。加在 #root 上跟内部结构无关。 */
body.pms-pv-open > #root{padding-right:var(--pms-pv-w,620px)}
body.pms-pv-open .ant-modal-wrap{padding-right:var(--pms-pv-w,620px)}
/* 右侧抽屉也得挪：它和面板抢同一条地方，不挪就整个被压在面板底下。
   附件列表在抽屉里、文件在面板里，这两个本来就该并排看——
   项目分发那一屏就是这么用的（一边点附件一边看内容）。 */
body.pms-pv-open .ant-drawer-right > .ant-drawer-content-wrapper{right:var(--pms-pv-w,620px)}
`

let cssDone = false
function injectCss() {
  if (cssDone) return
  cssDone = true
  const s = document.createElement('style')
  s.setAttribute('data-pms-pv', '1')
  s.textContent = CSS
  document.head.appendChild(s)
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
 * 通用在线预览侧栏。按扩展名选择渲染方式：
 * - 图片：直接贴在面板里（可切原始大小）
 * - PDF：浏览器原生 iframe
 * - docx：docx-preview 前端渲染
 * - xls/xlsx：SheetJS 渲染成表格
 * - 文本：<pre> 展示
 * - 其它：提示下载
 *
 * 为什么是侧栏不是弹窗：办文件的人要**边看边填**——看着投标文件在表单里录数字、
 * 对着附件在列表里判合格。弹窗一开就把底下全遮住、还带一层遮罩点不着，
 * 只能看一眼关掉、再点开下一件，一份材料来回开关十几次。
 * 侧栏没有遮罩，主区照样能点，宽度自己拖，习惯记住。
 *
 * 组件名和对外的 props 都没动（还叫 FilePreviewModal），
 * 所以那 18 处调用一行都不用改——这套系统医院天天在用，改动面越小越好。
 */
export default function FilePreviewModal({
  open, url, filename, downloadUrl, showPrint, compactDocx, onClose,
  siblings, index, onNavigate, extra,
}: Props) {
  const ext = fileExt(filename)
  const dl = downloadUrl || url
  const canPrint = !!showPrint && (ext === 'docx' || ext === 'html' || ext === 'htm')

  const [w, setW] = useState(savedW)
  const [narrow, setNarrow] = useState(() => window.innerWidth < NARROW)
  const pvRef = useRef<HTMLElement>(null)
  const gripRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  // 拖动的事件处理器只绑一次，里面拿不到最新的 w（闭包锁在初次渲染那一刻），
  // 所以额外留一份 ref 给它读。
  const wRef = useRef(w)
  wRef.current = w

  useEffect(() => { injectCss() }, [])

  // 窄屏铺满，宽屏按记住的宽度；窗口大小变了要重新夹一遍，
  // 否则从大屏挪到小屏，面板会比屏幕还宽、关闭按钮点不到。
  useEffect(() => {
    const onResize = () => {
      setNarrow(window.innerWidth < NARROW)
      setW(v => clampW(v))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // 只有宽屏才给主区让位；窄屏面板本来就铺满，让位等于把主区挤成零宽。
  useEffect(() => {
    if (!open || narrow) return
    holdRoom(w)
    return () => freeRoom()
  }, [open, narrow])          // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (open && !narrow) setRoom(w) }, [w, open, narrow])

  // Esc 关闭。
  //
  // 监听只能跟着 open 挂一次，**不能**把 onClose 写进依赖里。调用方给的 onClose
  // 基本都是现写的箭头函数，每次渲染都是新身份；一放进依赖，每次渲染都会
  // 摘掉再重挂一遍。平时看不出来，碰到「同一个 Esc 也被别人处理」就露馅：
  // antd 抽屉自己也收 Esc，它一关就触发重渲染，把我这个监听在**事件正在派发的
  // 半路上**摘走了——浏览器不会把当前这个事件补给新挂上去的监听，于是第一下
  // Esc 丢掉，得按第二下才关。所以真正要用的 onClose 从 ref 里现取。
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  // ── 拖左边框改宽度 ──────────────────────────────────────────────────
  //
  // 必须用「指针捕获」，不能把 mousemove/mouseup 挂在 document 上：
  // 面板里装的是 iframe（PDF 预览），一按住把手往面板里动，鼠标就进了 iframe，
  // 抬手的事件被 iframe 自己的文档吃掉，外层永远收不到——于是松了手还在拖，
  // 之后鼠标一动就跟着改宽度，只能刷页面。OPMS 上真出过这个故障，用户报的。
  // 捕获之后事件全归把手，iframe 抢不走；再加一层遮罩兜底。
  useEffect(() => {
    const grip = gripRef.current
    if (!grip) return
    let on = false

    const end = () => {
      if (!on) return
      on = false
      setDragging(false)
      document.body.style.userSelect = ''
      // 存最新宽度。这里读 ref 而不是回头去量 DOM——量 DOM 得赌那条 CSS 变量
      // 已经刷上去了，窄屏下我们根本不设它，一读就拿到空值存成默认宽。
      localStorage.setItem(W_KEY, String(wRef.current))
    }
    const down = (e: PointerEvent) => {
      if (e.button !== 0) return          // 只认左键，右键别当拖动
      on = true
      setDragging(true)
      e.preventDefault()
      document.body.style.userSelect = 'none'
      try { grip.setPointerCapture(e.pointerId) } catch { /* 老浏览器没有就算了 */ }
    }
    const move = (e: PointerEvent) => {
      if (!on) return
      // 自愈：万一还是漏了一次抬起（切窗口、被别的东西打断），
      // 发现鼠标键其实已经松了就立刻收工，绝不留一个粘住的拖动状态。
      if (!e.buttons) { end(); return }
      setW(clampW(window.innerWidth - e.clientX))
    }
    const key = (e: KeyboardEvent) => {
      const d = e.key === 'ArrowLeft' ? 24 : (e.key === 'ArrowRight' ? -24 : 0)
      if (!d) return
      e.preventDefault()
      setW(v => {
        const nw = clampW(v + d)
        localStorage.setItem(W_KEY, String(nw))
        return nw
      })
    }

    grip.addEventListener('pointerdown', down)
    grip.addEventListener('pointermove', move)
    grip.addEventListener('pointerup', end)
    grip.addEventListener('pointercancel', end)
    grip.addEventListener('lostpointercapture', end)
    grip.addEventListener('keydown', key)
    return () => {
      grip.removeEventListener('pointerdown', down)
      grip.removeEventListener('pointermove', move)
      grip.removeEventListener('pointerup', end)
      grip.removeEventListener('pointercancel', end)
      grip.removeEventListener('lostpointercapture', end)
      grip.removeEventListener('keydown', key)
      // 卸载时把拖动留下的痕迹都收掉，别让整页选不中字
      document.body.style.userSelect = ''
    }
  }, [open])

  if (!open) return null

  // 翻页：只有调用方给了 siblings + onNavigate 才出现
  const n = siblings?.length || 0
  const i = typeof index === 'number' ? index : -1
  const canNav = !!onNavigate && n > 1 && i >= 0
  const go = (d: number) => { if (onNavigate) onNavigate((i + d + n) % n) }

  const wide = () => {
    const target = w > window.innerWidth * 0.72 ? W_DEF : clampW(window.innerWidth - 320)
    setW(target)
    localStorage.setItem(W_KEY, String(target))
  }

  return (
    <>
      <aside
        ref={pvRef}
        className={'pms-pv' + (narrow ? ' full' : '')}
        style={narrow ? undefined : { width: w }}
      >
        {!narrow && (
          <div
            ref={gripRef}
            className="pms-pv-grip"
            tabIndex={0}
            role="separator"
            aria-label="拖动调整预览宽度"
            title="拖动调整宽度（聚焦后可用左右方向键）"
          />
        )}
        <div className="pms-pv-head">
          {canNav && (
            <>
              <Tooltip title="上一件">
                <Button size="small" type="text" icon={<LeftOutlined />} onClick={() => go(-1)} />
              </Tooltip>
              <span style={{ fontSize: 12, color: '#888', whiteSpace: 'nowrap' }}>{i + 1}/{n}</span>
              <Tooltip title="下一件">
                <Button size="small" type="text" icon={<RightOutlined />} onClick={() => go(1)} />
              </Tooltip>
            </>
          )}
          <div className="pms-pv-name" title={filename}>{filename}</div>
          {!narrow && (
            <Tooltip title="放宽 / 收窄">
              <Button size="small" type="text" icon={<ColumnWidthOutlined />} onClick={wide} />
            </Tooltip>
          )}
          <Tooltip title="关闭（Esc）">
            <Button size="small" type="text" icon={<CloseOutlined />} onClick={onClose} />
          </Tooltip>
        </div>
        <div className="pms-pv-body">
          <PreviewBody url={url} filename={filename} ext={ext} dl={dl} compactDocx={compactDocx} />
        </div>
        <div className="pms-pv-foot">
          {extra}
          <div style={{ flex: 1 }} />
          {canPrint && (
            <Button size="small" type="primary" icon={<PrinterOutlined />} onClick={() => printPreview(filename)}>
              打印
            </Button>
          )}
          <Button size="small" icon={<DownloadOutlined />} href={dl} download={filename}>下载</Button>
          <Button size="small" onClick={onClose}>关闭</Button>
        </div>
      </aside>
      <div className={'pms-pv-shield' + (dragging ? ' on' : '')} />
    </>
  )
}


function PdfFrame({ url, filename }: { url: string; filename: string }) {
  return <iframe src={url} title={filename} style={{ width: '100%', height: '100%', border: 'none', display: 'block' }} />
}

function PreviewBody({ url, filename, ext, dl, compactDocx }: { url: string; filename: string; ext: string; dl: string; compactDocx?: boolean }) {
  // docx/xls(x) 客户端渲染失败时，可切换为「服务端转 PDF」兜底
  const [pdfFallback, setPdfFallback] = useState(false)
  // 换文件时要把兜底状态清掉，否则翻到下一件还停在「转 PDF」模式
  useEffect(() => { setPdfFallback(false) }, [url])
  if (IMAGE_EXT.includes(ext)) return <ImageView url={url} filename={filename} />
  if (ext === 'pdf') return <PdfFrame url={url} filename={filename} />
  // 旧二进制 Office：后端自动转 PDF，直接用 iframe 预览
  if (LEGACY_OFFICE_EXT.includes(ext)) return <PdfFrame url={withPdf(url)} filename={filename} />
  if (ext === 'html' || ext === 'htm') return <HtmlView url={url} dl={dl} />
  if (pdfFallback && (ext === 'docx' || ext === 'xlsx' || ext === 'xls')) {
    return <PdfFrame url={withPdf(url)} filename={filename} />
  }
  if (ext === 'docx') return <DocxView url={url} dl={dl} compact={compactDocx} onPdfFallback={() => setPdfFallback(true)} />
  if (ext === 'xlsx' || ext === 'xls') return <ExcelView url={url} dl={dl} onPdfFallback={() => setPdfFallback(true)} />
  if (TEXT_EXT.includes(ext)) return <TextView url={url} />
  return <Unsupported dl={dl} filename={filename} />
}

/**
 * 图片贴在面板里看，不再弹全屏。
 * 默认按面板宽度缩放（一眼看全），点一下切到原始大小看细节——
 * 证件扫描件上的编号、印章要凑近看，缩放过的图上认不出来。
 */
function ImageView({ url, filename }: { url: string; filename: string }) {
  const [raw, setRaw] = useState(false)
  return (
    <div style={{ padding: 8, background: '#f5f5f5', minHeight: '100%', textAlign: 'center' }}>
      <img
        src={url}
        alt={filename}
        onClick={() => setRaw(v => !v)}
        title={raw ? '点击缩放到面板宽度' : '点击看原始大小'}
        style={{
          maxWidth: raw ? 'none' : '100%',
          cursor: raw ? 'zoom-out' : 'zoom-in',
          background: '#fff',
        }}
      />
    </div>
  )
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
  return <div style={{ height: '100%', minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{children}</div>
}

function DocxView({ url, dl, compact, onPdfFallback }: { url: string; dl: string; compact?: boolean; onPdfFallback?: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [renderErr, setRenderErr] = useState(false)
  const { loading, error, buf } = useFileBuffer(url)
  useEffect(() => { setRenderErr(false) }, [url])
  useEffect(() => {
    if (!buf || !ref.current) return
    ref.current.innerHTML = ''
    import('docx-preview')
      .then(({ renderAsync }) => renderAsync(buf, ref.current!, undefined, {
        className: 'docx', inWrapper: true, ignoreWidth: false,
      }))
      .catch(() => setRenderErr(true))
  }, [buf])

  // docx 是按 A4 的真实宽度铺的（≈794px），面板比这窄的时候右边一截就被切掉，
  // 得横向拖着看——原来那个弹窗有 80% 屏宽，所以从没露出来过。
  //
  // 这里按面板宽度整体缩一下，版式不动（不重排——重排会把套打好的表格和
  // 签章位置挪位，核对的时候就不能信了）。用 zoom 而不是 transform：
  // zoom 会重新参与布局，滚动条量得准；transform 缩完外面还按原尺寸算，
  // 底下会多出一大片空白。放不满一页宽就不放大，只缩不放。
  const natural = useRef(0)
  useEffect(() => {
    const box = ref.current
    const host = box?.parentElement
    if (!box || !host) return
    natural.current = 0
    const fit = () => {
      const page = box.querySelector('section.docx') as HTMLElement | null
      if (!page) return
      if (!natural.current) {
        // 原始页宽只量一次，而且必须在没缩之前量——缩过之后再量就越量越小。
        box.style.zoom = ''
        natural.current = page.offsetWidth
      }
      const avail = host.clientWidth - 24
      if (natural.current > 0 && avail > 0) {
        box.style.zoom = String(Math.max(Math.min(avail / natural.current, 1), 0.3))
      }
    }
    fit()
    // 面板宽度是能拖的，拖完要重新算一遍。
    // 注意观察的是**外层**容器，不是 box 自己：改 box 的 zoom 会改它自己的尺寸，
    // 观察自己就成了自激循环（改→通知→再改），一按住把手拖就卡死。
    const ro = new ResizeObserver(fit)
    ro.observe(host)
    const timer = window.setTimeout(fit, 400)   // 渲染是异步的，补一次
    return () => { ro.disconnect(); window.clearTimeout(timer) }
  }, [buf])
  if (loading) return <Centered><Spin tip="加载中…" /></Centered>
  if (error || renderErr) return <LoadError dl={dl} onPdfFallback={onPdfFallback} />
  return <div ref={ref} className={compact ? 'docx-compact' : undefined} style={{ padding: 16, background: '#f5f5f5' }} />
}

function ExcelView({ url, dl, onPdfFallback }: { url: string; dl: string; onPdfFallback?: () => void }) {
  const [html, setHtml] = useState('')
  const [renderErr, setRenderErr] = useState(false)
  const { loading, error, buf } = useFileBuffer(url)
  useEffect(() => { setRenderErr(false); setHtml('') }, [url])
  useEffect(() => {
    if (!buf) return
    import('xlsx').then(XLSX => {
      const wb = XLSX.read(buf, { type: 'array' })
      const parts = wb.SheetNames.map(name => {
        const table = XLSX.utils.sheet_to_html(wb.Sheets[name])
        return `<h4 style="margin:12px 8px 4px">${name}</h4>${table}`
      })
      if (!parts.length) throw new Error('empty')
      setHtml(parts.join(''))
    }).catch(() => setRenderErr(true))
  }, [buf])
  if (loading) return <Centered><Spin tip="加载中…" /></Centered>
  if (error || renderErr) return <LoadError dl={dl} onPdfFallback={onPdfFallback} />
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

function LoadError({ dl, onPdfFallback }: { dl: string; onPdfFallback?: () => void }) {
  return (
    <Centered>
      <Result
        status="warning"
        title={onPdfFallback ? '前端渲染失败，可试试服务器转 PDF 预览' : '文件加载失败'}
        extra={[
          onPdfFallback && (
            <Button key="pdf" type="primary" onClick={onPdfFallback}>转 PDF 预览</Button>
          ),
          <Button key="dl" icon={<DownloadOutlined />} href={dl}>下载文件</Button>,
        ]}
      />
    </Centered>
  )
}
