/**
 * 驳回采购文件——逐条列问题，每条选分类。
 *
 * 为什么要分类：驳回的原因不都是代理机构的错。
 *   代理机构文件问题 —— 文件本身有毛病，计入服务质量考核扣分
 *   采购需求调整     —— 采购人自己改了需求，代理返工不该由它背，不扣分
 * 有三个问题就加三条，考核按「代理机构文件问题」的条数算，比笼统写一段话好落地。
 */
import { useState } from 'react'
import { Modal, Button, Select, Input, Space, Typography, Alert, App } from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { rejectDoc, type RejectIssue, type IssueCategory } from '../services/procurementDoc'

const { Text } = Typography

export const ISSUE_CATEGORIES: IssueCategory[] = [
  { key: 'agency_doc', label: '代理机构文件问题', deduct: true },
  { key: 'demand_change', label: '采购需求调整', deduct: false },
]

export default function RejectIssuesModal({
  projectId, projectName, kind = 'doc', onClose, onDone,
}: {
  projectId: number | null
  projectName: string
  kind?: 'doc' | 'demand'
  onClose: () => void
  onDone: () => void
}) {
  const { message } = App.useApp()
  // 默认给一条空的，省得每次都先点「添加问题」
  const [issues, setIssues] = useState<RejectIssue[]>([{ category: 'agency_doc', text: '' }])
  const [saving, setSaving] = useState(false)

  const patch = (i: number, k: keyof RejectIssue, v: string) =>
    setIssues(list => list.map((it, n) => n === i ? { ...it, [k]: v } : it))
  const add = () => setIssues(list => [...list, { category: 'agency_doc', text: '' }])
  const del = (i: number) => setIssues(list => list.filter((_, n) => n !== i))

  const filled = issues.filter(i => i.text.trim())
  const nDeduct = filled.filter(
    i => ISSUE_CATEGORIES.find(c => c.key === i.category)?.deduct).length

  const submit = async () => {
    if (!projectId) return
    if (!filled.length) { message.warning('至少填一条问题'); return }
    setSaving(true)
    try {
      const res = await rejectDoc(projectId, kind, filled)
      message.success(res.data.message || '已驳回')
      setIssues([{ category: 'agency_doc', text: '' }])
      onDone()
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '驳回失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={!!projectId}
      title={`驳回${kind === 'doc' ? '采购文件' : '采购需求'} — ${projectName}`}
      width={720}
      onCancel={onClose}
      confirmLoading={saving}
      okText="确认驳回"
      okButtonProps={{ danger: true }}
      onOk={submit}
      destroyOnHidden
    >
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        message="一条问题一行，分类要选准：只有「代理机构文件问题」计入服务质量考核扣分；「采购需求调整」是采购人自己改需求，代理返工不扣它的分。代理机构侧会看到这份清单，照着改。"
      />
      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        {issues.map((it, i) => (
          <Space.Compact key={i} style={{ width: '100%' }}>
            <Select
              style={{ width: 170, flex: 'none' }}
              value={it.category}
              onChange={v => patch(i, 'category', v)}
              options={ISSUE_CATEGORIES.map(c => ({
                value: c.key,
                label: c.deduct ? `${c.label}（扣分）` : `${c.label}（不扣分）`,
              }))}
            />
            <Input.TextArea
              autoSize={{ minRows: 1, maxRows: 4 }} maxLength={500}
              placeholder={`第 ${i + 1} 条问题，写清楚要改什么`}
              value={it.text}
              onChange={e => patch(i, 'text', e.target.value)}
            />
            <Button danger icon={<DeleteOutlined />} disabled={issues.length === 1}
              onClick={() => del(i)} />
          </Space.Compact>
        ))}
        <Button type="dashed" icon={<PlusOutlined />} onClick={add} block>添加问题</Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          共 {filled.length} 条，其中 {nDeduct} 条属代理机构文件问题
          {nDeduct > 0 && <Text type="danger">（考核建议扣 {(nDeduct * 1.5).toFixed(1)} 分）</Text>}
        </Text>
      </Space>
    </Modal>
  )
}
