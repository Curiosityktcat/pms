import { useNavigate } from 'react-router-dom'
import { Card, Row, Col, Typography, Tag } from 'antd'
import {
  FormOutlined, ShareAltOutlined, SafetyCertificateOutlined, ProjectOutlined,
  FileTextOutlined, GlobalOutlined, MailOutlined, TeamOutlined,
  CheckCircleOutlined, AuditOutlined, FileDoneOutlined, FileSearchOutlined,
  FileProtectOutlined, BookOutlined, AlertOutlined, FolderOpenOutlined,
  ReadOutlined, SettingOutlined, RightOutlined, RobotOutlined, ThunderboltOutlined, CloudUploadOutlined,
  BarChartOutlined, ProfileOutlined,
} from '@ant-design/icons'
import { useAuth } from '../hooks/useAuth'
import DeptAnnouncementBoard from '../components/DeptAnnouncementBoard'

const { Title, Paragraph, Text } = Typography

interface Tile {
  no?: string           // 采购流程序号
  label: string
  path: string
  icon: React.ReactNode
  /** 有任一权限即可见；空数组 = 不受控（所有人可见） */
  anyPerm: string[]
  ownerOnly?: boolean   // 仅黄新博（私人文件库）
  cgbOnly?: boolean     // 仅采购部内部（科室/监督/代理机构都不给）
  deptToo?: boolean     // 工具集合里，科室账号也开放的那几个
}

// 采购部内部角色：这几个之外的（科室、监督、代理机构）看不到 cgbOnly 的东西
const CGB_ROLES = new Set(['officer', 'assistant', 'pd_assistant', 'leader'])
// 科室类角色：工具集合对他们只开放白名单里的那几个
const DEPT_ROLES = new Set(['dept', 'dept_manage', 'dept_demand', 'supervisor'])

// ── 采购流程（严格按业务顺序 0~11）──────────────────────────────
const FLOW: Tile[] = [
  // 0. 项目管理：黄新博 2026-08-19 要的——项目管理器和我的科室项目
  // 原来散在别处没有归属，合成一个入口。
  { no: '0', label: '项目管理器', path: '/project-monitor', icon: <BarChartOutlined />,
    anyPerm: ['project-monitor'] },
  { no: '0', label: '我的科室项目', path: '/dept-portal', icon: <ProfileOutlined />,
    anyPerm: ['dept-portal'] },
  { no: '1', label: '采购需求编制', path: '/procurement-demand', icon: <FormOutlined />,
    anyPerm: ['procurement-demand-gov', 'internal-bid-demand', 'procurement-demand-sole',
              'procurement-demand-inquiry', 'procurement-demand-emergency'] },
  { no: '2', label: '采购项目分发', path: '/project-distribution', icon: <ShareAltOutlined />,
    anyPerm: ['dispatch'] },
  { no: '3', label: '代理协议', path: '/agency-agreement', icon: <SafetyCertificateOutlined />,
    anyPerm: ['agency-agreement'] },
  { no: '4', label: '采购部项目管理', path: '/flow', icon: <ProjectOutlined />,
    anyPerm: ['new', 'flow', 'bid', 'bid-board', 'auth-letter'] },
  { no: '5', label: '采购文件编制', path: '/procurement-doc/demand', icon: <FileTextOutlined />,
    anyPerm: ['doc'] },
  { no: '6', label: '挂网管理', path: '/announcement', icon: <GlobalOutlined />,
    anyPerm: ['announcement'] },
  { no: '7', label: '询/议价函、紧急采购', path: '/inquiry', icon: <MailOutlined />,
    anyPerm: ['inquiry'] },
  { no: '8', label: '项目评审', path: '/inquiry-review', icon: <TeamOutlined />,
    anyPerm: ['inquiry-review', 'project-review'] },
  { no: '9', label: '采购结果确认', path: '/procurement-result', icon: <CheckCircleOutlined />,
    anyPerm: ['procurement-result'] },
  { no: '10', label: '合同管理', path: '/contract', icon: <AuditOutlined />,
    anyPerm: ['contract'] },
  { no: '11', label: '归档', path: '/archive', icon: <FileDoneOutlined />,
    anyPerm: ['archive'] },
  // 考核不按权限点挂：经办人要给自己项目的代理打分，助理/负责人要看汇总，
  // 曾经把它挂在「分发」权限下，结果经办人整个看不到，别再犯。
  // 但它是**采购部内部**的事——2026-08-19 黄新博：「这个地方除了采购部人员应该看不到」。
  // 所以改成按角色收：科室、监督、代理机构都不给。
  { no: '12', label: '代理机构考核', path: '/agency-assessment',
    icon: <SafetyCertificateOutlined />, anyPerm: [], cgbOnly: true },
]

