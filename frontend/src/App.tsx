import { useState, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { App as AntApp, ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AuthContext } from './hooks/useAuth'
import { ThemeContext, type ThemeMode } from './hooks/useTheme'
import { useIdleLogout } from './hooks/useIdleLogout'
import type { UserInfo } from './services/auth'
import { authMe } from './services/auth'
import AppLayout from './components/AppLayout'
import AdminLayout from './components/AdminLayout'
import LoginPage from './pages/LoginPage'
// 业务页按路由懒加载，缩小首屏包体（移动端尤其受益）
const ProjectFlowPage = lazy(() => import('./pages/ProjectFlowPage'))
const ProjectFormPage = lazy(() => import('./pages/ProjectFormPage'))
const BidManagePage = lazy(() => import('./pages/BidManagePage'))
const BidBoardPage = lazy(() => import('./pages/BidBoardPage'))
const ChpwdPage = lazy(() => import('./pages/ChpwdPage'))
const SupervisionPage = lazy(() => import('./pages/SupervisionPage'))  // 投诉质疑数据库
const AuthLetterPage = lazy(() => import('./pages/AuthLetterPage'))
const ProcurementPlanPage = lazy(() => import('./pages/ProcurementPlanPage'))  // 1.0 采购计划池
const DeptPortalPage = lazy(() => import('./pages/DeptPortalPage'))  // 科室门户（归口科室只读）
const AgencyManagePage = lazy(() => import('./pages/AgencyManagePage'))
const AgencyAssessmentPage = lazy(() => import('./pages/AgencyAssessmentPage'))
const SurveySingleSourcePage = lazy(() => import('./pages/SurveySingleSourcePage'))
const PeopleManagePage = lazy(() => import('./pages/PeopleManagePage'))
const AnnouncementPage = lazy(() => import('./pages/AnnouncementPage'))
const CorrectionAnnouncementPage = lazy(() => import('./pages/CorrectionAnnouncementPage'))
const BidReviewPage = lazy(() => import('./pages/BidReviewPage'))
const PublicAnnouncementDetailPage = lazy(() => import('./pages/PublicAnnouncementDetailPage'))
const ProcurementDemandPage = lazy(() => import('./pages/ProcurementDemandPage'))
const ProjectDistributionPage = lazy(() => import('./pages/ProjectDistributionPage'))
const ProcurementResultPage = lazy(() => import('./pages/ProcurementResultPage'))
const ContractPage = lazy(() => import('./pages/ContractPage'))
const InternalBidDemandPage = lazy(() => import('./pages/InternalBidDemandPage'))
const InquiryPage = lazy(() => import('./pages/InquiryPage'))
const InquiryReviewPage = lazy(() => import('./pages/InquiryReviewPage'))
const ProjectReviewUploadPage = lazy(() => import('./pages/ProjectReviewUploadPage'))
const CcgpBoardPage = lazy(() => import('./pages/CcgpBoardPage'))
const DocFormPage = lazy(() => import('./pages/DocFormPage'))
const AgencyAgreementPage = lazy(() => import('./pages/AgencyAgreementPage'))
const ProcurementDocPage = lazy(() => import('./pages/ProcurementDocPage'))
const ProcurementDemandConfirmPage = lazy(() => import('./pages/ProcurementDemandConfirmPage'))
const TemplateManagePage = lazy(() => import('./pages/TemplateManagePage'))
const ArchivePage = lazy(() => import('./pages/ArchivePage'))
const FileOcrPage = lazy(() => import('./pages/FileOcrPage'))
const DocIntakePage = lazy(() => import('./pages/DocIntakePage'))
const SysDocsPage = lazy(() => import('./pages/SysDocsPage'))
const AiDocGenPage = lazy(() => import('./pages/AiDocGenPage'))
const RdwebContractPushPage = lazy(() => import('./pages/RdwebContractPushPage'))
const ApiManagePage = lazy(() => import('./pages/ApiManagePage'))
const FileBoxPage = lazy(() => import('./pages/FileBoxPage'))
const DataPipeBoardPage = lazy(() => import('./pages/DataPipeBoardPage'))
const EmailSettingsPage = lazy(() => import('./pages/EmailSettingsPage'))
const ScraperSettingsPage = lazy(() => import('./pages/ScraperSettingsPage'))
const PermissionManagePage = lazy(() => import('./pages/PermissionManagePage'))
const UserAdminPage = lazy(() => import('./pages/UserAdminPage'))
const LlmUsagePage = lazy(() => import('./pages/LlmUsagePage'))
const LawLibraryPage = lazy(() => import('./pages/LawLibraryPage'))
const PortalPage = lazy(() => import('./pages/PortalPage'))

function RequireAuth({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null | undefined>(undefined)
  const [authError, setAuthError] = useState(false)

  // 已登录后启用空闲计时：30 分钟无操作自动登出
  useIdleLogout(!!user)

  useEffect(() => {
    authMe()
      .then((res) => setUser(res.data.user))
      .catch((e) => {
        // 超时或网络错误：显示错误提示，可手动重试
        if (e?.code === 'ECONNABORTED' || !e?.response) {
          setAuthError(true)
        } else {
          setUser(null)
        }
      })
  }, [])

  if (authError) {
    return (
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
        <span style={{ fontSize: 16, color: '#d93025' }}>连接服务器失败，请检查网络或稍后重试</span>
        <button onClick={() => window.location.reload()} style={{ padding: '8px 24px', cursor: 'pointer', borderRadius: 8, border: '1px solid #1a73e8', color: '#1a73e8', background: '#fff', fontSize: 14 }}>
          重新加载
        </button>
      </div>
    )
  }
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

// ── Google / Material 主题：浅色基底（全局生效，所有页面共用）──────────────
const lightTheme = {
  token: {
    colorPrimary: '#1a73e8',
    colorInfo: '#1a73e8',
    colorLink: '#1a73e8',
    colorSuccess: '#1e8e3e',
    colorWarning: '#f9ab00',
    colorError: '#d93025',
    colorTextBase: '#202124',
    colorBgLayout: '#f8f9fa',
    colorBorderSecondary: '#e8eaed',
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,
    fontSize: 14,
    fontFamily:
      "'Roboto','Google Sans','PingFang SC','Microsoft YaHei',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif",
    controlHeight: 36,
    wireframe: false,
    boxShadowSecondary:
      '0 1px 2px 0 rgba(60,64,67,.3), 0 2px 6px 2px rgba(60,64,67,.15)',
  },
  components: {
    Layout: {
      headerBg: '#ffffff',
      siderBg: '#ffffff',
      bodyBg: '#f8f9fa',
      headerHeight: 64,
      headerPadding: '0 24px',
    },
    Menu: {
      itemBg: 'transparent',
      itemColor: '#3c4043',
      itemHoverBg: '#f1f3f4',
      itemHoverColor: '#202124',
      itemSelectedBg: '#e8f0fe',
      itemSelectedColor: '#1a73e8',
      itemActiveBg: '#e8f0fe',
      itemHeight: 44,
      itemBorderRadius: 22,
      itemMarginInline: 0,
      iconSize: 18,
      fontSize: 14,
      subMenuItemBg: 'transparent',
    },
    Button: {
      controlHeight: 36,
      fontWeight: 500,
      primaryShadow: 'none',
      defaultShadow: 'none',
      borderRadius: 8,
    },
    Card: { borderRadiusLG: 12, headerFontSize: 16 },
    Table: {
      headerBg: '#f8f9fa',
      headerColor: '#5f6368',
      borderColor: '#e8eaed',
      rowHoverBg: '#f8f9fa',
      headerBorderRadius: 8,
    },
    Input: { borderRadius: 8, controlHeight: 36 },
    Select: { borderRadius: 8, controlHeight: 36 },
    Modal: { borderRadiusLG: 16 },
    Tabs: { itemSelectedColor: '#1a73e8', inkBarColor: '#1a73e8', itemColor: '#5f6368' },
    Segmented: { borderRadius: 20 },
  },
}

// ── 暖色护眼主题：仅对浅色基底做增量覆盖（把纯白 surface 换成暖米纸色）──
const THEME_PATCH: Record<string, any> = {
  light: {},
  // 暖色护眼：暖米纸感，降低纯白眩光，文字对比度保持
  sepia: {
    token: {
      colorBgLayout: '#e7e4d3',
      colorBgContainer: '#f4f1e6',
      colorBgElevated: '#f7f4ea',
      colorBorderSecondary: '#e0dbc7',
    },
    components: {
      Layout: { headerBg: '#f4f1e6', siderBg: '#f4f1e6', bodyBg: '#e7e4d3' },
      Menu: { itemHoverBg: '#ece7d5', itemSelectedBg: '#e5efe0', itemSelectedColor: '#1a7f4e' },
      Table: { headerBg: '#ece8d8', rowHoverBg: '#efeada', borderColor: '#e0dbc7' },
    },
  },
}

function mergeComponents(base: any, patch: any) {
  const out: any = { ...base }
  for (const k of Object.keys(patch)) out[k] = { ...(base[k] || {}), ...patch[k] }
  return out
}

function buildTheme(mode: string) {
  const patch = THEME_PATCH[mode] || {}
  return {
    ...lightTheme,
    token: { ...lightTheme.token, ...(patch.token || {}) },
    components: mergeComponents(lightTheme.components, patch.components || {}),
  }
}

export default function App() {
  const [user, setUser] = useState<UserInfo | null>(null)
  // 测试实例构建时注入 VITE_PMS_ENV=test，正式构建无此标志
  const isTest = import.meta.env.VITE_PMS_ENV === 'test'

  // 主题：浅色 / 暖色护眼，记忆到 localStorage（切换按钮在顶栏，见 AppLayout）
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    try { return localStorage.getItem('pms-theme') === 'sepia' ? 'sepia' : 'light' } catch { return 'light' }
  })
  useEffect(() => {
    try { localStorage.setItem('pms-theme', themeMode) } catch { /* ignore */ }
    document.documentElement.setAttribute('data-pms-theme', themeMode)
  }, [themeMode])

  return (
    <ThemeContext.Provider value={{ mode: themeMode, setMode: setThemeMode }}>
    <ConfigProvider locale={zhCN} theme={buildTheme(themeMode)}>
      <AntApp>
        {isTest && (
          <div
            style={{
              position: 'fixed', top: 0, left: '50%', transform: 'translateX(-50%)',
              zIndex: 9999, pointerEvents: 'none',
              background: '#ff4d4f', color: '#fff',
              padding: '2px 18px', borderRadius: '0 0 8px 8px',
              fontSize: 13, fontWeight: 600, letterSpacing: 1,
              boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
            }}
          >
            🧪 测试环境 TEST · 数据为副本，操作不影响正式系统
          </div>
        )}
        <BrowserRouter>
          <Suspense fallback={<div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Spin size="large" /></div>}>
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
              <Route
                index
                element={
                  /* 科室账号直接落到科室门户——/portal 是采购部工作台，科室进去只有空壳 */
                  <Navigate to={user?.role === 'dept' ? "/dept-portal" : "/portal"} replace />
                }
              />
              <Route path="portal" element={<PortalPage />} />
              <Route path="flow" element={<ProjectFlowPage />} />
              <Route path="new" element={<ProjectFormPage />} />
              <Route path="project/:id" element={<ProjectFormPage />} />
              <Route path="bid" element={<BidManagePage />} />
              <Route path="bid-board" element={<BidBoardPage />} />
              <Route path="ccgp-board" element={<CcgpBoardPage />} />
              <Route path="doc-form/:tplkey" element={<DocFormPage />} />
              <Route path="auth-letter" element={<AuthLetterPage />} />
              <Route path="people-manage" element={<PeopleManagePage />} />
              <Route path="template-manage" element={<TemplateManagePage />} />
              <Route path="announcement" element={<AnnouncementPage />} />
              <Route path="correction" element={<CorrectionAnnouncementPage />} />
              <Route path="survey" element={<SurveySingleSourcePage kind="survey" />} />
              <Route path="single-source" element={<SurveySingleSourcePage kind="single_source" />} />
              {/* 采购需求编制：无 type 参数时显示总览（供助理分发用） */}
              <Route path="project-distribution" element={<ProjectDistributionPage />} />
              <Route path="procurement-demand" element={<ProcurementDemandPage />} />
              {/* 各类型子板块：gov / competition / sole_source / inquiry / emergency */}
              <Route path="procurement-demand/:type" element={<ProcurementDemandPage />} />
              <Route path="procurement-result" element={<ProcurementResultPage />} />
              <Route path="contract" element={<ContractPage />} />
              <Route path="internal-bid-demand" element={<InternalBidDemandPage />} />
              <Route path="inquiry" element={<InquiryPage />} />
              <Route path="inquiry-review" element={<InquiryReviewPage />} />
              <Route path="project-review" element={<ProjectReviewUploadPage />} />
              <Route path="agency-agreement" element={<AgencyAgreementPage />} />
              <Route path="agency-manage" element={<AgencyManagePage />} />
              <Route path="agency-assessment" element={<AgencyAssessmentPage />} />
              <Route path="procurement-plan" element={<ProcurementPlanPage />} />
              <Route path="dept-portal" element={<DeptPortalPage />} />
              <Route path="procurement-doc" element={<ProcurementDocPage />} />
              <Route path="procurement-doc/demand" element={<ProcurementDemandConfirmPage />} />
              <Route path="procurement-doc/file" element={<ProcurementDocPage />} />
              <Route path="archive" element={<ArchivePage />} />
              <Route path="file-ocr" element={<FileOcrPage />} />
              <Route path="doc-intake" element={<DocIntakePage />} />
              <Route path="sys-docs" element={<SysDocsPage />} />
              <Route path="ai-doc-gen" element={<AiDocGenPage />} />
              <Route path="rdweb-contract" element={<RdwebContractPushPage />} />
              <Route path="bid-review" element={<BidReviewPage />} />
              <Route path="filebox" element={<FileBoxPage />} />
              <Route path="datapipe" element={<DataPipeBoardPage />} />
              <Route path="chpwd" element={<ChpwdPage />} />
              <Route path="supervision" element={<SupervisionPage />} />
              <Route path="law-library" element={<LawLibraryPage />} />
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
              <Route path="users" element={<UserAdminPage />} />
              <Route path="model" element={<ScraperSettingsPage />} />
              <Route path="api" element={<ApiManagePage />} />
              <Route path="usage" element={<LlmUsagePage />} />
              <Route path="email" element={<EmailSettingsPage />} />
            </Route>
          </Routes>
          </Suspense>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
    </ThemeContext.Provider>
  )
}
