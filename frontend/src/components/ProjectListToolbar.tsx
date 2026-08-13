/**
 * 流程模块统一的列表工具栏 + 过滤排序 hook。
 *
 * 规则（经办人要求，2026-07）：
 * - 按新增时间、按项目编号两种排序键都默认倒序（新的/编号大的在前），可按钮切正/倒序；
 * - 统一搜索框（名称/编号/代理机构，合同模块可扩展供应商）；
 * - 筛选：年度（取编号/创建时间中的年份）、采购方式。
 */
import { useMemo, useState } from 'react'
import { Input, Select, Segmented, Space, Button } from 'antd'
import { SearchOutlined, SortAscendingOutlined, SortDescendingOutlined } from '@ant-design/icons'

export interface ListFilterAccessors<T> {
  /** 参与关键词搜索的字段值 */
  searchText: (row: T) => (string | undefined | null)[]
  createdAt: (row: T) => string | undefined
  number: (row: T) => string | undefined
  /** 采购方式；不提供则隐藏该筛选 */
  method?: (row: T) => string | undefined
}

export type SortKey = 'created' | 'number'

/** 从项目编号（如 2026063011736）或创建时间提取年度 */
function rowYear<T>(row: T, acc: ListFilterAccessors<T>): string {
  const num = acc.number(row) || ''
  const m = num.match(/^(20\d{2})/)
  if (m) return m[1]
  const c = acc.createdAt(row) || ''
  return c.slice(0, 4)
}

export function useProjectListFilter<T>(rows: T[], acc: ListFilterAccessors<T>) {
  const [kw, setKw] = useState('')
  const [year, setYear] = useState<string>('')
  const [method, setMethod] = useState<string>('')
  const [sortBy, setSortBy] = useState<SortKey>('created')
  const [asc, setAsc] = useState(false)   // 默认倒序

  const years = useMemo(() => {
    const s = new Set<string>()
    rows.forEach(r => { const y = rowYear(r, acc); if (y) s.add(y) })
    return [...s].sort().reverse()
  }, [rows, acc])

  const methods = useMemo(() => {
    if (!acc.method) return []
    const s = new Set<string>()
    rows.forEach(r => { const m = acc.method!(r); if (m) s.add(m) })
    return [...s].sort()
  }, [rows, acc])

  const filtered = useMemo(() => {
    const k = kw.trim()
    let out = rows.filter(r => {
      if (k && !acc.searchText(r).some(t => (t || '').includes(k))) return false
      if (year && rowYear(r, acc) !== year) return false
      if (method && acc.method && (acc.method(r) || '') !== method) return false
      return true
    })
    out = [...out].sort((a, b) => {
      const r = sortBy === 'number'
        ? (acc.number(a) || '').localeCompare(acc.number(b) || '')
        : (acc.createdAt(a) || '').localeCompare(acc.createdAt(b) || '')
      return asc ? r : -r
    })
    return out
  }, [rows, kw, year, method, sortBy, asc, acc])

  return { filtered, kw, setKw, year, setYear, method, setMethod, sortBy, setSortBy, asc, setAsc, years, methods }
}

export default function ProjectListToolbar<T>({
  f, placeholder = '搜索项目名称 / 编号 / 代理机构', showMethod = true,
}: {
  f: ReturnType<typeof useProjectListFilter<T>>
  placeholder?: string
  showMethod?: boolean
}) {
  return (
    <Space wrap>
      <Input
        allowClear
        prefix={<SearchOutlined style={{ color: '#bbb' }} />}
        placeholder={placeholder}
        style={{ width: 300 }}
        value={f.kw}
        onChange={e => f.setKw(e.target.value)}
      />
      <Select
        allowClear
        placeholder="年度"
        style={{ width: 110 }}
        value={f.year || undefined}
        onChange={v => f.setYear(v || '')}
        options={f.years.map(y => ({ value: y, label: `${y}年` }))}
      />
      {showMethod && f.methods.length > 0 && (
        <Select
          allowClear
          placeholder="采购方式"
          style={{ width: 160 }}
          value={f.method || undefined}
          onChange={v => f.setMethod(v || '')}
          options={f.methods.map(m => ({ value: m, label: m }))}
        />
      )}
      <Segmented
        value={f.sortBy}
        onChange={v => f.setSortBy(v as SortKey)}
        options={[
          { value: 'created', label: '按新增时间' },
          { value: 'number', label: '按项目编号' },
        ]}
      />
      <Button
        icon={f.asc ? <SortAscendingOutlined /> : <SortDescendingOutlined />}
        onClick={() => f.setAsc(!f.asc)}
      >
        {f.asc ? '正序' : '倒序'}
      </Button>
    </Space>
  )
}

// 标准项目列表访问器（大多数流程模块直接用它）
import type { Project } from '../services/project'
export const PROJECT_ACCESSORS: ListFilterAccessors<Project> = {
  searchText: p => [p.name, p.number, p.agency_name],
  createdAt: p => p.created_at,
  number: p => p.number,
  method: p => p.method,
}
