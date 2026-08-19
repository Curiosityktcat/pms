/**
 * 顶栏「在线人数」指示：人形图标 + 当前在线人数（只显示数字，不显示名单）。
 * 每次打开/刷新页面即上报一次并刷新人数（满足"刷新网页时刷新"）；
 * 另以 POLL_MS 轻量轮询，保持自身在线心跳、人数实时。
 */
import { useEffect, useState, useCallback } from 'react'
import { TeamOutlined } from '@ant-design/icons'
import { pingPresence } from '../services/presence'

const POLL_MS = 30000  // < 后端 WINDOW(120s)，确保挂着的页面不掉线

export default function OnlineCount() {
  const [count, setCount] = useState<number | null>(null)

  const ping = useCallback(async () => {
    try {
      setCount((await pingPresence()).data.data.count)
    } catch {
      // 原来这里是静默吞掉的，结果科室账号被闸门挡成 403 之后
      // 界面上永远是「在线人数 0 人」，看不出是坏了还是真没人
      // （2026-08-19 黄新博实测发现）。取不到就干脆不显示。
      setCount(null)
    }
  }, [])

  useEffect(() => {
    ping()
    const t = setInterval(ping, POLL_MS)
    return () => clearInterval(t)
  }, [ping])

  if (count === null) return null      // 取不到就不显示，别谎报 0

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      color: '#666', fontSize: 13, marginRight: 12, cursor: 'default',
    }}>
      <TeamOutlined style={{ fontSize: 16 }} />
      在线人数 {count} 人
    </span>
  )
}
