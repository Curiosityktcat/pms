import { useEffect, useState } from 'react'
import { Button, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  exportSummaryUrl, getSummary, LOT_COMMON,
  type ReviewTask, type SummaryRow, type TaskSummary,
} from '../../services/bidReview'

const { Text, Title } = Typography

function checkCell(fails: number[], unfound: number[]) {
  if (fails.length)
    return <Tag color="red">不满足：第{fails.join('、')}条</Tag>
  if (unfound.length)
    return (
      <Tooltip title={`第${unfound.join('、')}条未找到证据，请人工核查`}>
        <Tag color="orange">{unfound.length} 条未找到</Tag>
      </Tooltip>
    )
  return <Tag color="green">通过</Tag>
}

/** ⑤ 汇总比价：按包分组，综合评分法算价格分/总分/排名，最低评标价法按报价排序。 */
export default function SummarySection({ task, reloadKey }: {
  task: ReviewTask
  reloadKey: number
}) {
  const [data, setData] = useState<TaskSummary | null>(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    setLoading(true)
    getSummary(task.id)
      .then(r => setData(r.data.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [task.id, reloadKey])

  if (!data || !data.groups.some(g => g.rows.length)) return null
  const isScore = data.eval_method === '综合评分法'

  const columns = [
    { title: '排名', dataIndex: 'rank', width: 60,
      render: (v: number | null) => v ?? <Text type="secondary">—</Text> },
    { title: '投标方', dataIndex: 'bid_file_name', ellipsis: true },
    { title: '总报价(元)', dataIndex: 'bid_price', width: 120,
      render: (v: number | null, x: SummaryRow) => v != null
        ? <Tooltip title={x.price_edited_by ? `人工修改：${x.price_edited_by}` : 'AI 抽取，请核对'}>{v}</Tooltip>
        : <Tag color="orange">缺报价</Tag> },
    { title: '资格审查', width: 150,
      render: (_: unknown, x: SummaryRow) => checkCell(x.qual_fails, x.qual_unfound) },
    { title: '符合性审查', width: 150,
      render: (_: unknown, x: SummaryRow) => checkCell(x.compliance_fails, x.compliance_unfound) },
    ...(isScore ? [
      { title: '技术商务分', dataIndex: 'tech_score', width: 95 },
      { title: '价格分', dataIndex: 'price_score', width: 80,
        render: (v: number | null) => v ?? <Text type="secondary">—</Text> },
      { title: '总分', dataIndex: 'total', width: 80,
        render: (v: number | null) => v != null ? <Text strong>{v}</Text> : <Text type="secondary">—</Text> },
    ] : []),
    { title: '淘汰建议', dataIndex: 'eliminated', width: 100,
      render: (v: string) => v ? <Tag color="red">{v}</Tag> : '' },
  ]

  return (
    <>
      <Title level={5} style={{ marginTop: 16 }}>
        ⑤ 汇总比价
        <Space style={{ marginLeft: 12 }}>
          <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
          <Button size="small" icon={<DownloadOutlined />} href={exportSummaryUrl(task.id)}>导出汇总表</Button>
        </Space>
      </Title>
      <Text type="secondary">
        {isScore
          ? `价格分按「最低有效报价得满分（${data.price_score_max || '?'}分）、其余按比例折算」计算；淘汰与缺报价者不参与基准与排名。${data.price_formula ? `文件规则原文：${data.price_formula}` : ''}`
          : '最低评标价法：通过资格与符合性审查的投标方按报价从低到高排序。'}
      </Text>
      {data.groups.map(g => (
        <div key={g.lot_no} style={{ marginTop: 8 }}>
          {(data.groups.length > 1 || g.lot_no !== LOT_COMMON) &&
            <Text strong>包{g.lot_no}</Text>}
          <Table rowKey="result_id" size="small" style={{ marginTop: 4 }}
            columns={columns} dataSource={g.rows} pagination={false} />
        </div>
      ))}
    </>
  )
}
