import { useState } from 'react'
import { List, Tag, Grid, Segmented, Tooltip } from 'antd'
import { AppstoreOutlined, BarsOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'

/** 卡片列表通用组件：紧凑卡片（标题行 + 信息行），边界清晰、一屏可容纳多条。
 *  右上角可切换「单列（舒展）/ 双列（一行两张）」，记忆在 localStorage。移动端恒为单列。 */

export interface RecordField {
  label: string
  value: ReactNode
}

export interface RecordCardData {
  key: string | number
  accent?: string // 左侧状态色条颜色，默认蓝
  title: ReactNode
  onTitleClick?: () => void
  subtitle?: ReactNode // 信息行起始的副信息（编号等）
  statusText?: string
  statusColor?: string // antd Tag color
  tags?: ReactNode // 标题右侧小标签 chips
  fields?: RecordField[] // 信息行内联 label: value
  meta?: ReactNode // 信息行尾部次要信息
  actions?: ReactNode // 右侧（移动端底部）操作区
}

const LS_KEY = 'pms_card_cols'

export function RecordCard({ data, isMobile, roomy }: { data: RecordCardData; isMobile: boolean; roomy: boolean }) {
  const accent = data.accent || '#1a73e8'
  const fields = (data.fields || []).filter((f) => f.value !== '' && f.value != null)

  return (
    <div
      className="record-card"
      style={{
        display: 'flex',
        flexDirection: isMobile ? 'column' : 'row',
        height: '100%',
        background: '#fff',
        border: '1px solid #d4d7dc',
        borderLeft: `4px solid ${accent}`,
        borderRadius: 8,
        boxShadow: '0 1px 1px rgba(60,64,67,.06)',
      }}
    >
      <div style={{ flex: 1, minWidth: 0, padding: roomy ? '13px 18px' : '8px 14px' }}>
        {/* 标题行 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            onClick={data.onTitleClick}
            style={{
              fontSize: roomy ? 15 : 14,
              fontWeight: 600,
              color: '#202124',
              cursor: data.onTitleClick ? 'pointer' : 'default',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              minWidth: 0,
            }}
          >
            {data.onTitleClick ? <a style={{ color: '#202124' }}>{data.title}</a> : data.title}
          </span>
          {data.tags && <span style={{ display: 'inline-flex', gap: 4, flexShrink: 0 }}>{data.tags}</span>}
          <span style={{ flex: 1 }} />
          {data.statusText && (
            <Tag
              color={data.statusColor}
              style={{ marginInlineEnd: 0, borderRadius: 10, fontSize: 11.5, lineHeight: '18px', padding: '0 9px', fontWeight: 600 }}
            >
              {data.statusText}
            </Tag>
          )}
        </div>

        {/* 信息行（内联字段） */}
        {(data.subtitle || fields.length > 0 || data.meta) && (
          <div
            style={{
              marginTop: roomy ? 7 : 3,
              fontSize: 12,
              color: '#5f6368',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: roomy ? '6px 14px' : '2px 12px',
            }}
          >
            {data.subtitle != null && data.subtitle !== '' && <span style={{ color: '#80868b' }}>{data.subtitle}</span>}
            {fields.map((f, i) => (
              <span key={i}>
                <span style={{ color: '#9aa0a6' }}>{f.label} </span>
                <span style={{ color: '#3c4043', fontWeight: 500 }}>{f.value}</span>
              </span>
            ))}
            {data.meta && <span style={{ color: '#9aa0a6' }}>{data.meta}</span>}
          </div>
        )}
      </div>

      {/* 操作区 */}
      {data.actions && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 6,
            flexWrap: 'wrap',
            flexShrink: 0,
            padding: isMobile ? '6px 12px 8px' : '0 12px',
            borderLeft: isMobile ? 'none' : '1px solid #f0f1f3',
            borderTop: isMobile ? '1px solid #f0f1f3' : 'none',
          }}
        >
          {data.actions}
        </div>
      )}
    </div>
  )
}

interface RecordCardsProps<T> {
  dataSource: T[]
  toCard: (item: T) => RecordCardData
  loading?: boolean
  emptyText?: string
  pageSize?: number
}

export default function RecordCards<T>({ dataSource, toCard, loading, emptyText, pageSize }: RecordCardsProps<T>) {
  const screens = Grid.useBreakpoint()
  const isMobile = !screens.md
  const [cols, setCols] = useState<number>(() => Number(localStorage.getItem(LS_KEY)) || 1)
  const changeCols = (v: number) => {
    setCols(v)
    localStorage.setItem(LS_KEY, String(v))
  }

  const effCols = isMobile ? 1 : cols
  const roomy = effCols === 1
  const ps = pageSize || (isMobile ? 12 : effCols === 2 ? 24 : 16)

  return (
    <div>
      {!isMobile && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
          <Segmented
            size="small"
            value={cols}
            onChange={(v) => changeCols(v as number)}
            options={[
              { value: 1, label: <Tooltip title="单列（舒展）"><BarsOutlined /></Tooltip> },
              { value: 2, label: <Tooltip title="双列（一行两张）"><AppstoreOutlined /></Tooltip> },
            ]}
          />
        </div>
      )}
      <List
        loading={loading}
        dataSource={dataSource}
        locale={{ emptyText: emptyText || '暂无数据' }}
        grid={{ gutter: roomy ? [0, 10] : [12, 12], column: effCols }}
        pagination={
          dataSource.length > ps
            ? { pageSize: ps, showTotal: (t) => `共 ${t} 条`, align: 'center' }
            : false
        }
        renderItem={(item) => {
          const data = toCard(item)
          return (
            <List.Item key={data.key} style={{ marginBlockEnd: 0 }}>
              <RecordCard data={data} isMobile={isMobile} roomy={roomy} />
            </List.Item>
          )
        }}
      />
    </div>
  )
}

/** 供页面判断是否窄屏（与卡片内部一致的断点）。 */
export function useIsMobile() {
  const screens = Grid.useBreakpoint()
  return !screens.md
}
