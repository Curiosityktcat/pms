import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App, Button, Empty, Input, InputNumber, Modal, Popconfirm, Select, Space, Spin,
  Steps, Table, Tag, Tooltip, Typography,
} from 'antd'
import {
  ArrowDownOutlined, ArrowUpOutlined, CheckCircleFilled, DeleteOutlined,
  DownloadOutlined, EditOutlined, PlusOutlined, RobotOutlined,
} from '@ant-design/icons'
import DemandAgentChat from './DemandAgentChat'
import {
  demandDocUrl, getDemandDocHtml, getDemandDocStatus, updateDemand,
  type DemandDocBlock, type DemandDocStatus, type DemandDocStructure,
} from '../services/procurementDemand'
import { getDeptMe } from '../services/deptPortal'
import { useAuth } from '../hooks/useAuth'
import './DemandDocWorkspace.css'

const { TextArea } = Input
const { Text } = Typography

type WorkspaceStep = 0 | 1
type TechnicalMark = '' | '★' | '▲'
interface TechnicalRow { mark: TechnicalMark; name: string; content: string }

const PROJECT_FIELDS: Record<string, { saveKey: string; control: DemandDocBlock['control'] }> = {
  '项目名称': { saveKey: 'project_name', control: 'text' },
  '需求科室': { saveKey: 'demand_dept', control: 'text' },
  '归口管理科室': { saveKey: 'manage_dept', control: 'text' },
  '所属年度': { saveKey: 'year', control: 'text' },
  '项目所属分类': { saveKey: 'category', control: 'select' },
  '预算金额': { saveKey: 'budget_amount', control: 'number' },
}

const FIRST_STEP_FIELDS = new Set([
  ...Object.keys(PROJECT_FIELDS), '项目概况', '采购组织形式', '采购方式', '采购包划分',
  '包名称', '最高限价', '评审方法', '是否允许合同分包', '标的',
])

const YES_NO_OPTIONS = ['是', '否']
const REVIEW_METHOD_OPTIONS = ['综合评分法', '最低评标价法']

