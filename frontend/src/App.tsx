import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { App as AntApp, ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AuthContext } from './hooks/useAuth'
import type { UserInfo } from './services/auth'
import { authMe } from './services/auth'
import AppLayout from './components/AppLayout'
import LoginPage from './pages/LoginPage'
import ProjectFlowPage from './pages/ProjectFlowPage'
import ProjectFormPage from './pages/ProjectFormPage'
import BidManagePage from './pages/BidManagePage'
import ChpwdPage from './pages/ChpwdPage'
import AuthLetterPage from './pages/AuthLetterPage'
import PeopleManagePage from './pages/PeopleManagePage'
import AnnouncementPage from './pages/AnnouncementPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null | undefined>(undefined)

  useEffect(() => {
    authMe()
      .then((res) => setUser(res.data.user))
      .catch(() => setUser(null))
  }, [])

  if (user === undefined) {
    return <Spin fullscreen tip="加载中..." />
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  return (
    <AuthContext.Provider value={{ user, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export default function App() {
  const [user, setUser] = useState<UserInfo | null>(null)

  return (
    <ConfigProvider locale={zhCN}>
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route
              path="/login"
              element={
                <AuthContext.Provider value={{ user, setUser }}>
                  <LoginPage />
                </AuthContext.Provider>
              }
            />
            <Route
              path="/*"
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="/flow" replace />} />
              <Route path="flow" element={<ProjectFlowPage />} />
              <Route path="new" element={<ProjectFormPage />} />
              <Route path="project/:id" element={<ProjectFormPage />} />
              <Route path="bid" element={<BidManagePage />} />
              <Route path="auth-letter" element={<AuthLetterPage />} />
              <Route path="people-manage" element={<PeopleManagePage />} />
              <Route path="announcement" element={<AnnouncementPage />} />
              <Route path="chpwd" element={<ChpwdPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}
