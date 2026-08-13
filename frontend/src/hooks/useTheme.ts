import { createContext, useContext } from 'react'

// 主题：浅色 / 暖色护眼（深色已移除）
export type ThemeMode = 'light' | 'sepia'

export const ThemeContext = createContext<{ mode: ThemeMode; setMode: (m: ThemeMode) => void }>({
  mode: 'light',
  setMode: () => {},
})

export const useTheme = () => useContext(ThemeContext)
