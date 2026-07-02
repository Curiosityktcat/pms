import { useState } from 'react'
import { Button, Modal, Tooltip, Typography, Steps, Alert, Divider, Tag } from 'antd'
import {
  RobotOutlined, BulbOutlined, ApiOutlined, FileSearchOutlined,
  BarChartOutlined, WarningOutlined,
} from '@ant-design/icons'

const { Title, Paragraph, Text } = Typography

/** 顶栏右上角「AI 使用说明」按钮 + 说明书弹窗。 */
export default function AiGuideButton({ isAdmin = false }: { isAdmin?: boolean }) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Tooltip title="查看 AI 功能使用说明">
        <Button
          icon={<RobotOutlined />}
          type="text"
          onClick={() => setOpen(true)}
          style={{ color: '#722ed1', fontSize: 13, marginRight: 8 }}
        >
          AI 使用说明
        </Button>
      </Tooltip>

      <Modal
        title={
          <span>
            <RobotOutlined style={{ color: '#722ed1', marginRight: 8 }} />
            AI 使用说明
          </span>
        }
        open={open}
        onCancel={() => setOpen(false)}
        footer={<Button type="primary" onClick={() => setOpen(false)}>我知道了</Button>}
        width={720}
        styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
      >
        {/* 1. AI 能帮你做什么 */}
        <Title level={5}><BulbOutlined style={{ color: '#faad14' }} /> 一、AI 能帮你做什么</Title>
        <Paragraph>
          目前提供 <Text strong>「AI 编制建议」</Text>：编制采购文件时，AI 会参考该项目
          <Text strong>已填写的采购需求</Text>，从以下方面给出意见和建议，帮助把采购文件编得更规范：
        </Paragraph>
        <Paragraph style={{ marginBottom: 4 }}>
          <Tag color="blue">完整性检查</Tag>
          <Tag color="red">合规与风险</Tag>
          <Tag color="green">技术参数</Tag>
          <Tag color="purple">评分办法</Tag>
          <Tag color="orange">商务与合同</Tag>
          <Tag>总体结论</Tag>
        </Paragraph>

        <Divider style={{ margin: '16px 0' }} />

        {/* 2. 使用前提 */}
        <Title level={5}><ApiOutlined style={{ color: '#1677ff' }} /> 二、使用前提</Title>
        <Paragraph>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>大模型已<Text strong>在线可用</Text>（由管理员在「后台管理 → 大模型配置」中配置并测试连接通过）。</li>
            <li>该项目<Text strong>已填写采购需求</Text>数据；否则会提示「未找到该项目的采购需求数据」。</li>
          </ul>
        </Paragraph>

        <Divider style={{ margin: '16px 0' }} />

        {/* 3. 操作步骤 */}
        <Title level={5}><FileSearchOutlined style={{ color: '#13c2c2' }} /> 三、操作步骤</Title>
        <Steps
          direction="vertical"
          size="small"
          current={-1}
          items={[
            { title: '进入采购文件确认页', description: '左侧菜单：5. 采购文件编制 → 5.2 采购文件确认' },
            { title: '点击「AI 编制建议」', description: '在对应项目那一行，点击带机器人图标的「AI 编制建议」按钮' },
            { title: '等待生成', description: '弹窗会自动调用大模型生成建议，请稍候（模型较慢时可能需数十秒）' },
            { title: '查看 / 复制 / 重新生成', description: '可直接阅读建议，点「复制」保存，或点「重新生成」再来一次' },
          ]}
        />

        <Divider style={{ margin: '16px 0' }} />

        {/* 4. 注意事项 */}
        <Title level={5}><WarningOutlined style={{ color: '#fa541c' }} /> 四、注意事项</Title>
        <Alert
          type="warning"
          showIcon
          message="AI 建议仅供参考"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              <li>AI <Text strong>不会修改或定稿任何文件</Text>，只给文字建议，最终内容须由经办人自行核对后采用。</li>
              <li>AI 可能有疏漏或不准确，涉及法定条款、技术参数请以制度规定和专业判断为准。</li>
              <li>请勿把 AI 建议直接当作最终采购文件使用。</li>
              <li><Text strong>代理机构</Text>使用 AI 会按 token 用量从本机构余额扣费（弹窗右上角可见剩余余额）；余额不足时请联系采购部充值。</li>
            </ul>
          }
        />

        {isAdmin && (
          <>
            <Divider style={{ margin: '16px 0' }} />
            <Title level={5}><BarChartOutlined style={{ color: '#722ed1' }} /> 五、管理员专用</Title>
            <Paragraph>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                <li><Text strong>大模型配置</Text>：后台管理 → 大模型配置，可切换本地 / 在线模型并测试连接。全系统共用此配置。</li>
                <li><Text strong>Token 用量与计费</Text>：后台管理 → Token 用量，查看各账号调用次数与费用；在「代理机构余额 / 计费」中设置每百万 token 单价、查看与充值各代理机构余额。</li>
              </ul>
            </Paragraph>
          </>
        )}
      </Modal>
    </>
  )
}