const moneyFormatter = (value: string | number | undefined) =>
  `${value ?? ''}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
const moneyParser = (value: string | undefined) =>
  Number((value || '').replace(/,/g, ''))

const reviewMethodsFor = (method: unknown) => {
  if (method === '竞争性谈判' || method === '询价') return ['最低评标价法']
  if (method === '竞争性磋商') return ['综合评分法']
  if (method === '单一来源') return []
  return REVIEW_METHOD_OPTIONS
}

const hasValue = (value: unknown) => value !== null && value !== undefined
  && value !== '' && !(Array.isArray(value) && value.length === 0)
  && !(typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value as object).length === 0)

const blockId = (block: DemandDocBlock) =>
  `${block.field_path}-${block.package_index ?? 'root'}-${block.package_field ?? ''}-${block.item_index ?? ''}`

const displayValue = (value: unknown) => hasValue(value) ? String(value) : '{{未填写}}'

const isFirstStepBlock = (block: DemandDocBlock) => {
  const name = block.package_field || block.field || block.label
  // 包级预算是立项时要定的，全局预算则由上面的项目字段单独判定。
  return FIRST_STEP_FIELDS.has(name)
    || (block.package_index !== undefined && name === '预算金额')
}

const normaliseMark = (value: unknown): TechnicalMark => {
  const text = String(value ?? '').trim()
  return text === '★' || text === '▲' ? text : ''
}

const parsePastedLines = (text: string): TechnicalRow[] => text.split(/\r?\n/)
  .map(line => line.trim()).filter(Boolean).map(line => {
    const cells = line.split('\t').map(cell => cell.trim())
    if (cells.length >= 4 && /^\d+[、.\uff0e)]?$/.test(cells[0])) {
      return { mark: normaliseMark(cells[1]), name: cells[2], content: cells.slice(3).join('\t') }
    }
    if (cells.length >= 3 && normaliseMark(cells[0])) {
      return { mark: normaliseMark(cells[0]), name: cells[1], content: cells.slice(2).join('\t') }
    }
    const withoutNo = line.replace(/^\s*\d+[\u3001.\uff0e)]\s*/, '')
    const mark = normaliseMark(withoutNo.slice(0, 1))
    return { mark, name: '', content: mark ? withoutNo.slice(1).trim() : withoutNo }
  })

const parseTechnicalRows = (value: unknown): TechnicalRow[] => {
  if (!hasValue(value)) return []
  if (typeof value === 'string') {
    try {
      const blocks = JSON.parse(value) as unknown
      if (Array.isArray(blocks)) {
        const rows = blocks.flatMap(block => {
          if (!block || typeof block !== 'object') return []
          const candidate = (block as { rows?: unknown[][] }).rows
          return Array.isArray(candidate) ? candidate : []
        })
        if (rows.length) return rows.map(row => ({
          mark: normaliseMark(row[0]), name: String(row[2] ?? ''), content: String(row[3] ?? ''),
        }))
      }
    } catch { /* 老数据是换行文本，继续按行兼容 */ }
    return parsePastedLines(value)
  }
  return []
}

const serialiseTechnicalRows = (rows: TechnicalRow[], title = '') => {
  const filled = rows.filter(row => row.name.trim() || row.content.trim())
  if (!filled.length) return ''
  return JSON.stringify([{
    kind: 'table',
    ...(title ? { title } : {}),
    header: ['参数性质', '序号', '技术要求名称', '技术参数与性能指标'],
    rows: filled.map((row, index) => [row.mark, index + 1, row.name.trim(), row.content.trim()]),
  }], null, 0)
}

const parseDepartments = (value: unknown) => String(value || '').split('、')
  .map(name => name.trim()).filter(Boolean)

const buildPackageRequirement = (items: Record<string, unknown>[], field: '技术要求' | '商务要求') => {
  if (field === '商务要求') return JSON.stringify(items.flatMap(item => {
    const content = String(item[field] || '').trim()
    return content ? [{ kind: 'p', text: `标的名称：${String(item['标的名称'] || '')}\n${content}` }] : []
  }))
  return JSON.stringify(items.flatMap(item => {
    try {
      const blocks = JSON.parse(String(item[field] || '')) as Record<string, unknown>[]
      return Array.isArray(blocks) ? blocks.map(block => ({
        ...block, title: String(item['标的名称'] || block.title || ''),
      })) : []
    } catch { return [] }
  }))
}

const enrichStructure = (source: DemandDocStructure): DemandDocStructure => ({
  ...source,
  sections: source.sections.map(section => ({
    ...section,
    blocks: section.blocks.flatMap(block => {
      const project = block.package_index === undefined
        ? PROJECT_FIELDS[block.field || block.label] : undefined
      const current = project ? {
        ...block, field: block.field || block.label, editable: true, required: true,
        locked: false, lock_reason: '', save_key: project.saveKey, control: project.control,
      } : block
      if (current.package_index === undefined || current.package_field !== '预算金额') return [current]
      const index = current.package_index
      const pkg = source.packages[index] || {}
      const packageName: DemandDocBlock = {
        kind: 'field', label: `合同包${index + 1} · 包名称`, field: '包名称',
        field_path: 'subcontract.packageName', class_name: 'subcontract-packageName',
        value: pkg['包名称'] || `采购包${index + 1}`, editable: true, required: true,
        control: 'text', save_key: 'packages_json', package_index: index, package_field: '包名称',
      }
      return [packageName, current]
    }),
  })),
})

function TechnicalEditor({ block, saving, onSave }: {
  block: DemandDocBlock
  saving: boolean
  onSave: (value: string) => Promise<void>
}) {
  const [rows, setRows] = useState<TechnicalRow[]>(() => parseTechnicalRows(block.value))

  useEffect(() => { setRows(parseTechnicalRows(block.value)) }, [block.value])

  const patchRow = (index: number, patch: Partial<TechnicalRow>) =>
    setRows(current => current.map((row, i) => i === index ? { ...row, ...patch } : row))
  const moveRow = (index: number, offset: -1 | 1) => setRows(current => {
    const target = index + offset
    if (target < 0 || target >= current.length) return current
    const next = [...current]
    ;[next[index], next[target]] = [next[target], next[index]]
    return next
  })

  return <div className="demand-technical-editor">
    <TextArea rows={2} className="demand-technical-paste"
      placeholder="整段粘贴到这里，系统会按换行拆成多条参数"
      onPaste={event => {
        const pasted = parsePastedLines(event.clipboardData.getData('text'))
        if (!pasted.length) return
        event.preventDefault()
        setRows(current => [...current, ...pasted])
      }} />
    {rows.map((row, index) => <div className="demand-technical-row" key={index}>
      <span className="demand-technical-no">{index + 1}</span>
      <Select value={row.mark} options={[
        { value: '', label: '无标识' }, { value: '★', label: '★' }, { value: '▲', label: '▲' },
      ]} onChange={mark => patchRow(index, { mark })} />
      <Input value={row.name} placeholder="技术要求名称"
        onChange={event => patchRow(index, { name: event.target.value })} />
      <TextArea value={row.content} autoSize={{ minRows: 2, maxRows: 6 }}
        placeholder="技术参数与性能指标"
        onChange={event => patchRow(index, { content: event.target.value })} />
      <Space.Compact direction="vertical">
        <Button size="small" icon={<ArrowUpOutlined />} disabled={index === 0}
          onClick={() => moveRow(index, -1)} />
        <Button size="small" icon={<ArrowDownOutlined />} disabled={index === rows.length - 1}
          onClick={() => moveRow(index, 1)} />
        <Button size="small" danger icon={<DeleteOutlined />}
          onClick={() => setRows(current => current.filter((_, i) => i !== index))} />
      </Space.Compact>
    </div>)}
    <Space>
      <Button size="small" icon={<PlusOutlined />}
        onClick={() => setRows(current => [...current, { mark: '', name: '', content: '' }])}>
        新增一行
      </Button>
      <Button size="small" type="primary" loading={saving}
        onClick={() => void onSave(serialiseTechnicalRows(rows, block.item_name))}>保存技术参数</Button>
    </Space>
    <div className="demand-editor-hint">★ 是实质性条款，▲ 是重要条款；整段粘贴后可再逐条补名称和标识。</div>
  </div>
}

export default function DemandDocWorkspace({ demandId, onChanged, onUnavailable }: {
  demandId: number
  onChanged?: () => void
  onUnavailable?: () => void
}) {
  const { message } = App.useApp()
  const { user } = useAuth()
  const [doc, setDoc] = useState<DemandDocStructure | null>(null)
  const [status, setStatus] = useState<DemandDocStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [step, setStep] = useState<WorkspaceStep>(0)
  const [active, setActive] = useState('')
  const [saving, setSaving] = useState('')
  const [tableBlock, setTableBlock] = useState<DemandDocBlock | null>(null)
  const [tableRows, setTableRows] = useState<unknown[][]>([])
  const [departments, setDepartments] = useState<{ code: string; name: string }[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [html, statusResult] = await Promise.all([
        getDemandDocHtml(demandId),
        getDemandDocStatus(demandId).catch(() => null),
      ])
      setDoc(enrichStructure(html.data.data))
      setStatus(statusResult?.data.data || null)
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { error?: string } } })
        ?.response?.data?.error
      message.warning(detail || '正文结构读取失败，已切换到备用表单')
      onUnavailable?.()
    } finally {
      setLoading(false)
    }
  }, [demandId, message, onUnavailable])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    getDeptMe().then(result => {
      const info = result.data.data
      const choices = info.depts || (info.dept ? [info.dept] : [])
      setDepartments(choices.map(item => ({ code: item.code, name: item.name })))
    }).catch(() => {
      // 科室字典暂时不可用时保留已有值，不能为了一个下拉让整张需求无法编辑。
      setDepartments(user?.dept_name ? [{ code: user.dept_code, name: user.dept_name }] : [])
    })
  }, [user?.dept_code, user?.dept_name])

  const visibleSections = useMemo(() => (doc?.sections || []).map(section => ({
    ...section,
    blocks: section.blocks.filter(block => step === 0
      ? isFirstStepBlock(block) : !isFirstStepBlock(block)),
  })).filter(section => section.blocks.length), [doc, step])

  const editItems = useMemo(() => visibleSections.flatMap(section => section.blocks)
    .filter(block => block.editable), [visibleSections])

  const procurementMethod = useMemo(() => (doc?.sections || []).flatMap(section => section.blocks)
    .find(block => block.field === '采购方式')?.value, [doc])

  const invalidReviewScores = useMemo(() => (doc?.sections || []).flatMap(section => section.blocks)
    .filter(block => block.field === '评审因素' && block.package_index !== undefined
      && doc?.packages[block.package_index]?.['评审方法'] === '综合评分法'
      && hasValue(block.value))
    .filter(block => (block.rows || []).reduce((sum, row) => String(row[0] || '') === '价格扣除'
      ? sum : sum + (Number(row[1]) || 0), 0) !== 100), [doc])

  const fillStepMissingCount = useMemo(() => {
    const missing = (doc?.sections || []).flatMap(section => section.blocks)
      .filter(block => !isFirstStepBlock(block) && block.required && !hasValue(block.value)).length
    return missing + invalidReviewScores.length
  }, [doc, invalidReviewScores])

  const firstStepMissing = useMemo(() => {
    const seen = new Set<string>()
    return (doc?.sections || []).flatMap(section => section.blocks)
      .filter(block => isFirstStepBlock(block) && block.required && !hasValue(block.value))
      .filter(block => {
        const key = block.package_index === undefined
          ? (block.field || block.label) : blockId(block)
        if (seen.has(key)) return false
        seen.add(key); return true
      }).map(block => ({ name: block.field || block.label, label: block.label, kind: block.kind }))
  }, [doc])

  const patchBlock = (target: DemandDocBlock, value: unknown) => {
    setDoc(current => current && ({
      ...current,
      sections: current.sections.map(section => ({
        ...section,
        blocks: section.blocks.map(block => blockId(block) === blockId(target)
          ? { ...block, value } : block),
        incomplete: section.blocks.some(block => {
          const nextValue = blockId(block) === blockId(target) ? value : block.value
          return block.required && !hasValue(nextValue)
        }),
      })),
    }))
  }

  const selectBlock = (block: DemandDocBlock) => {
    if (!block.editable) return
    const id = blockId(block)
    setActive(id)
    window.setTimeout(() => {
      const card = document.getElementById(`editor-${id}`)
      card?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      card?.querySelector<HTMLElement>('textarea,input,button')?.focus()
    }, 30)
  }

  const saveValue = async (block: DemandDocBlock, value: unknown) => {
    if (!block.save_key || !doc) return
    const id = blockId(block)
    setSaving(id)
    try {
      // 标的表一律走主清单保存：包内那张块的 save_key 是 packages_json，
      // 只写包不写 items_json，而成稿读的是 items_json——填了不出稿。
      // 这条路径本来就会把包内镜像一并写回，两处不会再各说各话。
      if (block.save_key === 'items' || block.field === '标的') {
        const items = Array.isArray(value) ? value as Record<string, unknown>[] : []
        // 标的主清单仍写 items_json，包内再镜像一份，后续每标的技术/商务要求才有稳定挂点。
        // 镜像时按列规范全字段映射。原来这里手写了 7 个键，新增的单价、
        // 节能/环保/进口及原因会在镜像这一步悄悄丢掉。
        const cols = block.columns || []
        const packages = doc.packages.map((pkg, index) => {
          const previous = Array.isArray(pkg['标的']) ? pkg['标的'] as Record<string, unknown>[] : []
          const mine = items.filter(item => String(item.package_no || '1') === String(index + 1))
          const rows = mine.map((item, itemIndex) => {
            const row: Record<string, unknown> = { ...previous[itemIndex], 包号: item.package_no }
            cols.forEach(col => { row[col.cn] = item[col.key] })
            return row
          })
          // 包最高限价 = 本包各标的合计金额之和。黄新博 2026-08-25：系统该自己算。
          const sum = mine.reduce((acc, item) => acc + (Number(item.amount) || 0), 0)
          return { ...pkg, 标的: rows, ...(sum > 0 ? { 最高限价: Number(sum.toFixed(2)) } : {}) }
        })
        await updateDemand(demandId, { items: items as never, packages_json: JSON.stringify(packages) })
        setDoc(current => current ? { ...current, packages } : current)
      } else if (block.save_key === 'packages_json') {
        const stored = block.control === 'number'
          ? Number(String(value || 0).replace(/,/g, '')) : value
        const packages = doc.packages.map((item, index) => index === block.package_index
          ? (() => {
            if (block.item_index === undefined) {
              return { ...item, [block.package_field || block.field || '']: stored }
            }
            const itemRows = Array.isArray(item['标的'])
              ? (item['标的'] as Record<string, unknown>[]).map(row => ({ ...row })) : []
            while (itemRows.length <= block.item_index) itemRows.push({})
            const itemField = block.package_field as '技术要求' | '商务要求'
            itemRows[block.item_index] = { ...itemRows[block.item_index],
              标的名称: block.item_name || itemRows[block.item_index]['标的名称'] || '',
              [itemField]: stored }
            return { ...item, 标的: itemRows,
              [itemField]: buildPackageRequirement(itemRows, itemField) }
          })() : item)
        await updateDemand(demandId, { packages_json: JSON.stringify(packages) })
        setDoc(current => current ? { ...current, packages } : current)
      } else {
        const stored = block.control === 'number'
          ? Number(String(value || 0).replace(/,/g, '')) : value
        if (block.field === '采购方式') {
          // 成稿优先读取 budget_method，列表又读取 procurement_method；两列必须同写，
          // 否则右边显示保存成功，重新打开却会被旧值盖回来。
          const methods = reviewMethodsFor(stored)
          const packages = doc.packages.map(pkg => ({
            ...pkg, 评审方法: methods.length === 1 ? methods[0]
              : methods.length === 0 ? '' : pkg['评审方法'],
          }))
          await updateDemand(demandId, {
            budget_method: String(stored ?? ''), procurement_method: String(stored ?? ''),
            packages_json: JSON.stringify(packages),
          })
          setDoc(current => current ? { ...current, packages } : current)
        } else {
          await updateDemand(demandId, { [block.save_key]: stored })
        }
      }
      patchBlock(block, value)
      message.success('已保存')
      onChanged?.()
      getDemandDocStatus(demandId).then(result => setStatus(result.data.data)).catch(() => {})
      if (block.save_key === 'items' || block.item_index !== undefined || block.field === '采购方式') {
        await load()
      }
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { error?: string } } })
        ?.response?.data?.error
      message.error(detail || `「${block.label}」保存失败`)
      await load()
    } finally {
      setSaving('')
    }
  }

  const changePackageCount = async (offset: -1 | 1) => {
    if (!doc || (offset < 0 && doc.packages.length <= 1)) return
    const reviewMethods = reviewMethodsFor(procurementMethod)
    const packages = offset > 0 ? [...doc.packages, {
      包名称: `采购包${doc.packages.length + 1}`,
      评审方法: reviewMethods.length === 1 ? reviewMethods[0] : '',
      是否允许合同分包: '否',
    }] : doc.packages.slice(0, -1)
    setSaving('packages')
    try {
      // 包数量和 packages_json 一起落库，避免列表页与成稿各认一份数量。
      await updateDemand(demandId, {
        packages_json: JSON.stringify(packages), package_count: packages.length,
      })
      message.success(offset > 0 ? '已新增采购包' : '已删除最后一个采购包')
      onChanged?.()
      await load()
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { error?: string } } })
        ?.response?.data?.error
      message.error(detail || '采购包调整失败')
    } finally { setSaving('') }
  }

  const openTable = (block: DemandDocBlock) => {
    setActive(blockId(block)); setTableBlock(block)
    setTableRows((block.rows || []).map(row => [...row]))
  }

  const saveTable = async () => {
    if (!tableBlock) return
    let value: unknown
    if (tableBlock.field === '评审因素') {
      value = Object.fromEntries(tableRows.filter(row => String(row[0] || '').trim()).map(row => [
        String(row[0]), { 分值: row[1] === '' ? undefined : Number(row[1]), 客观项: row[2], 标准: row[3] },
      ]))
    } else if (tableBlock.field === '标的') {
      const packageNo = String((tableBlock.package_index ?? 0) + 1)
      const cols = tableBlock.columns || []
      // 第 0 列是序号，其余按 columns 顺序一一对应。按 key 取值，不按下标猜——
      // 原来那套下标是照一张有「采购品目」的表写的，实际表里没有，整体串了一格。
      const cellOf = (row: unknown[], key: string) => {
        const at = cols.findIndex(c => c.key === key)
        return at < 0 ? '' : row[at + 1]
      }
      const currentItems = tableRows.filter(row => row.slice(1).some(hasValue)).map((row, index) => {
        const item: Record<string, unknown> = { package_no: packageNo, no: String(index + 1) }
        cols.forEach(col => {
          const raw = cellOf(row, col.key)
          if (col.control === 'number' || col.control === 'computed') {
            const text = String(raw ?? '').replace(/,/g, '').trim()
            item[col.key] = text === '' ? '' : Number(text)
          } else {
            item[col.key] = String(raw ?? '')
          }
        })
        // 合计金额 = 单价 × 数量，自动算。能算的不给人填，也免得和单价对不上。
        const qty = Number(item.qty) || 0
        const price = Number(item.unit_price) || 0
        if (qty && price) item.amount = Number((qty * price).toFixed(2))
        return item
      })
      // 分包各有一张标的表；保存当前包时把其他包原值带回，不能误删别人的标的。
      // 「别的包」按**包号**认，不按块身份认：同一个包既有顶层「采购标的」块、
      // 又有包内「4.x.8标的具体情况」块，按块身份认会把同一批标的并进来两遍
      // （现象就是「改一条变成新增一条」）。
      const otherItems = (doc?.sections || []).flatMap(section => section.blocks)
        .filter(block => block.field === '标的'
          && String((block.package_index ?? 0) + 1) !== packageNo)
        .flatMap(block => (Array.isArray(block.value) ? block.value : []).map((item, index) => {
          const row = item as Record<string, unknown>
          const out: Record<string, unknown> = {
            package_no: String((block.package_index ?? 0) + 1), no: String(index + 1),
          }
          // 存量数据两套键都可能有：items_json 用英文键，packages_json 用中文键。
          ;(block.columns || cols).forEach(col => {
            out[col.key] = row[col.key] ?? row[col.cn] ?? ''
          })
          return out
        }))
      value = [...otherItems, ...currentItems].sort((a, b) => Number(a.package_no) - Number(b.package_no))
    } else if (tableBlock.field === '一般资格要求') {
      value = tableRows.map(row => ({ 名称: String(row[1] || ''), 详细说明: String(row[2] || '') }))
    } else if (tableBlock.field === '特殊资格要求') {
      value = tableRows.filter(row => String(row[1] || '').trim() || String(row[2] || '').trim())
        .map(row => `${String(row[1] || '').trim()}：${String(row[2] || '').trim()}`).join('\n')
    } else {
      value = tableRows.map(row => String(row[1] || '')).filter(Boolean).join('\n')
    }
    await saveValue(tableBlock, value)
    setTableBlock(null)
  }

  if (loading && !doc) return <div className="demand-workspace-loading"><Spin tip="正在铺开采购需求正文" /></div>
  if (!doc) return <Empty description="正文暂时无法显示" />

  const missingTip = firstStepMissing.length
    ? firstStepMissing.map(item => item.label || item.name).join('、') : '立项必填项已填齐'
  const tableReviewTotal = tableBlock?.field === '评审因素'
    ? tableRows.reduce((sum, row) => String(row[0] || '') === '价格扣除'
      ? sum : sum + (Number(row[1]) || 0), 0) : 0

  return <div className="demand-doc-workspace-shell">
    <Steps className="demand-workspace-steps" current={step} onChange={value => setStep(value as WorkspaceStep)}
      items={[
        {
          title: '立项', status: step === 0 ? 'process' : firstStepMissing.length ? 'error' : 'finish',
          description: <Tooltip title={missingTip}><span>
            {firstStepMissing.length ? `还差 ${firstStepMissing.length} 项` : '已填齐'}
          </span></Tooltip>,
        },
        {
          title: '填写',
          status: step === 1 ? 'process' : undefined,
          description: status ? (fillStepMissingCount ? `还差 ${fillStepMissingCount} 项；` : '已填齐；')
            + `全文已填 ${status.filled}/${status.total}`
            : '补齐其余正文',
        },
      ]} />

    <div className="demand-doc-workspace">
      <section className="demand-workspace-pane demand-agent-pane">
        <div className="demand-pane-title"><span><RobotOutlined /> Agent 交互</span></div>
        <div className="demand-agent-body">
          <DemandAgentChat demandId={demandId} onApplied={() => { void load(); onChanged?.() }} />
        </div>
      </section>

      <main className="demand-workspace-pane demand-document-pane">
        <article className="demand-document-paper">
          <h1 className="demand-document-title">政府采购需求</h1>
          <nav className="demand-doc-directory">
            <div className="demand-doc-directory-title">{step === 0 ? '立项目录' : '填写目录'}</div>
            {visibleSections.map(section => <a key={section.key} href={`#doc-section-${section.key}`}
              onClick={event => {
                event.preventDefault()
                document.getElementById(`doc-section-${section.key}`)
                  ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }}>{section.title} {section.blocks.some(block => block.required && !hasValue(block.value))
                && <span className="demand-section-incomplete">❗</span>}</a>)}
          </nav>
          {visibleSections.map(section => <section className="demand-doc-section"
            id={`doc-section-${section.key}`} key={section.key}>
            <h2>{section.title}</h2>
            {section.blocks.map((block, index) => {
              const id = blockId(block)
              const technicalRows = block.package_field === '技术要求'
                ? parseTechnicalRows(block.value) : null
              if (block.kind === 'table') return <div key={`${id}-${index}`}
                className={`demand-doc-block demand-doc-table-wrap ${block.class_name} ${block.editable ? 'is-editable' : ''} ${block.editable && hasValue(block.value) ? 'is-filled' : ''} ${active === id ? 'is-active' : ''}`}
                onClick={() => selectBlock(block)} title={block.lock_reason || undefined}>
                <div><span className="demand-doc-label">（{index + 1}）{block.label}：</span>
                  {!hasValue(block.value) && <span className="demand-doc-missing">{'{{未填写}}'}</span>}</div>
                {technicalRows && technicalRows.length > 0 ? <table className="demand-doc-table"><thead><tr>
                  {['序号', '参数性质', '技术要求名称', '技术参数与性能指标'].map(header => <th key={header}>{header}</th>)}
                </tr></thead><tbody>{technicalRows.map((row, rowIndex) => <tr key={rowIndex}>
                  <td>{rowIndex + 1}</td><td>{row.mark}</td><td>{row.name}</td><td>{row.content}</td>
                </tr>)}</tbody></table>
                  : hasValue(block.value) && !!block.rows?.length && <table className="demand-doc-table"><thead><tr>
                    {(block.header || []).map(header => <th key={header}>{header}</th>)}</tr></thead><tbody>
                    {block.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) =>
                      <td key={cellIndex}>{String(cell ?? '')}</td>)}</tr>)}
                  </tbody></table>}
              </div>
              return <div key={`${id}-${index}`}
                className={`demand-doc-block ${block.editable ? 'is-editable' : ''} ${block.editable && hasValue(block.value) ? 'is-filled' : ''} ${active === id ? 'is-active' : ''}`}
                onClick={() => selectBlock(block)} title={block.lock_reason || undefined}>
                <span className="demand-doc-label">（{index + 1}）{block.label}：</span>
                <span className={`demand-doc-value ${hasValue(block.value) ? '' : 'demand-doc-missing'} ${block.class_name}`}>
                  {displayValue(block.value)}
                </span>
              </div>
            })}
          </section>)}
        </article>
      </main>

      <aside className="demand-workspace-pane demand-editor-pane">
        <div className="demand-pane-title">
          <span>{step === 0 ? '立项' : '填写'}：{editItems.length} 个编辑项</span>
          <Space size={4}>
            {step === 0 && <>
              <Button size="small" icon={<PlusOutlined />} loading={saving === 'packages'}
                onClick={() => void changePackageCount(1)}>新增包</Button>
              {doc.packages.length > 1 && <Popconfirm title="删除最后一个采购包？"
                onConfirm={() => void changePackageCount(-1)}>
                <Button size="small" danger icon={<DeleteOutlined />}>删末包</Button>
              </Popconfirm>}
            </>}
            <Button size="small" icon={<DownloadOutlined />}
              href={demandDocUrl(demandId, true)}>下载 Word</Button>
          </Space>
        </div>
        <div className="demand-editor-list">
          {editItems.map((block, index) => {
            const id = blockId(block)
            const done = hasValue(block.value)
            const isManageDept = block.field === '归口管理科室'
            const manageDeptLocked = isManageDept && user?.role === 'dept_manage'
            const isMoney = block.field === '预算金额' || block.package_field === '最高限价'
            const selectOptions = block.field === '评审方法'
              ? reviewMethodsFor(procurementMethod)
              : (block.options?.length ? block.options
                : (block.field?.startsWith('是否') || block.field?.includes('有无'))
                  ? YES_NO_OPTIONS : [])
            return <div id={`editor-${id}`} key={id}
              className={`demand-editor-card ${active === id ? 'is-active' : ''}`}
              onClick={() => setActive(id)}>
              <div className="demand-editor-card-head">
                <span className="demand-editor-card-index">{index + 1}、</span>
                <span className="demand-editor-card-label">{block.label}</span>
                {done ? <CheckCircleFilled className="demand-editor-done" />
                  : <span className="demand-editor-undone">○</span>}
                {saving === id && <Tag color="processing">保存中</Tag>}
              </div>
              {block.package_field === '技术要求' ? <TechnicalEditor block={block}
                saving={saving === id} onSave={value => saveValue(block, value)} />
                : block.control === 'table' ? <Button block icon={<EditOutlined />}
                  onClick={() => openTable(block)}>编辑整张表{done ? '（已填）' : ''}</Button>
                  : block.field === '需求科室' ? <Select mode="multiple" showSearch
                    optionFilterProp="label" style={{ width: '100%' }}
                    value={parseDepartments(block.value)} placeholder="请选择需求科室"
                    options={departments.map(item => ({ value: item.name, label: item.name }))}
                    onChange={value => {
                      const stored = value.join('、')
                      patchBlock(block, stored); void saveValue(block, stored)
                    }} />
                    : isManageDept ? <Select showSearch optionFilterProp="label"
                      style={{ width: '100%' }} disabled={manageDeptLocked}
                      value={manageDeptLocked ? user?.dept_name : hasValue(block.value) ? String(block.value) : undefined}
                      placeholder="请选择归口管理科室"
                      options={departments.map(item => ({ value: item.name, label: item.name }))}
                      onChange={value => void saveValue(block, value)} />
                  : block.control === 'textarea' ? <TextArea value={String(block.value ?? '')}
                    maxLength={block.maxlen || undefined} autoSize={{ minRows: 4, maxRows: 10 }}
                    placeholder="请填写" onChange={event => patchBlock(block, event.target.value)}
                    onBlur={event => void saveValue(block, event.target.value)} />
                    : block.control === 'select' ? <Select style={{ width: '100%' }}
                      value={hasValue(block.value) ? String(block.value) : undefined}
                      placeholder="请选择" options={selectOptions.map(value => ({ value, label: value }))}
                      onChange={value => void saveValue(block, value)} />
                      : block.control === 'number' ? <InputNumber style={{ width: '100%' }}
                        value={Number(String(block.value || 0).replace(/,/g, '')) || undefined}
                        addonAfter={isMoney ? '元' : undefined}
                        formatter={isMoney ? moneyFormatter : undefined}
                        parser={isMoney ? moneyParser : undefined}
                        placeholder="请填写" onChange={value => patchBlock(block, value)}
                        onBlur={event => void saveValue(block, event.target.value)} />
                        : <Input value={String(block.value ?? '')} placeholder="请填写"
                          onChange={event => patchBlock(block, event.target.value)}
                          onBlur={event => void saveValue(block, event.target.value)} />}
              {block.hint && <div className="demand-editor-hint">{block.hint}</div>}
              {block.lock_reason && <div className="demand-editor-hint">{block.lock_reason}</div>}
            </div>
          })}
          {!editItems.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="本步没有待编辑项" />}
        </div>
      </aside>
    </div>

    <Modal title={`编辑：${tableBlock?.label || ''}`} open={!!tableBlock} width={920}
      onCancel={() => setTableBlock(null)} onOk={() => void saveTable()} okText="保存整张表"
      confirmLoading={!!tableBlock && saving === blockId(tableBlock)}>
      {tableBlock && <Space direction="vertical" style={{ width: '100%' }}>
        <Text type="secondary">整张表作为一个字段保存，可增删行。</Text>
        {tableBlock.field === '评审因素' && <div className="demand-review-total">
          <Text type="secondary">价格扣除用于计算评审价格，不计入总分。</Text>
          {tableReviewTotal === 100
            ? <Text type="success">当前合计 100 分</Text>
            : <Text type="danger">当前合计 {tableReviewTotal} 分，必须等于 100 分</Text>}
        </div>}
        <Table<{ row: unknown[]; index: number }> pagination={false}
          rowKey={record => String(record.index)}
          dataSource={tableRows.map((row, index) => ({ row, index }))}
          scroll={{ x: (tableBlock.columns?.length || 0) > 6 ? 1800 : undefined }}
          columns={[...(tableBlock.header || []).map((header, column) => ({
            title: header,
            width: tableBlock.columns?.[column - 1]?.control === 'text' ? 150 : 120,
            render: (_: unknown, record: { row: unknown[]; index: number }) => {
              const patchCell = (value: unknown) => setTableRows(rows => rows.map((row, rowIndex) =>
                rowIndex === record.index ? row.map((old, cellIndex) =>
                  cellIndex === column ? value : old) : row))
              // 第 0 列固定是序号，其余对应 columns[column-1]。
              // 有列规范就按 control 渲染；没有（评审因素等老表）走原来的表头匹配。
              const spec = tableBlock.columns?.[column - 1]
              // 成稿上下文会把金额格式化成 500,000.00，直接 Number() 得 NaN，
              // 输入框就变成空的。取数一律先去掉千分位。
              const toNum = (value: unknown) => {
                const text = String(value ?? '').replace(/,/g, '').trim()
                return text === '' ? undefined : Number(text)
              }
              if (spec?.control === 'computed') {
                // 合计金额 = 单价 × 数量，只读，随填随显示。
                const cols = tableBlock.columns || []
                const at = (key: string) => {
                  const i = cols.findIndex(c => c.key === key)
                  return i < 0 ? 0 : (toNum(record.row[i + 1]) || 0)
                }
                const total = at('qty') * at('unit_price')
                return <span style={{ color: total ? undefined : '#bbb' }}>
                  {total ? total.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '自动计算'}
                </span>
              }
              if (spec?.control === 'yesno') return <Select style={{ width: '100%' }} allowClear
                value={hasValue(record.row[column]) ? String(record.row[column]) : undefined}
                options={YES_NO_OPTIONS.map(value => ({ value, label: value }))}
                onChange={patchCell} />
              if (spec?.control === 'number' || header === '分值'
                  || header === '数量' || header === '标的金额（元）') {
                const money = spec?.key === 'unit_price' || header === '标的金额（元）'
                return <InputNumber style={{ width: '100%' }} min={0}
                  value={hasValue(record.row[column]) ? toNum(record.row[column]) : undefined}
                  addonAfter={money ? '元' : undefined}
                  formatter={money ? moneyFormatter : undefined}
                  parser={money ? moneyParser : undefined}
                  onChange={patchCell} />
              }
              if (header === '客观评审项') return <Select style={{ width: '100%' }}
                value={hasValue(record.row[column]) ? String(record.row[column]) : undefined}
                options={YES_NO_OPTIONS.map(value => ({ value, label: value }))}
                onChange={patchCell} />
              return <Input value={String(record.row[column] ?? '')}
                disabled={column === 0 && header === '序号'}
                onChange={event => patchCell(event.target.value)} />
            },
          })), {
            title: '操作', width: 72,
            render: (_: unknown, record: { index: number }) => <Button danger type="link"
              onClick={() => setTableRows(rows => rows.filter((_, index) => index !== record.index))}>删除</Button>,
          }]}/>
        <Button onClick={() => setTableRows(rows => [...rows,
          (tableBlock.header || []).map((_, index) => index === 0 ? rows.length + 1 : '')])}>
          新增一行
        </Button>
      </Space>}
    </Modal>
  </div>
}
