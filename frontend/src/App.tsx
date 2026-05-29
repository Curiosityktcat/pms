import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { App as AntApp, ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AuthContext } from './hooks/useAuth'
import type { UserInfo } from './services/auth'
import { authMe } from './services/auth'
import AppLayout from './components/AppLayout'
import AdminLayout from './components/AdminLayout'
import LoginPage from './pages/LoginPage'
import ProjectFlowPage from './pages/ProjectFlowPage'
import ProjectFormPage from './pages/ProjectFormPage'
import BidManagePage from './pages/BidManagePage'
import BidBoardPage from './pages/BidBoardPage'
import ChpwdPage from './pages/ChpwdPage'
import AuthLetterPage from './pages/AuthLetterPage'
import PeopleManagePage from './pages/PeopleManagePage'
import AnnouncementPage from './pages/AnnouncementPage'
import PublicAnnouncementDetailPage from './pages/PublicAnnouncementDetailPage'
import ProcurementDemandPage from './pages/ProcurementDemandPage'
import ProcurementResultPage from './pages/ProcurementResultPage'
import ContractPage from './pages/ContractPage'
import InternalBidDemandPage from './pages/InternalBidDemandPage'
import InquiryPage from './pages/InquiryPage'
import AgencyAgreementPage from './pages/AgencyAgreementPage'
import ProcurementDocPage from './pages/ProcurementDocPage'
import TemplateManagePage from './pages/TemplateManagePage'
import ArchivePage from './pages/ArchivePage'
import EmailSettingsPage from './pages/EmailSettingsPage'
import ScraperSettingsPage from './pages/ScraperSettingsPage'
import PermissionManagePage from './pages/PermissionManagePage'

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
            {/* 公开公告详情页 — 无需登录 */}
            <Route
              path="/public/announcement/:id"
              element={<PublicAnnouncementDetailPage />}
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
              <Route path="bid-board" element={<BidBoardPage />} />
              <Route path="auth-letter" element={<AuthLetterPage />} />
              <Route path="people-manage" element={<PeopleManagePage />} />
              <Route path="template-manage" element={<TemplateManagePage />} />
              <Route path="announcement" element={<AnnouncementPage />} />
              {/* 采购需求编制：无 type 参数时显示总览（供助理分发用） */}
              <Route path="procurement-demand" element={<ProcurementDemandPage />} />
              {/* 各类型子板块：gov / competition / sole_source / inquiry / emergency */}
              <Route path="procurement-demand/:type" element={<ProcurementDemandPage />} />
              <Route path="procurement-result" element={<ProcurementResultPage />} />
              <Route path="contract" element={<ContractPage />} />
              <Route path="internal-bid-demand" element={<InternalBidDemandPage />} />
              <Route path="inquiry" element={<InquiryPage />} />
              <Route path="agency-agreement" element={<AgencyAgreementPage />} />
              <Route path="procurement-doc" element={<ProcurementDocPage />} />
              <Route path="archive" element={<ArchivePage />} />
              <Route path="chpwd" element={<ChpwdPage />} />
            </Route>
            {/* 后台管理系统 — 与业务系统独立的一套界面，仅管理员可进入 */}
            <Route
              path="/admin/*"
              element={
                <RequireAuth>
                  <AdminLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="permissions" replace />} />
              <Route path="permissions" element={<PermissionManagePage />} />
              <Route path="model" element={<ScraperSettingsPage />} />
              <Route path="email" element={<EmailSettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}
