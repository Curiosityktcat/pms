import { useNavigate } from 'react-router-dom'
import { Card, Row, Col, Typography, Tag } from 'antd'
import {
  FormOutlined, ShareAltOutlined, SafetyCertificateOutlined, ProjectOutlined,
  FileTextOutlined, GlobalOutlined, MailOutlined, TeamOutlined,
  CheckCircleOutlined, AuditOutlined, FileDoneOutlined, FileSearchOutlined,
  FileProtectOutlined, BookOutlined, AlertOutlined, FolderOpenOutlined,
  SettingOutlined, RightOutlined,
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
}

// ── 采购流程（严格按业务顺序 1~11）──────────────────────────────
const FLOW: Tile[] = [
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
]

// ── 工具集合（流程之外的能力）───────────────────────────────────
const TOOLS: Tile[] = [
  { label: '文件识别（OCR）', path: '/file-ocr', icon: <FileSearchOutlined />,
    anyPerm: ['file-ocr'] },
  { label: '投标文件审查', path: '/bid-review', icon: <FileProtectOutlined />,
    anyPerm: ['bid-review'] },
  { label: '法规库', path: '/law-library', icon: <BookOutlined />, anyPerm: [] },
  { label: '投诉质疑数据库', path: '/supervision', icon: <AlertOutlined />, anyPerm: [] },
  { label: '我的文件库', path: '/filebox', icon: <FolderOpenOutlined />,
    anyPerm: [], ownerOnly: true },
  { label: '基础数据维护', path: '/agency-manage', icon: <SettingOutlined />, anyPerm: [] },
]

export default function PortalPage() {
  const nav = useNavigate()
  const { user } = useAuth()
  const perms = new Set(user?.perms || [])
  const visible = (t: Tile) => {
    if (t.ownerOnly && user?.username !== '黄新博') return false
    return t.anyPerm.length === 0 || t.anyPerm.some(p => perms.has(p))
  }
  const flow = FLOW.filter(visible)
  const tools = TOOLS.filter(visible)

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
        extra={<Text type="secondary">按业务顺序 1 → 11</Text>}
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
