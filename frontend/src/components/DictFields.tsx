/**
 * 字段字典驱动的表单区：出现/锁定/带值全听后端的。
 *
 * 黄新博 2026-08-19 认可的方向：条件与联动放字段字典，Word 模板保持「笨」。
 * 这里是它在界面上的那一半——**前端不写任何业务判断**，
 * 每次改动就把当前值发给 /field-dict/resolve，后端算完告诉界面：
 * 哪些字段该出现、哪些锁成什么值、哪句提示。
 *
 * 好处是判断只有一份：不会出现「界面让填、出稿却被纠正」这种对不上的情况。
 */
import { useCallback, useEffect, useState } from 'react'
import { Checkbox, Input, InputNumber, Radio, Space, Spin, Tag, Tooltip, Typography } from 'antd'
import { LockOutlined, InfoCircleOutlined } from '@ant-design/icons'
import { getFieldDict, resolveFieldDict, type DictField, type DictMeta } from '../services/procurementDemand'

const { Text } = Typography

export interface DictFieldsProps {
  /** 只渲染这几个字段（按给的顺序） */
  names: string[]
  values: Record<string, unknown>
  onChange: (patch: Record<string, unknown>) => void
  title?: string
}

export default function DictFields({ names, values, onChange, title }: DictFieldsProps) {
  const [dict, setDict] = useState<DictField[]>([])
  const [meta, setMeta] = useState<Record<string, DictMeta>>({})
  const [eff, setEff] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getFieldDict().then(r => setDict(r.data.data)).finally(() => setLoading(false))
  }, [])

  const recompute = useCallback((v: Record<string, unknown>) => {
    resolveFieldDict(v).then(r => {
      setMeta(r.data.data.meta)
      setEff(r.data.data.values)
      // 后端纠正过的值要写回表单，否则界面显示的和成稿里的不是一回事
      const fixed: Record<string, unknown> = {}
      Object.entries(r.data.data.values).forEach(([k, val]) => {
        if (names.includes(k) && v[k] !== val) fixed[k] = val
      })
      if (Object.keys(fixed).length) onChange(fixed)
    }).catch(() => { /* 取不到就按原样显示，不挡着人填 */ })
  }, [names, onChange])

  useEffect(() => { recompute(values) }, [JSON.stringify(values)])   // eslint-disable-line

  if (loading) return <Spin size="small" />

  const shown = names
    .map(n => dict.find(f => f.name === n))
    .filter((f): f is DictField => !!f && (meta[f.name]?.visible ?? true))

  if (!shown.length) return null

  return (
    <div>
      {title && <div style={{ fontWeight: 600, margin: '4px 0 10px' }}>{title}</div>}
      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        {shown.map(f => {
          const m = meta[f.name] || {}
          const val = (eff[f.name] ?? values[f.name] ?? undefined) as never
          const set = (v: unknown) => onChange({ [f.name]: v })
          const opts = (f.options || []).map(o =>
            typeof o === 'string' ? { label: o, text: '' } : o)

          return (
            <div key={f.name}>
              <Space size={6} wrap style={{ marginBottom: 4 }}>
                <Text strong style={{ fontSize: 13 }}>{f.label || f.name}</Text>
                {m.locked && (
                  <Tooltip title={m.locked_reason || '固定值，不可修改'}>
                    <Tag color="default" style={{ marginInlineEnd: 0 }}>
                      <LockOutlined /> 固定
                    </Tag>
                  </Tooltip>
                )}
                {f.required && <Tag color="red" style={{ marginInlineEnd: 0 }}>必填</Tag>}
              </Space>

              {f.kind === 'choice' && (
                <Radio.Group value={val} disabled={m.locked}
                  onChange={e => set(e.target.value)}>
                  <Space direction={opts.some(o => (o.text || '').length > 30) ? 'vertical' : 'horizontal'}
                    size={opts.some(o => (o.text || '').length > 30) ? 8 : 16} wrap>
                    {opts.map(o => (
                      <Radio key={o.label} value={o.label} style={{ alignItems: 'flex-start' }}>
                        <span style={{ fontSize: 13 }}>{o.label}</span>
                        {o.text && (
                          <div style={{ fontSize: 12, color: '#5f6368', maxWidth: 620,
                                        lineHeight: 1.5, marginTop: 2 }}>{o.text}</div>
                        )}
                      </Radio>
                    ))}
                  </Space>
                </Radio.Group>
              )}

              {f.kind === 'multi' && (
                <Checkbox.Group value={(val as unknown as string[]) || []}
                  disabled={m.locked}
                  options={opts.map(o => ({ label: o.label, value: o.label }))}
                  onChange={v => set(v)} />
              )}

              {f.kind === 'number' && (
                <InputNumber style={{ width: 220 }} value={val as unknown as number}
                  disabled={m.locked} addonAfter={f.unit}
                  min={f.min} max={f.max} precision={f.decimals}
                  onChange={v => set(v)} />
              )}

              {(f.kind === 'text' || !f.kind) && (
                // 写死的法条原文用只读多行框，让人看得全但改不了
                m.locked
                  ? <Input.TextArea value={String(val ?? '')} readOnly autoSize={{ minRows: 2, maxRows: 8 }}
                      style={{ background: '#fafafa', fontSize: 12 }} />
                  : <Input value={String(val ?? '')} onChange={e => set(e.target.value)} />
              )}

              {m.hint && (
                <div style={{ fontSize: 12, color: '#5f6368', marginTop: 4 }}>
                  <InfoCircleOutlined /> {m.hint}
                </div>
              )}
              {m.locked && m.locked_reason && (
                <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>
                  {m.locked_reason}
                </div>
              )}
            </div>
          )
        })}
      </Space>
    </div>
  )
}
