import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Button, Space, Tabs, Popconfirm, App, Typography, Modal,
} from 'antd'
import { InboxOutlined, RollbackOutlined, PrinterOutlined, RobotOutlined } from '@ant-design/icons'
import {
  listArchive, archiveProject, revokeArchive, printBundleUrl, type ArchiveItem,
} from '../services/archive'
import FilePreviewModal from '../components/FilePreviewModal'
import RecordCards from '../components/RecordCards'
import HermesPanel, { type HermesField } from '../components/HermesPanel'
import ProjectListToolbar, { useProjectListFilter, type ListFilterAccessors } from '../components/ProjectListToolbar'

const ARCHIVE_ACCESSORS: ListFilterAccessors<ArchiveItem> = {
  searchText: it => [it.name, it.number, it.officer],
  createdAt: it => it.created_at,
  number: it => it.number,
  method: it => it.method,
}

const { Title, Text } = Typography

export default function ArchivePage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<ArchiveItem[]>([])
  const [tab, setTab] = useState<'todo' | 'done'>('todo')
  const [acting, setActing] = useState(0)
  const [printItem, setPrintItem] = useState<ArchiveItem | null>(null)
  const [approvalItem, setApprovalItem] = useState<ArchiveItem | null>(null)
  const approvalFields = useMemo<HermesField[]>(() => approvalItem ? [
    { label: '归口管理科室', value: approvalItem.manage_dept || '' },
    { label: '项目名称', value: '采购文件确认函，授权函，采购结果确认函', long: true },
    { label: '项目资料名称', value: '备案资料' },
    { label: '经办人', value: '曾旌城' },
  ] : [], [approvalItem])

  const load = useCallback(() => {
    setLoading(true)
    listArchive()
      .then(res => setItems(res.data.data || []))
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }, [message])
  useEffect(() => { load() }, [load])

  const tabItems = useMemo(
    () => items.filter(it => (tab === 'done' ? it.archived : !it.archived)),
    [items, tab])
  const listFilter = useProjectListFilter(tabItems, ARCHIVE_ACCESSORS)
  const filtered = listFilter.filtered

  const doArchive = async (id: number) => {
    setActing(id)
    try {
      await archiveProject(id)
      message.success('已归档')
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '归档失败')
    } finally {
      setActing(0)
    }
  }

  const doRevoke = async (id: number) => {
    setActing(id)
    try {
      await revokeArchive(id)
      message.success('已撤销归档')
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err?.response?.data?.error || '撤销失败')
    } finally {
      setActing(0)
    }
  }

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <InboxOutlined /> 项目归档
          </Title>
          <Text type="secondary">
            汇总项目要件（授权函 / 采购结果 / 合同），由采购部助理确认归档。
          </Text>
        </div>

        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Tabs
            activeKey={tab}
            onChange={k => setTab(k as 'todo' | 'done')}
            items={[{ key: 'todo', label: '待归档' }, { key: 'done', label: '已归档' }]}
          />
          <ProjectListToolbar f={listFilter} placeholder="搜索名称 / 编号 / 经办人" />
        </Space>

        <RecordCards
          dataSource={filtered}
          loading={loading}
          emptyText={tab === 'done' ? '暂无已归档项目' : '暂无待归档项目'}
          toCard={(r) => ({
            key: r.id,
            accent: r.archived ? '#34a853' : '#1a73e8',
            title: r.name || `项目#${r.id}`,
            subtitle: r.number || '无编号',
            statusText: r.status,
            statusColor: r.archived ? 'green' : 'blue',
            fields: [
              { label: '经办人', value: r.officer },
              { label: '授权函', value: `${r.auth_letter_count} 份` },
              { label: '采购结果', value: `${r.result_count} 项` },
              { label: '合同', value: `${r.contract_count} 份` },
            ],
            actions: (
              <>
                <Button size="small" icon={<PrinterOutlined />} onClick={() => setPrintItem(r)}>
                  一键打印资料
                </Button>
                <Button size="small" icon={<RobotOutlined />} onClick={() => setApprovalItem(r)}>
                  项目审批填报
                </Button>
                {r.archived ? (
                  <Popconfirm title="撤销归档？状态将回退为「合同签订」" onConfirm={() => doRevoke(r.id)}>
                    <Button size="small" danger icon={<RollbackOutlined />} loading={acting === r.id}>
                      撤销归档
                    </Button>
                  </Popconfirm>
                ) : (
                  <Popconfirm title="确认归档该项目？" onConfirm={() => doArchive(r.id)}>
                    <Button size="small" type="primary" ghost icon={<InboxOutlined />} loading={acting === r.id}>
                      归档
                    </Button>
                  </Popconfirm>
                )}
              </>
            ),
          })}
        />
      </Space>

      {printItem && (
        <FilePreviewModal
          open={!!printItem}
          url={printBundleUrl(printItem.id)}
          filename={`${printItem.number || printItem.name}-归档资料.docx`}
          showPrint
          onClose={() => setPrintItem(null)}
        />
      )}

      <Modal
        title={`采购项目审批填报 — ${approvalItem?.name || ''}`}
        open={!!approvalItem}
        onCancel={() => setApprovalItem(null)}
        footer={null}
        width={620}
        destroyOnHidden
      >
        <HermesPanel taskType="procurement-approval" projectId={approvalItem?.id}
          title={approvalItem?.name} fields={approvalFields}
          directSubmitUrl={approvalItem ? `/archive/${approvalItem.id}/submit-to-rdweb` : undefined}
          directStatusUrl={approvalItem ? `/archive/${approvalItem.id}/rdweb-status` : undefined} />
      </Modal>
    </Card>
  )
}
