import { useState } from 'react'
import {
  App, Button, Input, List, Modal, Select, Space, Table, Tag, Typography,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { updateTask, type ReviewLot, type ReviewTask } from '../../services/bidReview'

const { Text, Title } = Typography

/** ① 文件概要：评审方式 / 价格分 / 分包情况 / 标的信息（AI 识别，人工可改）。 */
export default function DocSummarySection({ task, onSaved }: {
  task: ReviewTask
  onSaved: () => void
}) {
  const { message } = App.useApp()
  const [lotsOpen, setLotsOpen] = useState(false)
  const [lotsDraft, setLotsDraft] = useState<ReviewLot[]>([])

  const save = async (data: Parameters<typeof updateTask>[1], ok = '已保存') => {
    try { await updateTask(task.id, data); message.success(ok); onSaved() }
    catch { message.error('保存失败') }
  }

  const isScore = task.eval_method === '综合评分法'
  const lotNotes = (task.summary || []).filter(s => s.kind === '分包')
  const subjects = (task.summary || []).filter(s => s.kind === '标的')

  return (
    <>
      <Title level={5}>① 文件概要与评审方式</Title>
      <Space wrap style={{ marginBottom: 8 }}>
        <Text>评审方式：</Text>
        <Select size="small" style={{ width: 140 }}
          value={task.eval_method || undefined}
          placeholder="未识别，请选择"
          onChange={v => save({ eval_method: v })}
          options={[
            { value: '综合评分法', label: '综合评分法' },
            { value: '最低评标价法', label: '最低评标价法' },
          ]} />
        {task.eval_method && <Tag color="cyan">AI 识别，可修改</Tag>}
        {isScore && (
          <>
            <Text>价格分满分：</Text>
            <Input size="small" style={{ width: 80 }}
              key={`psm:${task.price_score_max}`}
              defaultValue={task.price_score_max}
              placeholder="如 30"
              onBlur={e => {
                if (e.target.value !== task.price_score_max)
                  save({ price_score_max: e.target.value })
              }} />
            <Text>价格分规则：</Text>
            <Input size="small" style={{ width: 360 }}
              key={`pf:${task.price_formula}`}
              defaultValue={task.price_formula}
              placeholder="价格分计算规则原文（系统按最低有效报价满分比例折算）"
              onBlur={e => {
                if (e.target.value !== task.price_formula)
                  save({ price_formula: e.target.value })
              }} />
          </>
        )}
      </Space>

      <div style={{ marginBottom: 8 }}>
        <Space wrap>
          <Text strong>分包情况：</Text>
          {lotNotes.map((s, i) => <Text key={i} type="secondary">{s.content}</Text>)}
          {!lotNotes.length && !task.lots.length && <Text type="secondary">不分包/未识别</Text>}
          <Button size="small" icon={<EditOutlined />}
            onClick={() => { setLotsDraft(task.lots.map(l => ({ ...l }))); setLotsOpen(true) }}>
            编辑分包
          </Button>
        </Space>
        {task.lots.length > 0 && (
          <Table rowKey="lot_no" size="small" style={{ marginTop: 4, maxWidth: 680 }}
            dataSource={task.lots} pagination={false}
            columns={[
              { title: '包号', dataIndex: 'lot_no', width: 90 },
              { title: '包名/内容', dataIndex: 'name', ellipsis: true },
              { title: '预算/最高限价', dataIndex: 'budget', width: 180 },
            ]} />
        )}
      </div>

      {subjects.length > 0 && (
        <List size="small" style={{ marginBottom: 8, maxWidth: 900 }}
          header={<Text strong>标的信息</Text>}
          dataSource={subjects}
          renderItem={s => (
            <List.Item>
              <Text>{s.content}</Text>
              {s.source_page ? <Text type="secondary">　第{s.source_page}页</Text> : null}
            </List.Item>
          )} />
      )}

      <Modal title="编辑分包" open={lotsOpen} destroyOnHidden width={640}
        onCancel={() => setLotsOpen(false)} okText="保存"
        onOk={async () => {
          const clean = lotsDraft.filter(l => l.lot_no.trim())
          await save({ lots: clean })
          setLotsOpen(false)
        }}>
        <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
          {lotsDraft.map((l, i) => (
            <Space key={i} wrap>
              <Input size="small" style={{ width: 90 }} placeholder="包号"
                value={l.lot_no}
                onChange={e => setLotsDraft(d => d.map((x, j) => j === i ? { ...x, lot_no: e.target.value } : x))} />
              <Input size="small" style={{ width: 260 }} placeholder="包名/内容"
                value={l.name}
                onChange={e => setLotsDraft(d => d.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
              <Input size="small" style={{ width: 150 }} placeholder="预算/限价"
                value={l.budget}
                onChange={e => setLotsDraft(d => d.map((x, j) => j === i ? { ...x, budget: e.target.value } : x))} />
              <Button size="small" danger icon={<DeleteOutlined />}
                onClick={() => setLotsDraft(d => d.filter((_, j) => j !== i))} />
            </Space>
          ))}
          <Button size="small" icon={<PlusOutlined />}
            onClick={() => setLotsDraft(d => [...d, { lot_no: '', name: '', budget: '' }])}>
            添加包
          </Button>
          <Text type="secondary">注意：修改包号后请同步检查条目的适用包与已上传投标文件的所投包。</Text>
        </Space>
      </Modal>
    </>
  )
}
