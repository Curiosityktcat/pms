import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Card, Button, Space, Tabs, Popconfirm, App, Typography, Modal, Empty, Spin,
} from 'antd'
import {
  InboxOutlined, RollbackOutlined, PrinterOutlined, RobotOutlined,
  FolderOpenOutlined, FolderOutlined, FileWordOutlined, EyeOutlined, DownloadOutlined,
} from '@ant-design/icons'
import {
  listArchive, archiveProject, revokeArchive, printBundleUrl,
  archiveTree,
  type ArchiveItem, type ArchiveTreeFolder,
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
  // 文件夹视图：打开某项目 → 按轮次浏览/下载各归档要件
  const [folderItem, setFolderItem] = useState<ArchiveItem | null>(null)
  const [tree, setTree] = useState<ArchiveTreeFolder[]>([])
  const [treeLoading, setTreeLoading] = useState(false)
  const [itemPreview, setItemPreview] = useState<{ url: string; name: string } | null>(null)

  const openFolder = useCallback((r: ArchiveItem) => {
    setFolderItem(r)
    setTree([])
    setTreeLoading(true)
    archiveTree(r.id)
      .then(res => setTree(res.data.data || []))
      .catch(() => message.error('加载归档资料失败'))
      .finally(() => setTreeLoading(false))
  }, [message])
  const approvalFields = useMemo<HermesField[]>(() => approvalItem ? [
    { label: '归口管理科室', value: approvalItem.manage_dept || '' },
    { label: '项目名称', value: '采购文件确认函，授权函，采购结果确认函', long: true },
    { label: '项目资料名称', value: '备案资料' },
    // 经办人必须是 rd-web 人员库里搜得到的人，取本项目经办人；
    // 原来写死「曾旌城」，人员选择框搜不到，提交必然失败
    { label: '经办人', value: approvalItem.officer || '' },
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
                <Button size="small" type="primary" ghost icon={<FolderOpenOutlined />} onClick={() => openFolder(r)}>
                  打开文件夹
                </Button>
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

      <Modal
        title={<><FolderOpenOutlined style={{ color: '#faad14', marginRight: 6 }} />{folderItem?.name || ''}　归档资料</>}
        open={!!folderItem}
        onCancel={() => setFolderItem(null)}
        footer={null}
        width={640}
        destroyOnHidden
      >
        {treeLoading ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}><Spin /></div>
        ) : tree.length === 0 ? (
          <Empty description="该项目暂无归档资料" />
        ) : (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {tree.map(fd => (
              <div key={fd.folder}>
                <Text strong><FolderOutlined style={{ color: '#faad14', marginRight: 6 }} />{fd.folder}</Text>
                <div style={{ marginTop: 8 }}>
                  {fd.items.map((it, idx) => (
                    <div key={idx} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '8px 12px', marginBottom: 6, borderRadius: 6,
                      background: '#f8f9fa', border: '1px solid #eef0f2',
                    }}>
                      <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <FileWordOutlined style={{ color: '#2b5797', marginRight: 8 }} />{it.name}
                      </span>
                      <Space size={4} style={{ flexShrink: 0 }}>
                        {it.preview_url && (
                          <Button size="small" icon={<EyeOutlined />}
                            onClick={() => setItemPreview({ url: it.preview_url, name: it.name })}>预览</Button>
                        )}
                        <Button size="small" type="primary" ghost icon={<DownloadOutlined />}
                          href={it.url} target="_blank">下载</Button>
                      </Space>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </Space>
        )}
      </Modal>

      {itemPreview && (
        <FilePreviewModal
          open={!!itemPreview}
          url={itemPreview.url}
          filename={itemPreview.name}
          showPrint
          onClose={() => setItemPreview(null)}
        />
      )}
    </Card>
  )
}