// ── 工具集合（流程之外的能力）───────────────────────────────────
const TOOLS: Tile[] = [
  { label: 'AI 采购文件生成', path: '/ai-doc-gen', icon: <RobotOutlined />, anyPerm: [] },
  { label: '合同审签推送', path: '/rdweb-contract', icon: <ThunderboltOutlined />,
    anyPerm: ['contract'] },
  { label: '文件识别（OCR）', path: '/file-ocr', icon: <FileSearchOutlined />,
    anyPerm: ['file-ocr'] },
  { label: '资料智能归档', path: '/doc-intake', icon: <CloudUploadOutlined />, anyPerm: [] },
  { label: '投标文件审查', path: '/bid-review', icon: <FileProtectOutlined />,
    anyPerm: [], ownerOnly: true },   // 仅限「黄新博」本人
  // 2026-08-19 黄新博：「工具栏对于归口科室和需求科室，只开放法规库和投诉质疑数据库，
  // 其余功能都不给」——靠 deptToo 标出这两个，其余对科室一律隐藏。
  { label: '法规库', path: '/law-library', icon: <BookOutlined />, anyPerm: [], deptToo: true },
  { label: '系统说明书', path: '/sys-docs', icon: <ReadOutlined />,
    anyPerm: [], ownerOnly: true },   // 仅限「黄新博」本人
  { label: '投诉质疑数据库', path: '/supervision', icon: <AlertOutlined />,
    anyPerm: [], deptToo: true },
  { label: '我的文件库', path: '/filebox', icon: <FolderOpenOutlined />,
    anyPerm: [], ownerOnly: true },
  { label: '基础数据维护', path: '/agency-manage', icon: <SettingOutlined />, anyPerm: [] },
]

export default function PortalPage() {
  const nav = useNavigate()
  const { user } = useAuth()
  const perms = new Set(user?.perms || [])
  const role = user?.role || ''
  const isDeptSide = DEPT_ROLES.has(role)
  const visible = (t: Tile) => {
    if (t.ownerOnly && user?.username !== '黄新博') return false
    if (t.cgbOnly && !CGB_ROLES.has(role) && !user?.is_admin) return false
    return t.anyPerm.length === 0 || t.anyPerm.some(p => perms.has(p))
  }
  const flow = FLOW.filter(visible)
  // 工具集合对科室/监督只开放白名单那两个；采购部照旧
  const tools = TOOLS.filter(t => visible(t) && (!isDeptSide || t.deptToo))

  const tile = (t: Tile, color: string) => (
    <Col xs={12} sm={8} md={6} lg={t.no ? 4 : 6} key={t.path} style={{ display: 'flex' }}>
      <Card
        hoverable
        size="small"
        style={{ width: '100%', textAlign: 'center', borderTop: `3px solid ${color}` }}
        styles={{ body: { padding: '18px 8px 14px' } }}
        onClick={() => nav(t.path)}
      >
        <div style={{ fontSize: 26, color, marginBottom: 8 }}>{t.icon}</div>
        <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4 }}>
          {t.no && <Tag color={color} style={{ marginRight: 4, padding: '0 5px' }}>{t.no}</Tag>}
          {t.label}
        </div>
      </Card>
    </Col>
  )

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '8px 4px' }}>
      <Title level={3} style={{ marginBottom: 2 }}>自行采购管理信息系统</Title>
      <Paragraph type="secondary" style={{ marginBottom: 20 }}>
        欢迎{user?.display_name ? `，${user.display_name}` : ''} · 选择要进入的功能
      </Paragraph>

      <Card
        title={<span><RightOutlined style={{ color: '#1677ff' }} /> 采购流程</span>}
        extra={<Text type="secondary">按业务顺序 0 → 11</Text>}
        style={{ marginBottom: 20 }}
      >
        <Row gutter={[14, 14]}>{flow.map(t => tile(t, '#1677ff'))}</Row>
        {flow.length === 0 && <Text type="secondary">当前账号没有可用的流程模块</Text>}
      </Card>

      <Card title={<span><RightOutlined style={{ color: '#52c41a' }} /> 工具集合</span>}>
        <Row gutter={[14, 14]}>{tools.map(t => tile(t, '#52c41a'))}</Row>
      </Card>

      <DeptAnnouncementBoard />
    </div>
  )
}
