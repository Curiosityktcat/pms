import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'

/** 读取 URL 的 ?focus=<项目id>（待办「去处理」跳转时带上），无则 null。 */
export function useFocusId(): number | null {
  const [sp] = useSearchParams()
  const v = sp.get('focus')
  const n = v ? Number(v) : NaN
  return Number.isFinite(n) ? n : null
}

/** 滚动到并高亮闪烁 antd Table 中 data-row-key=rowKey 的那一行。 */
export function flashRow(rowKey: string | number) {
  setTimeout(() => {
    const el = document.querySelector(`[data-row-key="${rowKey}"]`) as HTMLElement | null
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const tds = Array.from(el.querySelectorAll('td')) as HTMLElement[]
    tds.forEach(td => {
      td.style.transition = 'background-color .5s'
      td.style.backgroundColor = '#fff1b8'   // antd gold-2
    })
    setTimeout(() => tds.forEach(td => { td.style.backgroundColor = '' }), 2000)
  }, 400)
}

/**
 * 数据就绪后对 ?focus 命中只执行一次定位回调（切页签 / 高亮行 / 预选项目）。
 * ready 通常传 `!loading && 数据已加载`。回调用 ref 持有，始终取最新闭包。
 */
export function useFocusTarget(ready: boolean, handle: (id: number) => void) {
  const focusId = useFocusId()
  const done = useRef(false)
  const handleRef = useRef(handle)
  handleRef.current = handle
  useEffect(() => {
    if (focusId != null && ready && !done.current) {
      done.current = true
      handleRef.current(focusId)
    }
  }, [focusId, ready])
}
