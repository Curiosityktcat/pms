import { useState } from 'react'
import {
  App, Button, Input, List, Modal, Popconfirm, Progress, Select, Space, Table,
  Tag, Tooltip, Typography, Upload,
} from 'antd'
import {
  DeleteOutlined, DownloadOutlined, PlayCircleOutlined, UploadOutlined,
  FileAddOutlined, PaperClipOutlined,
} from '@ant-design/icons'

// 待上传文件项（自管原始 File，避免依赖 antd 的 originFileObj）
interface PickedFile { uid: string; name: string; file: File }

// 受控 Upload：beforeUpload 收集原始 File，返回 false 阻止自动上传
function pickerProps(
  items: PickedFile[],
  setItems: (fn: (prev: PickedFile[]) => PickedFile[]) => void,
) {
  return {
    multiple: true,
    accept: '.pdf,.docx,.png,.jpg,.jpeg',
    fileList: items.map(it => ({ uid: it.uid, name: it.name })),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    beforeUpload: (file: any) => {
      setItems(prev => [...prev, { uid: file.uid, name: file.name, file }])
      return false as const
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onRemove: (file: any) => {
      setItems(prev => prev.filter(it => it.uid !== file.uid))
    },
  }
}
import {
  addResultFiles, createSupplier, deleteResult, deleteResultFile, exportCsvUrl,
  startReview, updateResult, LOT_COMMON,
  type ReviewResult, type ReviewTask, type UploadStat,
} from '../../services/bidReview'
import { getErr, lotTag, RESULT_STATUS_CN } from './shared'

const { Text, Title } = Typography

const EMPTY_STAT: UploadStat = { percent: 0, rate: 0, estimated: 0 }

function fmtSpeed(bps: number) {
  if (bps >= 1024 * 1024) return `${(bps / 1024 / 1024).toFixed(1)} MB/s`
  if (bps >= 1024) return `${(bps / 1024).toFixed(0)} KB/s`
  return `${Math.round(bps)} B/s`
}

function fmtEta(sec: number) {
  if (!sec || !isFinite(sec)) return ''
  if (sec >= 60) return `约剩 ${Math.floor(sec / 60)} 分 ${Math.round(sec % 60)} 秒`
  return `约剩 ${Math.round(sec)} 秒`
}

/** ③ 投标方（每方可挂多个文件）：建方+批量上传、报价、启动审查、查看/导出。 */
export default function ResultsSection({ task, canUpload, onOpenItems, onChanged, viewingId }: {
  task: ReviewTask
  canUpload: boolean
  onOpenItems: (r: ReviewResult) => void
  onChanged: () => void
  viewingId: number | null
}) {
  const { message } = App.useApp()
  const [upOpen, setUpOpen] = useState(false)
  const [upLabel, setUpLabel] = useState('')
  const [upLot, setUpLot] = useState(LOT_COMMON)
  const [upFiles, setUpFiles] = useState<PickedFile[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [stat, setStat] = useState<UploadStat>(EMPTY_STAT)   // 上传进度/速率
  // 给已有投标方追加文件
  const [addToRow, setAddToRow] = useState<ReviewResult | null>(null)
  const [addFiles, setAddFiles] = useState<PickedFile[]>([])

  const hasLots = task.lots.length > 0

  const doStart = async (r: ReviewResult) => {
    try {
      await startReview(task.id, r.id)
      message.success('已开始审查')
      onChanged()
    } catch (err) { message.error(getErr(err, '启动失败')) }
  }

  const savePrice = async (r: ReviewResult, price: string) => {
    try {
      await updateResult(task.id, r.id, { bid_price: price.trim() })
      message.success('报价已保存')
      onChanged()
    } catch (err) { message.error(getErr(err, '保存失败')) }
  }

  const submitNew = async () => {
    const files = upFiles.map(f => f.file)
    if (!files.length) { message.warning('请至少选择一个文件'); return }
    setSubmitting(true); setStat(EMPTY_STAT)
    try {
      const res = await createSupplier(task.id, upLabel.trim(), upLot, files, setStat)
      message.success(res.data.message || '已创建投标方')
      setUpOpen(false); setUpLabel(''); setUpFiles([])
      onChanged()
    } catch (err) { message.error(getErr(err, '上传失败')) }
    finally { setSubmitting(false); setStat(EMPTY_STAT) }
  }

  const submitAddFiles = async () => {
    if (!addToRow) return
    const files = addFiles.map(f => f.file)
    if (!files.length) { message.warning('请至少选择一个文件'); return }
    setSubmitting(true); setStat(EMPTY_STAT)
    try {
      const res = await addResultFiles(task.id, addToRow.id, files, setStat)
      message.success(res.data.message || '已追加文件')
      setAddToRow(null); setAddFiles([])
      onChanged()
    } catch (err) { message.error(getErr(err, '追加失败')) }
    finally { setSubmitting(false); setStat(EMPTY_STAT) }
  }

  const removeFile = async (r: ReviewResult, fid: number) => {
    try {
      await deleteResultFile(task.id, r.id, fid)
      message.success('已删除该文件')
      onChanged()
    } catch (err) { message.error(getErr(err, '删除失败')) }
  }

  const openNew = () => {
    setUpLabel(''); setUpFiles([])
    setUpLot(hasLots ? task.lots[0].lot_no : LOT_COMMON)
    setUpOpen(true)
  }

  const columns = [
    {
      title: '投标方', dataIndex: 'bid_file_name', ellipsis: true,
      render: (v: string, r: ReviewResult) => (
        <Space size={4}>
          <Text>{v}</Text>
          <Tag icon={<PaperClipOutlined />} color="default">{r.file_count ?? 0} 个文件</Tag>
        </Space>
      ),
    },
    ...(hasLots ? [{
      title: '所投包', dataIndex: 'lot_no', width: 85,
      render: (v: string) => lotTag(v),
    }] : []),
    {
      title: '总报价(元)', width: 190,
      render: (_: unknown, r: ReviewResult) => (
        <Input size="small" key={`${r.id}:${r.bid_price}`}
          defaultValue={r.bid_price} placeholder="审查后 AI 抽取"
          suffix={r.price_edited_by
            ? <Tooltip title={`人工修改：${r.price_edited_by}`}><Tag color="blue" style={{ margin: 0 }}>人工</Tag></Tooltip>
            : (r.bid_price
              ? <Tooltip title={`AI 抽取${r.price_page ? `（${r.price_page}）` : ''}，请核对`}><Tag color="cyan" style={{ margin: 0 }}>AI</Tag></Tooltip>
              : <span />)}
          onBlur={e => { if (e.target.value.trim() !== r.bid_price) savePrice(r, e.target.value) }} />
      ),
    },
    {
      title: '状态', width: 180,
      render: (_: unknown, r: ReviewResult) => {
        const m = RESULT_STATUS_CN[r.status] || { label: r.status, color: 'default' }
        return (
          <Space size={4}>
            <Tag color={m.color}>{m.label}</Tag>
            {r.status === 'running' && <Text type="secondary">{r.progress || (r.ocr_status === 'running' ? '识别中' : '')}</Text>}
            {r.status === 'failed' && <Tooltip title={r.error_msg}><Tag color="red">原因</Tag></Tooltip>}
          </Space>
        )
      },
    },
    {
      title: '操作', width: 320,
      render: (_: unknown, r: ReviewResult) => (
        <Space size={4} wrap>
          <Button size="small" icon={<FileAddOutlined />}
            disabled={r.status === 'running' || r.ocr_status === 'running'}
            onClick={() => { setAddToRow(r); setAddFiles([]) }}>加文件</Button>
          {(r.status === 'pending' || r.status === 'failed') && (
            <Button size="small" type="primary" ghost icon={<PlayCircleOutlined />}
              onClick={() => doStart(r)}>开始审查</Button>
          )}
          {r.status === 'done' && (
            <>
              <Popconfirm title="重新审查将覆盖 AI 判定与人工改判/改分（人工改过的报价保留），确定？"
                okText="重新审查" cancelText="取消" onConfirm={() => doStart(r)}>
                <Button size="small" icon={<PlayCircleOutlined />}>重审</Button>
              </Popconfirm>
              <Button size="small" type={viewingId === r.id ? 'primary' : 'default'}
                onClick={() => onOpenItems(r)}>查看结果</Button>
              <Button size="small" icon={<DownloadOutlined />}
                href={exportCsvUrl(task.id, r.id)}>导出</Button>
            </>
          )}
          <Popconfirm title="删除该投标方及其全部文件、审查结果？" okText="删除" cancelText="取消"
            onConfirm={async () => {
              try {
                await deleteResult(task.id, r.id)
                onChanged()
              } catch (err) { message.error(getErr(err, '删除失败')) }
            }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <Title level={5} style={{ marginTop: 16 }}>③ 投标方（每方可上传多个文件，系统合并后审查）</Title>
      <Button icon={<UploadOutlined />} disabled={!canUpload} onClick={openNew}>
        新建投标方并上传文件{!canUpload ? '（请先确认审查条目）' : ''}
      </Button>
      <Table rowKey="id" size="small" style={{ marginTop: 8 }}
        dataSource={task.results || []} pagination={false}
        locale={{ emptyText: '暂无投标方' }}
        columns={columns}
        expandable={{
          expandedRowRender: (r: ReviewResult) => (
            <List size="small" dataSource={r.files || []}
              locale={{ emptyText: '无文件' }}
              renderItem={f => (
                <List.Item actions={f.id ? [
                  <Popconfirm key="del" title="删除该文件？" okText="删除" cancelText="取消"
                    onConfirm={() => removeFile(r, f.id)}>
                    <Button type="link" size="small" danger>删除</Button>
                  </Popconfirm>,
                ] : []}>
                  <Space><PaperClipOutlined /><Text>{f.file_name}</Text></Space>
                </List.Item>
              )} />
          ),
          rowExpandable: (r: ReviewResult) => (r.file_count ?? 0) > 0,
        }} />

      {/* 新建投标方 + 批量上传 */}
      <Modal title="新建投标方并上传文件" open={upOpen} okText="创建并上传"
        confirmLoading={submitting} onOk={submitNew}
        onCancel={() => setUpOpen(false)} destroyOnHidden>
        <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
          <Input placeholder="投标方名称（留空则用首个文件名）" value={upLabel}
            onChange={e => setUpLabel(e.target.value)} maxLength={100} />
          {hasLots && (
            <Space>
              <Text>所投包：</Text>
              <Select style={{ width: 220 }} value={upLot} onChange={setUpLot}
                options={task.lots.map(l => ({
                  value: l.lot_no, label: `包${l.lot_no}${l.name ? `（${l.name}）` : ''}`,
                }))} />
            </Space>
          )}
          <Upload {...pickerProps(upFiles, setUpFiles)}>
            <Button icon={<UploadOutlined />}>选择文件（可多选）</Button>
          </Upload>
          {submitting && (
            <div>
              <Progress percent={stat.percent}
                status={stat.percent >= 100 ? 'success' : 'active'}
                format={p => p && p >= 100 ? '上传完成，正在保存…' : `${p}%`} />
              {stat.percent < 100 && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {fmtSpeed(stat.rate)}{fmtEta(stat.estimated) ? `　${fmtEta(stat.estimated)}` : ''}
                </Text>
              )}
            </div>
          )}
          <Text type="secondary">
            把该投标方的全部文件一次选上（资格、商务、技术、报价等）。支持 Word(.docx)/PDF/图片；
            系统按选择顺序合并后整体审查。
          </Text>
        </Space>
      </Modal>

      {/* 给已有投标方追加文件 */}
      <Modal title={`追加文件 — ${addToRow?.bid_file_name || ''}`} open={!!addToRow}
        okText="上传" confirmLoading={submitting} onOk={submitAddFiles}
        onCancel={() => setAddToRow(null)} destroyOnHidden>
        <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
          <Upload {...pickerProps(addFiles, setAddFiles)}>
            <Button icon={<UploadOutlined />}>选择文件（可多选）</Button>
          </Upload>
          {submitting && (
            <div>
              <Progress percent={stat.percent}
                status={stat.percent >= 100 ? 'success' : 'active'}
                format={p => p && p >= 100 ? '上传完成，正在保存…' : `${p}%`} />
              {stat.percent < 100 && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {fmtSpeed(stat.rate)}{fmtEta(stat.estimated) ? `　${fmtEta(stat.estimated)}` : ''}
                </Text>
              )}
            </div>
          )}
          <Text type="secondary">追加后该投标方需重新审查（旧识别结果将作废重新合并）。</Text>
        </Space>
      </Modal>
    </>
  )
}
