/**
 * 当前处理人标签：一眼看出这个项目此刻卡在谁手上、卡的是哪个审核环节、等了几天。
 *
 * 数据来自后端 services/pending_owner.py（与系统待办同一个派单引擎，
 * 所以「待办在谁名下」和这里显示的处理人永远一致）。
 * 各审核环节列表行、项目流程页、项目进展弹窗统一用这个组件，样式只维护一处。
 */
import { Tag, Tooltip, Typography } from 'antd'
import { ClockCircleOutlined, ExclamationCircleOutlined, CheckCircleOutlined } from '@ant-design/icons'
import type { Pending } from '../services/project'

const { Text } = Typography

/** 环节标题去掉「（5.1）」这类编号后缀，表格里省地方；tooltip 里给全称。 */
function shortLabel(label: string): string {
  return label.replace(/（[^）]*）\s*$/, '')
}

function waitText(days?: number | null): string {
  if (days == null) return ''
  return days <= 0 ? '今天' : `已等 ${days} 天`
}

/**
 * @param p        后端返回的 pending（null = 本环节无人待办：已办完/已归档）
 * @param compact  表格行内用：只显示「处理人 + 环节」，细节进 tooltip
 * @param doneText p 为空时显示的文字
 */
export default function PendingOwnerTag({
  p, compact = false, doneText = '无待处理',
}: { p?: Pending; compact?: boolean; doneText?: string }) {
  if (!p) {
    return (
      <Tag icon={<CheckCircleOutlined />} color="default" style={{ marginInlineEnd: 0 }}>
        {doneText}
      </Tag>
    )
  }
  const color = p.is_reject ? 'red' : p.role === 'agency' ? 'orange' : 'blue'
  const icon = p.is_reject ? <ExclamationCircleOutlined /> : <ClockCircleOutlined />
  const who = p.owner_name || '—'
  const wait = waitText(p.waiting_days)
  const tip = (
    <div style={{ lineHeight: 1.7 }}>
      <div>当前处理人：{who}（{p.role_label}）</div>
      <div>待办事项：{p.label}</div>
      {p.since ? <div>停留起始：{p.since.replace('T', ' ').slice(0, 16)}{wait ? `（${wait}）` : ''}</div> : null}
      {p.others?.length ? (
        <div>同时待处理：{p.others.map(o => `${o.label}→${o.owner_name}`).join('；')}</div>
      ) : null}
    </div>
  )

  if (compact) {
    return (
      <Tooltip title={tip}>
        <span style={{ whiteSpace: 'nowrap' }}>
          <Tag icon={icon} color={color} style={{ marginInlineEnd: 4 }}>{who}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>{shortLabel(p.label)}</Text>
          {p.others?.length ? <Text type="secondary" style={{ fontSize: 12 }}> +{p.others.length}</Text> : null}
        </span>
      </Tooltip>
    )
  }

  return (
    <Tooltip title={tip}>
      <Tag icon={icon} color={color} style={{ marginInlineEnd: 0 }}>
        待 {who}（{p.role_label}）{shortLabel(p.label)}
        {wait ? ` · ${wait}` : ''}
      </Tag>
    </Tooltip>
  )
}
