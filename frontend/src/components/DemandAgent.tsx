/**
 * 采购需求 Agent：上传资料 → 它读了给建议 → 勾选采纳。
 *
 * 黄新博 2026-08-19 ⑩ 第 2 条：「可以上传一些文件，然后通过对话的方式
 * 让 Agent 干活，填写采购需求。」
 *
 * 有意做成「先看后采纳」而不是直接写：金额、编号、法条这类东西模型写错了
 * 是要担责的。每条建议都带原文依据，好核对。
 */
import { useState } from 'react'
import {
  Alert, App, Button, Checkbox, Empty, Input, Modal, Space, Spin, Tag, Typography, Upload,
} from 'antd'
import { InboxOutlined, RobotOutlined, CheckOutlined } from '@ant-design/icons'
import { agentSuggest, agentApply, type AgentResult } from '../services/procurementDemand'

const { TextArea } = Input
const { Text } = Typography

export default function DemandAgent(
  { demandId, open, onClose, onApplied }:
  { demandId?: number; open: boolean; onClose: () => void; onApplied?: () => void },
) {
  const { message } = App.useApp()
  const [files, setFiles] = useState<File[]>([])
  const [text, setText] = useState('')
  const [instruction, setInstruction] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<AgentResult | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [pkgPicked, setPkgPicked] = useState<Set<string>>(new Set())

  const run = async () => {
    if (!demandId) return
    if (!files.length && !text.trim()) {
      message.warning('先传几份资料，或者把文字粘进来'); return
    }
    setBusy(true); setRes(null)
    try {
      const r = await agentSuggest(demandId, files, text.trim(), instruction.trim())
      setRes(r.data.data)
      // 默认全选——大多数建议是能用的，让人取消个别的比逐个勾快
      setPicked(new Set(Object.keys(r.data.data.fields || {})))
      const pk = new Set<string>()
      ;(r.data.data.packages || []).forEach((p, i) =>
        Object.keys(p).forEach(k => pk.add(`${i}|${k}`)))
      setPkgPicked(pk)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(msg || 'Agent 没跑成')
    } finally { setBusy(false) }
  }

  const apply = async () => {
    if (!demandId || !res) return
    const f: Record<string, string> = {}
    Object.entries(res.fields || {}).forEach(([k, v]) => {
      if (picked.has(k)) f[k] = v.value
    })
    const pkgs: Record<string, string>[] = []
    ;(res.packages || []).forEach((p, i) => {
      const one: Record<string, string> = {}
      Object.entries(p).forEach(([k, v]) => {
        if (pkgPicked.has(`${i}|${k}`)) one[k] = v.value
      })
      pkgs[i] = one
    })
    setBusy(true)
    try {
      const r = await agentApply(demandId, f, pkgs)
      message.success(r.data.message || '已采纳')
      onApplied?.()
      onClose()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(msg || '采纳失败')
    } finally { setBusy(false) }
  }

  const total = res
    ? Object.keys(res.fields || {}).length
      + (res.packages || []).reduce((n, p) => n + Object.keys(p).length, 0)
    : 0
  const chosen = picked.size + pkgPicked.size

  return (
    <Modal open={open} onCancel={onClose} width={860}
      title={<span><RobotOutlined /> 让 Agent 读资料填需求</span>}
      footer={[
        <Button key="c" onClick={onClose}>关闭</Button>,
        !res
          ? <Button key="r" type="primary" loading={busy} onClick={run}>开始读</Button>
          : <Button key="a" type="primary" icon={<CheckOutlined />} loading={busy}
              disabled={!chosen} onClick={apply}>
              采纳选中的（{chosen}/{total}）
            </Button>,
      ]}>
      {!res ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert type="info" showIcon
            message="它只摘原文里有的，不会替你编"
            description="金额、编号、日期这类不让它碰——那些要么来自立项，要么必须你自己填。
              每条建议都会附上原文依据，采纳前你能核对。" />
          <Upload.Dragger multiple showUploadList={{ showRemoveIcon: true }}
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.txt"
            fileList={files.map((f, i) => ({ uid: String(i), name: f.name, status: 'done' as const }))}
            beforeUpload={(f) => { setFiles(v => [...v, f as File]); return false }}
            onRemove={(f) => { setFiles(v => v.filter((_, i) => String(i) !== f.uid)) }}>
            <p style={{ margin: 0, fontSize: 24, color: '#1a73e8' }}><InboxOutlined /></p>
            <p style={{ margin: '4px 0 0' }}>把科室报的需求说明、参数表、报价单拖进来</p>
            <p style={{ margin: 0, fontSize: 12, color: '#5f6368' }}>
              支持 PDF / Word / 图片（扫描件会自动过 OCR）
            </p>
          </Upload.Dragger>
          <div>
            <Text style={{ fontSize: 13 }}>或者直接粘文字</Text>
            <TextArea rows={4} value={text} onChange={e => setText(e.target.value)}
              placeholder="把科室发来的需求描述粘这里也行" />
          </div>
          <div>
            <Text style={{ fontSize: 13 }}>有什么特别要求（可不填）</Text>
            <Input value={instruction} onChange={e => setInstruction(e.target.value)}
              placeholder="比如：技术要求按「参数项/技术要求」两列整理" />
          </div>
          {busy && <div style={{ textAlign: 'center' }}><Spin /> 正在读资料，稍等…</div>}
        </Space>
      ) : (
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="blue">读了 {res.read?.length || 0} 份资料</Tag>
            <Tag>{res.material_chars} 字</Tag>
            <Tag color="green">给出 {total} 条建议</Tag>
          </Space>
          {(res.failed || []).length > 0 && (
            <Alert type="warning" showIcon message="这几份没读成"
              description={(res.failed || []).join('；')} />
          )}
          {total === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="这些资料里没摘到能填的内容" />
          ) : (
            <div style={{ maxHeight: 420, overflowY: 'auto' }}>
              {Object.entries(res.fields || {}).map(([k, v]) => (
                <div key={k} style={{ borderBottom: '1px solid #f0f0f0', padding: '8px 0' }}>
                  <Checkbox checked={picked.has(k)}
                    onChange={e => setPicked(s => {
                      const n = new Set(s); e.target.checked ? n.add(k) : n.delete(k); return n
                    })}>
                    <Text strong style={{ fontSize: 13 }}>{k}</Text>
                  </Checkbox>
                  <div style={{ marginLeft: 24, fontSize: 13 }}>{v.value}</div>
                  <div style={{ marginLeft: 24, fontSize: 12, color: '#8c8c8c', marginTop: 2 }}>
                    依据：{v.evidence}
                  </div>
                </div>
              ))}
              {(res.packages || []).map((p, i) =>
                Object.entries(p).map(([k, v]) => {
                  const key = `${i}|${k}`
                  return (
                    <div key={key} style={{ borderBottom: '1px solid #f0f0f0', padding: '8px 0' }}>
                      <Checkbox checked={pkgPicked.has(key)}
                        onChange={e => setPkgPicked(s => {
                          const n = new Set(s); e.target.checked ? n.add(key) : n.delete(key); return n
                        })}>
                        <Text strong style={{ fontSize: 13 }}>合同包{i + 1} · {k}</Text>
                      </Checkbox>
                      <div style={{ marginLeft: 24, fontSize: 13, whiteSpace: 'pre-wrap' }}>{v.value}</div>
                      <div style={{ marginLeft: 24, fontSize: 12, color: '#8c8c8c', marginTop: 2 }}>
                        依据：{v.evidence}
                      </div>
                    </div>
                  )
                }))}
            </div>
          )}
          {(res.notes || []).length > 0 && (
            <Alert type="info" message="它说不准的地方"
              description={<ul style={{ margin: 0, paddingLeft: 18 }}>
                {res.notes.map((n, i) => <li key={i} style={{ fontSize: 12 }}>{n}</li>)}
              </ul>} />
          )}
        </Space>
      )}
    </Modal>
  )
}
