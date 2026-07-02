/**
 * 文档式填空编辑器（学四川政采的「数据驱动文档式编辑」）。
 * 左：章节大纲+完成度；中：A4 文档预览，未填字段黄色高亮占位，点击行内编辑；
 * 顶：保存(自动+手动)、导出Word、状态。数据结构化存库，模板由后端配置。
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  App, Button, Input, Select, DatePicker, Progress, Tag, Spin, Affix,
} from 'antd'
import {
  SaveOutlined, DownloadOutlined, CheckCircleOutlined, ArrowLeftOutlined, EditOutlined,
  PlusOutlined, DeleteOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getDocTemplate, getDocForm, saveDocForm, docWordUrl,
  type DocTemplate, type DocField, type FieldValue, type TableRow,
} from '../services/docForm'

type Values = Record<string, FieldValue>

function isFilled(f: DocField, v: FieldValue | undefined): boolean {
  if (f.type === 'table') return Array.isArray(v) && v.length > 0
  return String(v ?? '').trim().length > 0
}

export default function DocFormEditor({ projectId, templateKey, onBack }: {
  projectId: number; templateKey: string; onBack?: () => void
}) {
  const { message } = App.useApp()
  const [tpl, setTpl] = useState<DocTemplate | null>(null)
  const [values, setValues] = useState<Values>({})
  const [status, setStatus] = useState<'草稿' | '已完成'>('草稿')
  const [projectName, setProjectName] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const midRef = useRef<HTMLDivElement>(null)
  const valuesRef = useRef<Values>({})   // 持有最新 values 供定时保存
  valuesRef.current = values

  useEffect(() => {
    setLoading(true)
    Promise.all([getDocTemplate(templateKey), getDocForm(projectId, templateKey)])
      .then(([t, f]) => {
        setTpl(t.data.data)
        setValues(f.data.data.data || {})
        setStatus(f.data.data.status)
        setProjectName(f.data.data.project_name || '')
      })
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }, [projectId, templateKey, message])

  const doSave = useCallback(async (silent = false, st?: '草稿' | '已完成') => {
    setSaving(true)
    try {
      const res = await saveDocForm(projectId, templateKey,
        { data: valuesRef.current, ...(st ? { status: st } : {}) })
      setDirty(false)
      if (st) setStatus(res.data.data.status)
      if (!silent) message.success('已保存')
    } catch { if (!silent) message.error('保存失败') }
    finally { setSaving(false) }
  }, [projectId, templateKey, message])

  const onField = (key: string, v: FieldValue) => {
    setValues(prev => ({ ...prev, [key]: v }))
    setDirty(true)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => doSave(true), 1500)   // 自动保存
  }
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const progress = useMemo(() => {
    if (!tpl) return { filled: 0, total: 0 }
    const fs = tpl.sections.flatMap(s => s.fields)
    const filled = fs.filter(f => isFilled(f, values[f.key])).length
    return { filled, total: fs.length }
  }, [tpl, values])

  const scrollTo = (secKey: string) => {
    const el = midRef.current?.querySelector(`#sec-${secKey}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const markDone = async () => {
    await doSave(true, status === '已完成' ? '草稿' : '已完成')
    message.success(status === '已完成' ? '已退回草稿' : '已标记完成')
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 80 }}><Spin tip="加载中…" /></div>
  if (!tpl) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 112px)' }}>
      {/* 顶栏 */}
      <Affix offsetTop={0}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px',
          background: '#fff', borderBottom: '1px solid #f0f0f0', boxShadow: '0 1px 4px rgba(0,0,0,.05)',
        }}>
          {onBack && <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回</Button>}
          <span style={{ fontWeight: 700, fontSize: 15 }}>{tpl.name}</span>
          <Tag color="blue" style={{ maxWidth: 320 }} title={projectName}>
            <span style={{ display: 'inline-block', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' }}>{projectName}</span>
          </Tag>
          <Tag color={status === '已完成' ? 'green' : 'orange'}>{status}</Tag>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 12, color: '#888' }}>完成度 {progress.filled}/{progress.total}</span>
          <Progress percent={progress.total ? Math.round(progress.filled / progress.total * 100) : 0}
            style={{ width: 120 }} size="small" />
          <Button icon={<SaveOutlined />} loading={saving} onClick={() => doSave(false)}>
            {dirty ? '保存*' : '保存'}
          </Button>
          <Button icon={<DownloadOutlined />}
            onClick={() => window.open(docWordUrl(projectId, templateKey), '_blank')}>导出Word</Button>
          <Button type={status === '已完成' ? 'default' : 'primary'} icon={<CheckCircleOutlined />}
            onClick={markDone}>{status === '已完成' ? '撤销完成' : '标记完成'}</Button>
        </div>
      </Affix>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* 左：章节大纲 */}
        <div style={{ width: 210, borderRight: '1px solid #f0f0f0', overflowY: 'auto', background: '#fafafa', padding: '12px 0' }}>
          {tpl.sections.map(sec => {
            const fs = sec.fields
            const filled = fs.filter(f => isFilled(f, values[f.key])).length
            const done = filled === fs.length
            return (
              <div key={sec.key} onClick={() => scrollTo(sec.key)}
                style={{ padding: '8px 14px', cursor: 'pointer', fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                onMouseEnter={e => (e.currentTarget.style.background = '#f0f0f0')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                <span style={{ color: done ? '#52c41a' : '#333' }}>{sec.title}</span>
                <span style={{ fontSize: 11, color: done ? '#52c41a' : '#bbb' }}>{filled}/{fs.length}</span>
              </div>
            )
          })}
        </div>

        {/* 中：A4 文档 */}
        <div ref={midRef} style={{ flex: 1, overflowY: 'auto', background: '#f0f2f5', padding: '24px 0' }}>
          <div style={{
            maxWidth: 820, margin: '0 auto', background: '#fff', boxShadow: '0 2px 12px rgba(0,0,0,.08)',
            padding: '48px 56px', minHeight: '100%', fontFamily: '宋体, SimSun, serif',
          }}>
            <h1 style={{ textAlign: 'center', fontSize: 24, margin: '0 0 4px', fontWeight: 700 }}>{tpl.name}</h1>
            {tpl.subtitle && <div style={{ textAlign: 'center', color: '#999', marginBottom: 28 }}>{tpl.subtitle}</div>}
            {tpl.sections.map(sec => (
              <section key={sec.key} id={`sec-${sec.key}`} style={{ marginBottom: 26 }}>
                <h3 style={{ fontSize: 16, fontWeight: 700, borderLeft: '4px solid #1677ff', paddingLeft: 10, margin: '0 0 12px' }}>{sec.title}</h3>
                {sec.fields.map(f => (
                  <FieldRow key={f.key} field={f} value={values[f.key]}
                    onChange={v => onField(f.key, v)} />
                ))}
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── 单字段（文档式：显示态 + 点击行内编辑）──────────────────────
function FieldRow({ field, value, onChange }: {
  field: DocField; value: FieldValue | undefined; onChange: (v: FieldValue) => void
}) {
  const [editing, setEditing] = useState(false)
  if (field.type === 'table') return <TableField field={field} value={value} onChange={onChange} />
  const val = value === undefined || value === null ? '' : String(value)
  const empty = !val.trim()

  const placeholder = (
    <span style={{ background: '#fff3cd', color: '#b8860b', padding: '0 8px', borderRadius: 3, cursor: 'pointer', fontStyle: 'normal' }}>
      （点击填写）
    </span>
  )
  const shownValue = empty ? placeholder : (
    <span style={{ cursor: 'pointer', whiteSpace: 'pre-wrap' }}>{val}</span>
  )

  const editor = (() => {
    const common = { autoFocus: true, style: { width: '100%' } as React.CSSProperties }
    if (field.type === 'textarea')
      return <Input.TextArea {...common} autoSize={{ minRows: 2, maxRows: 12 }} defaultValue={val}
        onBlur={e => { setEditing(false); if (e.target.value !== val) onChange(e.target.value) }} />
    if (field.type === 'select')
      return <Select {...common} defaultValue={val || undefined} options={(field.options || []).map(o => ({ value: o, label: o }))}
        onChange={v => { onChange(v); setEditing(false) }} onBlur={() => setEditing(false)} open autoClearSearchValue />
    if (field.type === 'date')
      return <DatePicker {...common} defaultValue={val ? dayjs(val) : undefined}
        onChange={d => { onChange(d ? d.format('YYYY-MM-DD') : ''); setEditing(false) }} open onOpenChange={o => !o && setEditing(false)} />
    return <Input {...common} type={field.type === 'number' ? 'number' : 'text'} defaultValue={val}
      onPressEnter={e => { setEditing(false); const t = (e.target as HTMLInputElement).value; if (t !== val) onChange(t) }}
      onBlur={e => { setEditing(false); if (e.target.value !== val) onChange(e.target.value) }} />
  })()

  if (field.layout === 'block') {
    return (
      <div style={{ marginBottom: 14, lineHeight: 1.9, fontSize: 14 }}>
        <div style={{ fontWeight: 600 }}>{field.label}{field.required && <span style={{ color: 'red' }}> *</span>}：</div>
        {editing ? editor : (
          <div onClick={() => setEditing(true)} style={{ minHeight: 26, paddingLeft: 2 }}>
            {empty ? placeholder : <span style={{ whiteSpace: 'pre-wrap', cursor: 'pointer' }}>{val}</span>}
            {!empty && <EditOutlined style={{ color: '#ccc', marginLeft: 6, fontSize: 12 }} />}
          </div>
        )}
      </div>
    )
  }
  return (
    <div style={{ marginBottom: 8, lineHeight: 2, fontSize: 14 }}>
      <span style={{ fontWeight: 600 }}>{field.label}{field.required && <span style={{ color: 'red' }}> *</span>}：</span>
      {editing ? <span style={{ display: 'inline-block', minWidth: 260, verticalAlign: 'middle' }}>{editor}</span>
        : <span onClick={() => setEditing(true)}>{shownValue}</span>}
    </div>
  )
}

// ── 动态表格字段（标的情况 / 评审因素 等）──────────────────────
function TableField({ field, value, onChange }: {
  field: DocField; value: FieldValue | undefined; onChange: (v: FieldValue) => void
}) {
  const rows: TableRow[] = Array.isArray(value) ? value : []
  const cols = field.columns || []
  const set = (rs: TableRow[]) => onChange(rs)
  const cell: React.CSSProperties = { border: '1px solid #ddd', padding: '2px 6px' }
  const th: React.CSSProperties = { ...cell, background: '#fafafa', fontWeight: 600, textAlign: 'center' }
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{field.label}：</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>{cols.map(c => <th key={c.key} style={th}>{c.label}</th>)}<th style={{ ...th, width: 40 }} /></tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={cols.length + 1} style={{ ...cell, textAlign: 'center', color: '#b8860b', background: '#fff3cd' }}>
              （暂无，点下方「添加行」）
            </td></tr>
          )}
          {rows.map((row, ri) => (
            <tr key={ri}>
              {cols.map(c => (
                <td key={c.key} style={cell}>
                  <Input size="small" variant="borderless" value={row[c.key] || ''}
                    onChange={e => set(rows.map((r, i) => i === ri ? { ...r, [c.key]: e.target.value } : r))} />
                </td>
              ))}
              <td style={{ ...cell, textAlign: 'center' }}>
                <Button size="small" type="text" danger icon={<DeleteOutlined />}
                  onClick={() => set(rows.filter((_, i) => i !== ri))} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button size="small" type="dashed" icon={<PlusOutlined />} style={{ marginTop: 6 }}
        onClick={() => set([...rows, {}])}>添加行</Button>
    </div>
  )
}
