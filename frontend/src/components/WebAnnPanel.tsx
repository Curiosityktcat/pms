/**
 * 项目的官网公告存档面板。
 *
 * PMS 2026-06 上线前，院内竞选项目的公告只挂在医院官网，
 * 挂网时间、开标时间这些过程数据在 PMS 里是空的。这里把抓回来的官网公告
 * 按项目展示，补上那段历史。只读——数据源是官网。
 */
import { useState, useEffect } from 'react'
import { Drawer, Timeline, Tag, Typography, Empty, Spin, Descriptions, App } from 'antd'
import { GlobalOutlined } from '@ant-design/icons'
import { getWebAnnsByProject, type WebAnn } from '../services/webAnnouncement'

const { Text, Link } = Typography

const TYPE_COLOR: Record<string, string> = {
  院内竞选公告: 'blue',
  更正公告: 'orange',
  结果公示: 'green',
  中标公告: 'green',
  单一来源公示: 'purple',
  需求调研公告: 'cyan',
  废标公告: 'red',
}

export default function WebAnnPanel(
  { projectId, projectName, open, onClose }:
  { projectId: number | null; projectName?: string; open: boolean; onClose: () => void },
) {
  const { message } = App.useApp()
  const [rows, setRows] = useState<WebAnn[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !projectId) return
    setLoading(true)
    getWebAnnsByProject(projectId)
      .then(r => setRows(r.data.data || []))
      .catch(() => message.error('加载官网公告失败'))
      .finally(() => setLoading(false))
  }, [open, projectId, message])

  return (
    <Drawer
      open={open} onClose={onClose} width={720}
      title={<span><GlobalOutlined /> 官网公告存档{projectName ? ` —— ${projectName}` : ''}</span>}
    >
      <Text type="secondary" style={{ fontSize: 12 }}>
        来自医院官网「招标采购信息」栏目，PMS 上线前的公告只挂在那里。此处只读，以官网为准。
      </Text>
      <div style={{ height: 12 }} />
      {loading ? <Spin /> : rows.length === 0 ? (
        <Empty description="该项目在官网上没有找到公告" />
      ) : (
        <Timeline
          items={rows.map(a => ({
            color: TYPE_COLOR[a.ann_type] || 'gray',
            children: (
              <div>
                <div style={{ marginBottom: 4 }}>
                  <Tag color={TYPE_COLOR[a.ann_type] || 'default'}>{a.ann_type || '公告'}</Tag>
                  <Text strong>{a.publish_date}</Text>
                  {a.round_text && <Tag color="orange" style={{ marginLeft: 6 }}>{a.round_text}</Tag>}
                </div>
                <Link href={a.url} target="_blank">{a.title}</Link>
                <Descriptions size="small" column={2} style={{ marginTop: 8 }}
                  items={[
                    { key: 'b', label: '开标时间', children: a.bid_time || '—' },
                    { key: 'd', label: '获取文件', children:
                      a.doc_get_start ? `${a.doc_get_start} ~ ${a.doc_get_end}` : '—' },
                    { key: 'o', label: '经办人', children: a.officer || '—' },
                    { key: 'g', label: '代理机构', children: a.agency || '—' },
                    ...(a.budget_text ? [{ key: 'm', label: '预算/限价', children: a.budget_text }] : []),
                    ...(a.winner ? [{ key: 'w', label: '中标供应商', children: a.winner }] : []),
                    ...(a.bid_place ? [{ key: 'p', label: '开标地点', children: a.bid_place, span: 2 }] : []),
                  ]}
                />
              </div>
            ),
          }))}
        />
      )}
    </Drawer>
  )
}
