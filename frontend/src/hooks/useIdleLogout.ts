import { useEffect, useRef } from 'react'
import { authLogout } from '../services/auth'

// 空闲超时时长：30 分钟无任何用户操作即自动登出
export const IDLE_LIMIT_MS = 30 * 60 * 1000

// 视为“用户操作”的事件（后台轮询等网络请求不在此列，因此不会续期）
const ACTIVITY_EVENTS = [
  'mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart', 'click', 'wheel',
]

/**
 * 登录后启用空闲计时：用户连续 30 分钟无操作时，自动退出并跳转登录页。
 * @param enabled 仅在已登录时为 true
 */
export function useIdleLogout(enabled: boolean) {
  const timer = useRef<number | null>(null)
  const lastReset = useRef(0)

  useEffect(() => {
    if (!enabled) return

    const doLogout = async () => {
      try {
        await authLogout()
      } catch {
        // 后端可能已过期，忽略错误，照常跳转
      }
      window.location.href = '/login?expired=1'
    }

    const reset = () => {
      const now = Date.now()
      // 节流：1 秒内的连续操作不重复重置计时器
      if (now - lastReset.current < 1000) return
      lastReset.current = now
      if (timer.current) window.clearTimeout(timer.current)
      timer.current = window.setTimeout(doLogout, IDLE_LIMIT_MS)
    }

    ACTIVITY_EVENTS.forEach((e) =>
      window.addEventListener(e, reset, { passive: true }),
    )
    reset() // 启动计时

    return () => {
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, reset))
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [enabled])
}
