import { Alert, Input, InputNumber, Select, Space, Table, Tooltip, Typography } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import {
  exportCsvUrl, type ReviewItem, type ReviewResult, type ReviewTask,
} from '../../services/bidReview'
import { catTag, verdictTag } from './shared'

const { Text, Title, Paragraph } = Typography

export type ItemPatch = { verdict?: string; final_score?: number | null; note?: string }

/** ④ 单家审查结果：淘汰建议横幅 + 资格/符合性/打分 三段表格。 */
export default function ItemsSection({ task, result, items, onUpdate }: {
  task: ReviewTask
  result: ReviewResult
  items: ReviewItem[]
  onUpdate: (it: ReviewItem, data: ItemPatch) => void
}) {
  const qual = items.filter(it => it.category === '资格')
  const comp = items.filter(it => it.category === '实质性' || it.category === '商务')
  const score = items.filter(it => it.category === '打分')

  const qualFails = qual.filter(it => it.verdict === '不满足')
  const compFails = comp.filter(it => it.verdict === '不满足')
  const unfoundCnt = [...qual, ...comp].filter(it => it.verdict === '未找到').length

  const noteCol = {
    title: '人工批注', dataIndex: 'note', width: 170,
    render: (v: string, it: ReviewItem) => (
      <Input size="small" defaultValue={v} placeholder="复核批注"
        key={`${it.id}:${v}`}
        onBlur={e => { if (e.target.value !== v) onUpdate(it, { note: e.target.value }) }} />
    ),
  }
  const evidenceCols = [
    { title: '证据页码', dataIndex: 'evidence_page', width: 95,
      render: (v: string) => v || <Text type="secondary">—</Text> },
    {
      title: '原文摘录', dataIndex: 'evidence_text', ellipsis: true,
      render: (v: string) => v
        ? <Tooltip title={<div style={{ maxHeight: 300, overflow: 'auto' }}>{v}</div>}>{v}</Tooltip>
        : <Text type="secondary">—</Text>,
    },
    { title: '置信度', dataIndex: 'confidence', width: 70,
      render: (v: string) => v || '—' },
  ]

  const judgeColumns = (withCat: boolean) => [
    { title: '#', dataIndex: 'criteria_seq', width: 50 },
    { title: '条目', dataIndex: 'criteria_content', width: 250, ellipsis: true,
      render: (v: string) => <Tooltip title={<div style={{ maxHeight: 300, overflow: 'auto' }}>{v}</div>}>{v}</Tooltip> },
    ...(withCat ? [{ title: '类别', dataIndex: 'category', width: 75,
      render: (v: string) => catTag(v) }] : []),
    {
      title: 'AI 判定（可改）', dataIndex: 'verdict', width: 125,
      render: (v: string, it: ReviewItem) => (
        <Select size="small" value={v} style={{ width: 100 }}
          onChange={nv => onUpdate(it, { verdict: nv })}
          options={[
            { value: '满足', label: '满足' },
            { value: '不满足', label: '不满足' },
            { value: '未找到', label: '未找到' },
          ]}
          labelRender={() => verdictTag(v)} />
      ),
    },
    ...evidenceCols,
    noteCol,
  ]

  const scoreColumns = [
    { title: '#', dataIndex: 'criteria_seq', width: 50 },
    { title: '评分项', dataIndex: 'criteria_content', width: 200, ellipsis: true,
      render: (v: string, it: ReviewItem) => (
        <Tooltip title={<div style={{ maxHeight: 300, overflow: 'auto' }}>
          {v}{it.score_rule ? `\n评分规则：${it.score_rule}` : ''}
        </div>}>{v}</Tooltip>
      ) },
    { title: '分值', dataIndex: 'max_score', width: 65,
      render: (v: number | null) => v != null ? `${v}分` : '—' },
    { title: 'AI建议分', dataIndex: 'ai_score', width: 85,
      render: (v: number | null) => v != null ? v : <Text type="secondary">—</Text> },
    { title: 'AI理由', dataIndex: 'ai_reason', ellipsis: true,
      render: (v: string) => v
        ? <Tooltip title={<div style={{ maxHeight: 300, overflow: 'auto' }}>{v}</div>}>{v}</Tooltip>
        : <Text type="secondary">—</Text> },
    { title: '证据页码', dataIndex: 'evidence_page', width: 95,
      render: (v: string) => v || <Text type="secondary">—</Text> },
    {
      title: '最终得分（可改）', width: 130,
      render: (_: unknown, it: ReviewItem) => (
        <InputNumber size="small" min={0} max={it.max_score ?? undefined}
          key={`${it.id}:${it.final_score}`}
          defaultValue={it.final_score ?? undefined}
          placeholder="未评"
          onBlur={e => {
            const raw = (e.target as HTMLInputElement).value
            const num = raw === '' ? null : Number(raw)
            if (num !== null && Number.isNaN(num)) return
            if (num !== it.final_score) onUpdate(it, { final_score: num })
          }} />
      ),
    },
    noteCol,
  ]

  const totalScore = score.reduce((s, it) => s + (it.final_score || 0), 0)

  return (
    <>
      <Title level={5} style={{ marginTop: 16 }}>
        ④ 审查结果 — {result.bid_file_name}
        <Button size="small" icon={<DownloadOutlined />} style={{ marginLeft: 12 }}
          href={exportCsvUrl(task.id, result.id)}>导出审查表</Button>
      </Title>
      {qualFails.length > 0 ? (
        <Alert type="error" showIcon style={{ marginBottom: 8 }}
          message={`建议资格性淘汰：第 ${qualFails.map(x => x.criteria_seq).join('、')} 条资格要求不满足（以人工复核为准）`} />
      ) : compFails.length > 0 ? (
        <Alert type="error" showIcon style={{ marginBottom: 8 }}
          message={`建议符合性淘汰：第 ${compFails.map(x => x.criteria_seq).join('、')} 条实质性/商务要求不满足（以人工复核为准）`} />
      ) : (
        <Alert type="success" showIcon style={{ marginBottom: 8 }}
          message={`资格、符合性审查初判通过${unfoundCnt ? `；${unfoundCnt} 条未找到证据，请人工核查` : ''}（以人工复核为准）`} />
      )}
      <Paragraph type="secondary" style={{ marginBottom: 8 }}>
        判定、得分与批注可直接修改，自动保存并记录复核人。
      </Paragraph>

      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Text strong>资格审查（{qual.length} 条）</Text>
          <Table rowKey="id" size="small" columns={judgeColumns(false)}
            dataSource={qual} pagination={false} style={{ marginTop: 4 }} />
        </div>
        <div>
          <Text strong>符合性审查 · 实质性+商务（{comp.length} 条）</Text>
          <Table rowKey="id" size="small" columns={judgeColumns(true)}
            dataSource={comp} pagination={false} style={{ marginTop: 4 }} />
        </div>
        {task.eval_method === '综合评分法' && score.length > 0 && (
          <div>
            <Text strong>打分（{score.length} 项，不含价格分）</Text>
            <Table rowKey="id" size="small" columns={scoreColumns}
              dataSource={score} pagination={false} style={{ marginTop: 4 }}
              summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={6}>
                    <Text strong>技术商务分合计</Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={1} colSpan={2}>
                    <Text strong>{Math.round(totalScore * 100) / 100} 分</Text>
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              )} />
          </div>
        )}
      </Space>
    </>
  )
}
