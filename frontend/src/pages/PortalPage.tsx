import { useNavigate } from 'react-router-dom'
import { Card, Row, Col, Button, Typography, Space } from 'antd'
import {
  ShoppingCartOutlined, FileTextOutlined, SettingOutlined, RightOutlined,
} from '@ant-design/icons'
import { useAuth } from '../hooks/useAuth'

const { Title, Paragraph, Text } = Typography

interface Entry { label: string; path: string }
interface Group {
  key: string; title: string; desc: string; color: string
  icon: React.ReactNode; primary: Entry; links: Entry[]; adminOnly?: boolean
}

const GROUPS: Group[] = [
  {
    key: 'biz', title: '采购业务', desc: '从需求编制到立项、开标、合同的完整采购流程',
    color: '#1677ff', icon: <ShoppingCartOutlined />,
    primary: { label: '进入采购流程', path: '/flow' },
    links: [
      { label: '采购需求编制', path: '/procurement-demand' },
      { label: '项目分发', path: '/project-distribution' },
      { label: '开标管理', path: '/bid' },
      { label: '采购文件编制', path: '/procurement-doc' },
      { label: '投标审查', path: '/bid-review' },
      { label: '询议价', path: '/inquiry' },
      { label: '合同管理', path: '/contract' },
      { label: '归档', path: '/archive' },
    ],
  },
  {
    key: 'doc', title: '文档工具', desc: '文件 OCR / 格式转换、法规知识库、个人文件库',
    color: '#52c41a', icon: <FileTextOutlined />,
    primary: { label: '文件 OCR / 转换', path: '/file-ocr' },
    links: [
      { label: '文件 OCR', path: '/file-ocr' },
      { label: '法规库', path: '/law-library' },
      { label: '文件库', path: '/filebox' },
    ],
  },
  {
    key: 'admin', title: '后台管理', desc: '权限、大模型、邮件等系统级配置', adminOnly: true,
    color: '#722ed1', icon: <SettingOutlined />,
    primary: { label: '进入后台', path: '/admin' },
    links: [
      { label: '权限管理', path: '/admin/permissions' },
      { label: '大模型配置', path: '/admin/model' },
      { label: 'Token 用量', path: '/admin/usage' },
      { label: '邮件配置', path: '/admin/email' },
    ],
  },
]

export default function PortalPage() {
  const nav = useNavigate()
  const { user } = useAuth()
  const groups = GROUPS.filter(g => !g.adminOnly || user?.is_admin)

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '8px 4px' }}>
      <Title level={3} style={{ marginBottom: 2 }}>采购管理系统</Title>
      <Paragraph type="secondary" style={{ marginBottom: 24 }}>
        欢迎{user?.display_name ? `，${user.display_name}` : ''} · 选择一个工作区进入
      </Paragraph>
      <Row gutter={[20, 20]}>
        {groups.map(g => (
          <Col xs={24} md={12} lg={8} key={g.key}>
            <Card
              hoverable
              style={{ height: '100%', borderTop: `3px solid ${g.color}` }}
              styles={{ body: { display: 'flex', flexDirection: 'column', height: '100%' } }}
              onClick={() => nav(g.primary.path)}
            >
              <Space align="center" style={{ marginBottom: 8 }}>
                <span style={{ fontSize: 26, color: g.color }}>{g.icon}</span>
                <Title level={4} style={{ margin: 0 }}>{g.title}</Title>
              </Space>
              <Text type="secondary" style={{ minHeight: 40, display: 'block' }}>{g.desc}</Text>
              <div style={{ margin: '14px 0', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {g.links.map(l => (
                  <Button
                    key={l.path} size="small"
                    onClick={e => { e.stopPropagation(); nav(l.path) }}
                  >{l.label}</Button>
                ))}
              </div>
              <Button
                type="primary" block style={{ marginTop: 'auto', background: g.color, borderColor: g.color }}
                onClick={e => { e.stopPropagation(); nav(g.primary.path) }}
              >
                {g.primary.label} <RightOutlined />
              </Button>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  )
}
