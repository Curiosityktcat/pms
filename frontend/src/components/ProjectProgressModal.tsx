import { useEffect, useState } from 'react'
import { Modal, Steps, Tag, Spin, Empty, Typography, App } from 'antd'
import {
  getProjectProgress, type ProjectProgress, type ProgressNode,
} from '../services/project'

const { Text } = Typography

const STAGE_CN: Record<string, string> = {
  round_failed: '本轮流标，待开下一轮',
  done: '本轮已全部完成',
}

function stageLabel(p: ProjectProgress): string {
  const s = p.project.current_stage
  if (STAGE_CN[s]) return STAGE_CN[s]
  const node = p.rounds.at(-1)?.nodes.find(n => n.key === s)
  return node ? `待办：${node.label}` : '—'
}

function fmt(t: string): string {
  return t ? t.replace('T', ' ').slice(0, 16) : ''
}

/** 单个节点的描述（时间 + 操作人 + 各节点专属明细）。 */
function NodeDesc({ node }: { node: ProgressNode }) {
  const lines: React.ReactNode[] = []
  if (node.at || node.by) {
    lines.push(
      <div key="meta">
        <Text type="secondary">{fmt(node.at)}</Text>
        {node.by ? <Text type="secondary"> · {node.by}</Text> : null}
      </div>,
    )
  }
  if (node.key === 'doc_upload' && node.files?.length) {
    lines.push(
      <div key="files">
        {node.files.map((f, i) => (
          <div key={i}><Text style={{ fontSize: 12 }}>📎 {f.name}　<Text type="secondary">{fmt(f.at)}</Text></Text></div>
        ))}
      </div>,
    )
  }
  if (node.key === 'announce' && !node.done && node.ann_status) {
    lines.push(<Tag key="ann" color="orange">{node.ann_status}</Tag>)
  }
  if (node.key === 'bid_open' && node.result_value) {
    lines.push(
      <Tag key="bid" color={node.result_value === '可开标' ? 'green' : 'red'}>{node.result_value}</Tag>,
    )
  }
  if (node.key === 'review' && node.result_value) {
    lines.push(
      <Tag key="rv" color={node.result_value === '中选' ? 'green' : 'red'}>{node.result_value}</Tag>,
    )
  }
  if (node.key === 'result' && node.packages?.length) {
    lines.push(
      <div key="res">
        {node.packages.map((pk, i) => {
          const r = String(pk.result ?? '')
          return (
            <div key={i} style={{ fontSize: 12 }}>
              包{String(pk.package_no ?? i + 1)}：
              <Tag color={r === '成交' ? 'green' : r === '废标' ? 'red' : 'default'} style={{ marginInlineEnd: 0 }}>{r || '待定'}</Tag>
              {pk.winner ? <Text type="secondary"> {String(pk.winner)}</Text> : null}
            </div>
          )
        })}
      </div>,
    )
  }
  if (node.key === 'contract' && node.packages?.length) {
    lines.push(
      <div key="ct">
        {node.packages.map((pk, i) => (
          <div key={i} style={{ fontSize: 12 }}>
            包{String(pk.package_no ?? i + 1)}：
            <Tag color={pk.signed ? 'green' : 'default'} style={{ marginInlineEnd: 0 }}>{pk.signed ? '已签订' : '待签订'}</Tag>
            {pk.winner ? <Text type="secondary"> {String(pk.winner)}</Text> : null}
          </div>
        ))}
      </div>,
    )
  }
  return <div style={{ paddingBottom: 4 }}>{lines}</div>
}

export default function ProjectProgressModal({
  projectId, open, onClose,
}: { projectId: number | null; open: boolean; onClose: () => void }) {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<ProjectProgress | null>(null)

  useEffect(() => {
    if (!open || !projectId) return
    setLoading(true)
    setData(null)
    getProjectProgress(projectId)
      .then(res => setData(res.data.data))
      .catch(() => message.error('加载项目进展失败'))
      .finally(() => setLoading(false))
  }, [open, projectId, message])

  const isLatest = (ri: number) => !!data && ri === data.rounds.length - 1

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      title={data ? (
        <span>
          {data.project.name}
          <Tag color="blue" style={{ marginInlineStart: 8 }}>当前第 {data.project.current_round} 次</Tag>
          <Tag>{stageLabel(data)}</Tag>
        </span>
      ) : '项目进展'}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : !data || data.rounds.length === 0 ? (
        <Empty description="暂无进展记录" />
      ) : (
        <div style={{ maxHeight: '70vh', overflowY: 'auto', paddingTop: 8 }}>
          {data.rounds.map((rd, ri) => (
            <div key={rd.round_number} style={{ marginBottom: 20 }}>
              <div style={{ marginBottom: 10, fontWeight: 600 }}>
                第 {rd.round_number} 次采购
                <Tag color={rd.status === '已结束' ? 'default' : 'processing'} style={{ marginInlineStart: 8 }}>{rd.status}</Tag>
              </div>
              <Steps
                direction="vertical"
                size="small"
                items={rd.nodes.map(n => ({
                  title: n.label,
                  status: n.done
                    ? ('finish' as const)
                    : (isLatest(ri) && data.project.current_stage === n.key
                        ? ('process' as const)
                        : ('wait' as const)),
                  description: <NodeDesc node={n} />,
                }))}
              />
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
