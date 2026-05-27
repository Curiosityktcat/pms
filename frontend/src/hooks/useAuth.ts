import { createContext, useContext } from 'react'
import type { UserInfo } from '../services/auth'

export interface AuthContextValue {
  user: UserInfo | null
  setUser: (u: UserInfo | null) => void
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  setUser: () => {},
})

export const useAuth = () => useContext(AuthContext)
