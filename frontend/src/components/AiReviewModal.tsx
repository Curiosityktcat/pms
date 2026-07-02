import { useState, useEffect, useCallback } from 'react'
import { Modal, Button, Spin, Empty, Typography, Tag, Space, App } from 'antd'
import { RobotOutlined, ReloadOutlined, CopyOutlined } from '@ant-design/icons'
import type { Project } from '../services/project'
import { aiReviewDoc } from '../services/procurementDoc'

const { Text, Paragraph } = Typography

/** 采购文件「AI 编制建议」弹窗：调用大模型对采购需求给出意见和建议（只读）。 */
export default function AiReviewModal({
  project, open, onClose,
}: {
  project: Project | null
  open: boolean
  onClose: () => void
}) {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [text, setText] = useState('')
  const [balance, setBalance] = useState<number | null>(null)

  const run = useCallback(async () => {
    if (!project) return
    setLoading(true)
    setText('')
    try {
      const res = await aiReviewDoc(project.id)
      if (res.data.ok) {
        setText(res.data.data.suggestions || '')
        setBalance(typeof res.data.data.balance === 'number' ? res.data.data.balance : null)
      } else {
        message.error((res.data as { error?: string }).error || '生成失败')
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      message.error(e.response?.data?.error || 'AI 生成失败，请确认大模型已在后台配置并在线')
    } finally {
      setLoading(false)
    }
  }, [project, message])

  // 打开时自动生成一次
  useEffect(() => {
    if (open && project) run()
    // 关闭时清空，避免下次闪现旧内容
    if (!open) { setText(''); setBalance(null) }
  }, [open, project, run])

  const copy = () => {
    navigator.clipboard?.writeText(text).then(
      () => message.success('已复制到剪贴板'),
      () => message.error('复制失败'),
    )
  }

  return (
    <Modal
      title={
        <Space>
          <RobotOutlined style={{ color: '#1677ff' }} />
          <span>AI 编制建议 — {project?.name || ''}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={760}
      destroyOnHidden
      footer={[
        <Button key="copy" icon={<CopyOutlined />} disabled={!text || loading} onClick={copy}>
          复制
        </Button>,
        <Button key="regen" icon={<ReloadOutlined />} loading={loading} onClick={run}>
          重新生成
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
      ]}
    >
      <div style={{ marginBottom: 8 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          建议由大模型根据本项目「采购需求」生成，仅供参考，请经办人自行核对后采用。
        </Text>
        {balance !== null && (
          <Tag color={balance <= 0 ? 'red' : balance < 10 ? 'orange' : 'green'}>
            剩余 AI 余额：¥{balance.toFixed(2)}
          </Tag>
        )}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin tip="AI 正在审阅采购需求，请稍候…（首次或大模型较慢时可能需要数十秒）">
            <div style={{ height: 60 }} />
          </Spin>
        </div>
      ) : text ? (
        <Paragraph
          style={{
            whiteSpace: 'pre-wrap', maxHeight: '60vh', overflow: 'auto',
            background: '#f6f8fc', borderRadius: 6, padding: '12px 16px',
            margin: 0, lineHeight: 1.7,
          }}
        >
          {text}
        </Paragraph>
      ) : (
        <Empty description="暂无内容" />
      )}
    </Modal>
  )
}
