import { useState } from 'react'
import {
  App, Button, Empty, Input, InputNumber, Modal, Popconfirm, Select, Space,
  Table, Tabs, Tooltip, Typography,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import {
  addCriteria, deleteCriteria, updateCriteria, CATEGORIES, LOT_COMMON,
  type Category, type CriteriaFields, type ReviewCriteria, type ReviewTask,
} from '../../services/bidReview'
import { getErr, lotTag } from './shared'

const { Text, Title } = Typography

interface Draft extends CriteriaFields {
  id: number          // 0 = 新增
}

/** ② 审查条目清单：按 资格/实质性/商务/打分 分 Tab 展示与编辑。 */
export default function CriteriaSection({ task, onSaved, canAdd }: {
  task: ReviewTask
  onSaved: () => void
  canAdd: boolean
}) {
  const { message } = App.useApp()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [activeCat, setActiveCat] = useState<Category>('资格')

  const criteria = task.criteria || []
  const showScore = task.eval_method !== '最低评标价法'
  const cats = CATEGORIES.filter(c => c !== '打分' || showScore)
  const lotOptions = [
    { value: LOT_COMMON, label: '通用（全部包）' },
    ...task.lots.map(l => ({ value: l.lot_no, label: `包${l.lot_no}` })),
  ]

  const saveDraft = async () => {
    if (!draft) return
    if (!(draft.content || '').trim()) { message.warning('条目内容不能为空'); return }
    if (draft.category === '打分' && !draft.max_score) {
      message.warning('打分项必须填写分值'); return
    }
    const data: CriteriaFields = {
      content: (draft.content || '').trim(),
      category: draft.category,
      lot_no: draft.lot_no || LOT_COMMON,
      max_score: draft.category === '打分' ? draft.max_score : null,
      score_rule: draft.category === '打分' ? (draft.score_rule || '') : '',
    }
    try {
      if (draft.id === 0) await addCriteria(task.id, data)
      else await updateCriteria(task.id, draft.id, data)
      message.success('已保存')
      setDraft(null)
      onSaved()
    } catch (err) { message.error(getErr(err, '保存失败')) }
  }

  const columnsFor = (cat: Category) => {
    const cols: object[] = [
      { title: '#', width: 50, render: (_: unknown, __: unknown, i: number) => i + 1 },
      {
        title: cat === '打分' ? '评分项' : '条目内容', dataIndex: 'content', ellipsis: true,
        render: (v: string) => <Tooltip title={<div style={{ maxHeight: 300, overflow: 'auto' }}>{v}</div>}>{v}</Tooltip>,
      },
      { title: '适用包', dataIndex: 'lot_no', width: 90, render: (v: string) => lotTag(v) },
    ]
    if (cat === '打分') {
      cols.push(
        { title: '分值', dataIndex: 'max_score', width: 70,
          render: (v: number | null) => v != null ? `${v}分` : '—' },
        { title: '评分规则', dataIndex: 'score_rule', ellipsis: true,
          render: (v: string) => v
            ? <Tooltip title={<div style={{ maxHeight: 300, overflow: 'auto' }}>{v}</div>}>{v}</Tooltip>
            : <Text type="secondary">—</Text> },
      )
    }
    cols.push(
      { title: '来源页', dataIndex: 'source_page', width: 75,
        render: (p: number | null) => p ? `第${p}页` : '—' },
      {
        title: '操作', width: 100,
        render: (_: unknown, c: ReviewCriteria) => (
          <Space size={0}>
            <Button type="link" size="small" icon={<EditOutlined />}
              onClick={() => setDraft({ ...c })} />
            <Popconfirm title="删除该条目？" okText="删除" cancelText="取消"
              onConfirm={async () => { await deleteCriteria(task.id, c.id); onSaved() }}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        ),
      },
    )
    return cols
  }

  return (
    <>
      <Title level={5} style={{ marginTop: 16 }}>② 审查条目清单</Title>
      <Space style={{ marginBottom: 4 }}>
        <Button size="small" icon={<PlusOutlined />} disabled={!canAdd}
          onClick={() => setDraft({
            id: 0, content: '', category: activeCat, lot_no: LOT_COMMON,
            max_score: null, score_rule: '',
          })}>
          手工添加条目
        </Button>
        <Text type="secondary">类别与适用包可在编辑中调整；打分项需填分值与评分规则。</Text>
      </Space>
      <Tabs size="small" activeKey={activeCat}
        onChange={k => setActiveCat(k as Category)}
        items={cats.map(cat => {
          const rows = criteria.filter(c => c.category === cat)
          return {
            key: cat,
            label: `${cat === '打分' ? '打分项' : `${cat}要求`}（${rows.length}）`,
            children: (
              <Table rowKey="id" size="small" columns={columnsFor(cat)}
                dataSource={rows} pagination={false}
                locale={{ emptyText: <Empty description="上传采购文件后自动抽取，或手工添加" /> }} />
            ),
          }
        })} />

      <Modal title={draft?.id ? '编辑条目' : '新增条目'} open={!!draft}
        onOk={saveDraft} onCancel={() => setDraft(null)} okText="保存"
        destroyOnHidden width={560}>
        {draft && (
          <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
            <Space>
              <Text>类别：</Text>
              <Select size="small" style={{ width: 110 }} value={draft.category}
                onChange={v => setDraft({ ...draft, category: v })}
                options={cats.map(c => ({ value: c, label: c }))} />
              <Text>适用包：</Text>
              <Select size="small" style={{ width: 150 }}
                value={draft.lot_no || LOT_COMMON}
                onChange={v => setDraft({ ...draft, lot_no: v })}
                options={lotOptions} />
              {draft.category === '打分' && (
                <>
                  <Text>分值：</Text>
                  <InputNumber size="small" min={0.5} style={{ width: 90 }}
                    value={draft.max_score ?? undefined}
                    onChange={v => setDraft({ ...draft, max_score: v ?? null })} />
                </>
              )}
            </Space>
            <Input.TextArea rows={3} value={draft.content}
              onChange={e => setDraft({ ...draft, content: e.target.value })}
              placeholder={draft.category === '打分' ? '评分项名称/内容' : '条目内容（保留采购文件原文表述）'}
              maxLength={1000} />
            {draft.category === '打分' && (
              <Input.TextArea rows={3} value={draft.score_rule}
                onChange={e => setDraft({ ...draft, score_rule: e.target.value })}
                placeholder="评分规则（如何给分/扣分，AI 按此给建议分）" maxLength={1000} />
            )}
          </Space>
        )}
      </Modal>
    </>
  )
}
