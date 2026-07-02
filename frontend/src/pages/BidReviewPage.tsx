import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Card, Table, Button, Space, Tag, Input, App, Typography, Popconfirm,
  Modal, Upload, Alert, Spin,
} from 'antd'
import {
  AuditOutlined, PlusOutlined, UploadOutlined, DeleteOutlined, FileTextOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import axios from 'axios'
import {
  listTasks, createTask, getTask, deleteTask, uploadProcDocUrl,
  listItems, updateItem,
  type ReviewTask, type ReviewResult, type ReviewItem,
} from '../services/bidReview'
import { TASK_STATUS_CN } from '../components/bidreview/shared'
import DocSummarySection from '../components/bidreview/DocSummarySection'
import CriteriaSection from '../components/bidreview/CriteriaSection'
import ResultsSection from '../components/bidreview/ResultsSection'
import ItemsSection, { type ItemPatch } from '../components/bidreview/ItemsSection'
import SummarySection from '../components/bidreview/SummarySection'

const { Title, Text } = Typography

export default function BidReviewPage() {
  const { message } = App.useApp()
  const [tasks, setTasks] = useState<ReviewTask[]>([])
  const [loading, setLoading] = useState(true)
  const [current, setCurrent] = useState<ReviewTask | null>(null)   // 选中任务（详情）
  const [items, setItems] = useState<ReviewItem[]>([])
  const [currentResult, setCurrentResult] = useState<ReviewResult | null>(null)
  const [newName, setNewName] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [summaryKey, setSummaryKey] = useState(0)   // 改分/改价/审完后驱动汇总重算
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listTasks()
      setTasks(res.data.data || [])
    } catch { message.error('加载任务失败') } finally { setLoading(false) }
  }, [message])
  useEffect(() => { load() }, [load])

  const refreshDetail = useCallback(async (tid: number) => {
    try {
      const res = await getTask(tid)
      setCurrent(res.data.data)
      return res.data.data
    } catch { return null }
  }, [])

  const openItems = useCallback(async (tid: number, r: ReviewResult) => {
    setCurrentResult(r)
    try {
      const res = await listItems(tid, r.id)
      setItems(res.data.data || [])
    } catch { message.error('加载审查结果失败') }
  }, [message])

  // 处理中状态轮询（采购文件 OCR/抽取 + 投标文件审查）
  useEffect(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    if (!current) return
    const busy = ['ocr_proc_doc', 'extracting'].includes(current.status)
      || (current.results || []).some(r => r.status === 'running' || r.ocr_status === 'running')
    if (!busy) return
    pollRef.current = setInterval(async () => {
      const t = await refreshDetail(current.id)
      if (t) {
        const stillBusy = ['ocr_proc_doc', 'extracting'].includes(t.status)
          || (t.results || []).some(r => r.status === 'running' || r.ocr_status === 'running')
        if (!stillBusy && pollRef.current) {
          clearInterval(pollRef.current); pollRef.current = null
          load()
          setSummaryKey(k => k + 1)
          // 若正查看某份结果，刷新明细
          if (currentResult) {
            const done = (t.results || []).find(r => r.id === currentResult.id)
            if (done?.status === 'done') openItems(t.id, done)
          }
        }
      }
    }, 4000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id, current?.status, JSON.stringify((current?.results || []).map(r => [r.status, r.ocr_status]))])

  const handleCreate = async () => {
    if (!newName.trim()) { message.warning('请填写项目名称'); return }
    try {
      const res = await createTask(newName.trim())
      message.success('任务已创建，请上传采购文件')
      setCreateOpen(false); setNewName('')
      load()
      setCurrent({ ...res.data.data, criteria: [], results: [] })
    } catch { message.error('创建失败') }
  }

  // 上传（采购文件 / 投标文件通用）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const makeUpload = (url: string, extra?: Record<string, string>) => async (options: any) => {
    const { file, onSuccess, onError } = options
    setUploading(true)
    const fd = new FormData()
    fd.append('file', file as Blob)
    Object.entries(extra || {}).forEach(([k, v]) => { if (v) fd.append(k, v) })
    try {
      const res = await axios.post(url, fd, {
        withCredentials: true, headers: { 'Content-Type': 'multipart/form-data' },
      })
      onSuccess?.(res.data)
      message.success(res.data.message || '上传成功')
      if (current) refreshDetail(current.id)
      load()
    } catch (err: unknown) {
      onError?.(err as Error)
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '上传失败')
    } finally { setUploading(false) }
  }

  const handleItemUpdate = async (it: ReviewItem, data: ItemPatch) => {
    if (!current || !currentResult) return
    try {
      await updateItem(current.id, currentResult.id, it.id, data)
      setItems(prev => prev.map(x => x.id === it.id
        ? { ...x, ...data, reviewed_by: '已复核' } as ReviewItem : x))
      setSummaryKey(k => k + 1)
    } catch (err: unknown) {
      const m = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      message.error(m || '保存失败')
    }
  }

  const onResultsChanged = () => {
    if (current) refreshDetail(current.id)
    setSummaryKey(k => k + 1)
  }

  // ── 任务列表列 ──
  const taskColumns = [
    { title: '项目名称', dataIndex: 'task_name', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 150,
      render: (s: string) => {
        const m = TASK_STATUS_CN[s] || { label: s, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    { title: '评审方式', dataIndex: 'eval_method', width: 110, render: (v: string) => v || '—' },
    { title: '审查条目', dataIndex: 'criteria_count', width: 90, render: (n: number) => n ? `${n} 条` : '—' },
    { title: '投标文件', dataIndex: 'result_count', width: 90, render: (n: number) => n ? `${n} 份` : '—' },
    { title: '创建', dataIndex: 'created_at', width: 160, render: (v: string) => v?.replace('T', ' ') || '—' },
    {
      title: '操作', width: 160,
      render: (_: unknown, t: ReviewTask) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={async () => {
            setCurrentResult(null); setItems([])
            await refreshDetail(t.id)
            setSummaryKey(k => k + 1)
          }}>打开</Button>
          <Popconfirm title="删除该任务及全部审查数据？" okText="删除" cancelText="取消"
            onConfirm={async () => {
              await deleteTask(t.id)
              if (current?.id === t.id) { setCurrent(null); setCurrentResult(null) }
              load()
            }}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const busy = current && (['ocr_proc_doc', 'extracting'].includes(current.status))
  const hasCriteria = !!(current?.criteria || []).length

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <AuditOutlined /> 投标文件审查（AI 辅助）
          </Title>
          <Text type="secondary">
            上传采购文件自动抽取 分包/标的/资格/实质性/商务/打分 条目 → 经办人确认 →
            上传投标文件 → AI 按 资格→符合性→打分 审查并抽报价 → 人工复核 → 汇总比价导出。
          </Text>
        </div>
        <Alert type="warning" showIcon
          message="AI 辅助审查结果仅供参考，须经办人逐条复核确认后方可用于正式评审。" />

        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建审查任务
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => {
            load()
            if (current) { refreshDetail(current.id); setSummaryKey(k => k + 1) }
          }}>
            刷新
          </Button>
        </Space>

        <Table rowKey="id" size="small" loading={loading}
          columns={taskColumns} dataSource={tasks}
          pagination={{ pageSize: 5, showSizeChanger: false }}
          rowClassName={t => (t.id === current?.id ? 'ant-table-row-selected' : '')}
        />

        {current && (
          <Card type="inner" title={
            <Space>
              <FileTextOutlined /> {current.task_name}
              {(() => { const m = TASK_STATUS_CN[current.status] || { label: current.status, color: 'default' }
                return <Tag color={m.color}>{m.label}</Tag> })()}
            </Space>
          }>
            {current.status === 'failed' && (
              <Alert type="error" showIcon style={{ marginBottom: 12 }}
                message={`处理失败：${current.error_msg || '未知错误'}`}
                action={<Text type="secondary">可重新上传采购文件重试</Text>} />
            )}
            {current.status === 'criteria_ready' && current.error_msg && (
              <Alert type="warning" showIcon style={{ marginBottom: 12 }}
                message={`部分抽取未完成：${current.error_msg}`} />
            )}

            {/* 采购文件上传 */}
            <Space style={{ marginBottom: 8 }} wrap>
              <Upload customRequest={makeUpload(uploadProcDocUrl(current.id))}
                showUploadList={false} accept=".pdf,.docx,.png,.jpg,.jpeg" disabled={uploading || !!busy}>
                <Button icon={<UploadOutlined />} loading={uploading || !!busy}>
                  {current.proc_doc_name ? `重新上传采购文件（当前：${current.proc_doc_name}）` : '上传采购文件（Word/PDF）'}
                </Button>
              </Upload>
              {busy && <Spin size="small" />}
              {busy && <Text type="secondary">
                {current.status === 'ocr_proc_doc'
                  ? '识别文件中（Word/文本PDF 秒级；扫描件 OCR 每页约6秒）…'
                  : `AI 抽取条目中${current.progress ? `（${current.progress}）` : ''}…`}
              </Text>}
            </Space>

            {(current.proc_doc_name || hasCriteria) && (
              <>
                <DocSummarySection task={current} onSaved={() => refreshDetail(current.id)} />
                <CriteriaSection task={current} canAdd={!busy}
                  onSaved={() => refreshDetail(current.id)} />
              </>
            )}

            <ResultsSection task={current} canUpload={hasCriteria && !busy}
              viewingId={currentResult?.id ?? null}
              onOpenItems={r => openItems(current.id, r)}
              onChanged={onResultsChanged} />

            {currentResult && (
              <ItemsSection task={current} result={currentResult}
                items={items} onUpdate={handleItemUpdate} />
            )}

            <SummarySection task={current} reloadKey={summaryKey} />
          </Card>
        )}
      </Space>

      {/* 新建任务 */}
      <Modal title="新建审查任务" open={createOpen} onOk={handleCreate}
        onCancel={() => setCreateOpen(false)} okText="创建" destroyOnHidden>
        <Input placeholder="项目名称（可以是 pms 外的项目）" value={newName}
          onChange={e => setNewName(e.target.value)} maxLength={200}
          onPressEnter={handleCreate} style={{ marginTop: 8 }} />
      </Modal>
    </Card>
  )
}
