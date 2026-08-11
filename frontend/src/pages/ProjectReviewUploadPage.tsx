import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Card, Button, Drawer, Space, App, Upload, Popconfirm, Tooltip, Typography,
  Alert, Tag, Modal, Input, Tabs, Select,
} from 'antd'
import {
  PaperClipOutlined, EyeOutlined, DownloadOutlined, DeleteOutlined,
  CheckCircleOutlined, StopOutlined, SendOutlined,
} from '@ant-design/icons'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'
import { useAuth } from '../hooks/useAuth'
import { useFocusTarget, flashRow } from '../hooks/useFocusRow'
import {
  listReviewProjects, uploadReviewFile, deleteReviewFile,
  submitReview, confirmReview, rejectReview,
  reviewPreviewUrl, reviewDownloadUrl, type ReviewProject,
} from '../services/projectReview'
import PendingOwnerTag from '../components/PendingOwnerTag'

const { Text } = Typography

function fmtSize(n: number) {
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

export default function ProjectReviewUploadPage() {
  const { message } = App.useApp()
  const { user } = useAuth()
  const role = user?.role || ''
  const canUpload = ['agency', 'officer', 'assistant', 'pd_assistant', 'leader'].includes(role) || !!user?.is_admin
  // 审核评审资料：采购人方（与后端 _can_confirm_review 一致）
  const canConfirm = ['officer', 'assistant', 'leader'].includes(role) || !!user?.is_admin
  const [rejectRow, setRejectRow] = useState<ReviewProject | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const [rows, setRows] = useState<ReviewProject[]>([])
  const [loading, setLoading] = useState(false)
  const [cur, setCur] = useState<ReviewProject | null>(null)
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ open: boolean; url: string; name: string }>({ open: false, url: '', name: '' })

  // 这一屏的评审资料常常是「一份评审情况 PDF ＋ 几张签字照」，
  // 要一件件对着看。把同一批交给面板，就能在面板上直接翻，不用来回点关。
  const pvList = (cur?.attachments || [])
    .filter(a => isPreviewable(a.original_name))
    .map(a => ({ url: reviewPreviewUrl(cur!.id, a.id), filename: a.original_name }))
  const pvIdx = pvList.findIndex(x => x.url === preview.url)
  // 分类页签：待审核在最左并默认选中
  const [tab, setTab] = useState<'pending' | 'rejected' | 'done' | 'all'>('pending')
  const [keyword, setKeyword] = useState('')
  const [agencyFilter, setAgencyFilter] = useState<string>()
  const [methodFilter, setMethodFilter] = useState<string>()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listReviewProjects()
      setRows(res.data.data || [])
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])
  useEffect(() => { load() }, [load])

  // 待办「去处理」跳来时（?focus=项目id）：切到全部页签并高亮该行，
  // 否则项目可能正好不在当前页签里，点进来看不到东西。
  useFocusTarget(!loading && rows.length > 0, (id) => {
    if (!rows.some(r => r.id === id && bucketOf(r) === tab)) setTab('all')
    flashRow(id)
  })

  // 打开的抽屉同步最新数据
  useEffect(() => {
    if (cur) {
      const fresh = rows.find(r => r.id === cur.id)
      if (fresh && fresh !== cur) setCur(fresh)
    }
  }, [rows]) // eslint-disable-line react-hooks/exhaustive-deps

  const doUpload = async (file: File) => {
    if (!cur) return
    setUploading(true)
    try { await uploadReviewFile(cur.id, file); message.success('已上传'); await load() }
    catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '上传失败')
    } finally { setUploading(false) }
  }

  const runAction = async (fn: () => Promise<{ data: { message?: string } }>) => {
    try {
      const res = await fn()
      message.success(res.data.message || '操作成功')
      await load()
    } catch (e) {
      const err = e as { response?: { data?: { error?: string } } }
      message.error(err.response?.data?.error || '操作失败')
    }
  }

  const doReject = async () => {
    if (!rejectRow) return
    if (!rejectReason.trim()) { message.warning('请填写驳回原因'); return }
    await runAction(() => rejectReview(rejectRow.id, rejectReason.trim()))
    setRejectRow(null); setRejectReason('')
  }

  // 审核状态 → 卡片展示（"" 表示尚未提交审核）
  const REVIEW_META: Record<string, { text: string; color: string; accent: string }> = {
    '已确认': { text: '评审资料已确认', color: 'green', accent: '#34a853' },
    '待确认': { text: '待经办人确认', color: 'orange', accent: '#f9ab00' },
    '已驳回': { text: '已驳回，待补件', color: 'red', accent: '#d93025' },
  }

  const toCard = (p: ReviewProject): RecordCardData => {
    const n = p.attachments?.length || 0
    const rs = p.review_status || ''
    const meta = REVIEW_META[rs]
    // 项目已推进过采购结果阶段，评审资料就不可能还卡在「待提交审核」——
    // 那是本功能上线前上传的老资料，按历史资料显示，别再催人去审一遍
    const legacyDone = !rs && n > 0 && p.past_result
    return {
      key: p.id,
      accent: meta?.accent || (legacyDone ? '#5f6368' : n > 0 ? '#1a73e8' : '#f9ab00'),
      title: <span style={{ fontWeight: 600 }}>{p.name}</span>,
      subtitle: <Text type="secondary">{p.number}</Text>,
      statusText: meta?.text
        || (legacyDone ? '历史资料，无需审核' : n > 0 ? '已上传，待提交审核' : '待上传评审结果'),
      statusColor: meta?.color || (legacyDone ? 'default' : n > 0 ? 'blue' : 'orange'),
      tags: p.past_result
        ? <Tag color="default" style={{ marginInlineEnd: 0 }}>历史资料</Tag>
        : undefined,
      fields: [
        { label: '当前处理人', value: <PendingOwnerTag p={p.pending} compact /> },
        { label: '采购方式', value: p.method },
        { label: '代理机构', value: p.agency_name || p.agency_code || '—' },
        { label: '轮次', value: `第 ${p.current_round} 轮` },
        { label: '评审结果', value: n > 0 ? `${n} 个文件` : <Text type="warning">未上传</Text> },
        ...(rs === '已驳回' && p.review_reject_reason
          ? [{
            label: `驳回原因${(p.review_reject_count || 0) > 1 ? `（第${p.review_reject_count}次）` : ''}`,
            value: <Text type="danger">{p.review_reject_reason}</Text>,
          }]
          : []),
        ...(rs === '已确认' && p.review_confirmed_by
          ? [{ label: '确认人', value: p.review_confirmed_by }] : []),
      ],
      actions: (
        <>
          <Button size="small" type={n > 0 ? 'default' : 'primary'} icon={<PaperClipOutlined />} onClick={() => setCur(p)}>
            {canUpload ? '上传/查看评审结果' : '查看评审结果'}
          </Button>
          {/* 代理机构：传完点提交，被驳回后补件再提交 */}
          {canUpload && n > 0 && ['', '已驳回'].includes(rs) && !p.past_result && (
            <Button size="small" type="primary" ghost icon={<SendOutlined />}
              onClick={() => runAction(() => submitReview(p.id))}>
              {rs === '已驳回' ? '补件后重新提交' : '提交审核'}
            </Button>
          )}
          {/* 经办人：确认或驳回 */}
          {canConfirm && rs === '待确认' && (
            <>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />}
                onClick={() => runAction(() => confirmReview(p.id))}>确认</Button>
              <Button size="small" danger icon={<StopOutlined />}
                onClick={() => { setRejectRow(p); setRejectReason('') }}>驳回</Button>
            </>
          )}
        </>
      ),
    }
  }

  // ── 分类：待审核（未提交/待确认）/ 已驳回 / 已审核 ───────────────
  const bucketOf = (p: ReviewProject) => {
    const rs = p.review_status || ''
    if (rs === '已确认') return 'done'
    if (rs === '已驳回') return 'rejected'
    return 'pending'          // "" 未提交 与 待确认 都算待审核
  }

  const agencyOptions = useMemo(
    () => Array.from(new Set(rows.map(r => r.agency_name || r.agency_code).filter(Boolean)))
      .sort().map(v => ({ value: v as string, label: v as string })),
    [rows],
  )
  const methodOptions = useMemo(
    () => Array.from(new Set(rows.map(r => r.method).filter(Boolean)))
      .sort().map(v => ({ value: v as string, label: v as string })),
    [rows],
  )

  const applyFilter = (list: ReviewProject[]) => {
    const kw = keyword.trim()
    return list
      .filter(r => !agencyFilter || (r.agency_name || r.agency_code) === agencyFilter)
      .filter(r => !methodFilter || r.method === methodFilter)
      .filter(r => !kw
        || (r.name || '').includes(kw)
        || (r.number || '').includes(kw)
        || (r.officer || '').includes(kw)
        || (r.agency_name || '').includes(kw))
  }

  const counts = {
    pending: rows.filter(r => bucketOf(r) === 'pending').length,
    rejected: rows.filter(r => bucketOf(r) === 'rejected').length,
    done: rows.filter(r => bucketOf(r) === 'done').length,
  }
  const shown = applyFilter(tab === 'all' ? rows : rows.filter(r => bucketOf(r) === tab))

  return (
    <Card title="8.5 项目评审资料上传">
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        message="院内竞选 / 单一来源采购：代理机构完成可开标判定、线下开标评审后，在此上传「签字的评审结果」并提交审核；经办人确认后方可在「9. 采购结果确认」草拟采购结果确认函。已推进到后续阶段的项目仍会保留在此（标「历史资料」）。"
      />

      <Tabs
        activeKey={tab}
        onChange={k => setTab(k as typeof tab)}
        items={[
          { key: 'pending', label: `待审核 (${counts.pending})` },
          { key: 'rejected', label: `已驳回 (${counts.rejected})` },
          { key: 'done', label: `已审核 (${counts.done})` },
          { key: 'all', label: `全部 (${rows.length})` },
        ]}
      />

      <Space wrap style={{ marginBottom: 12 }}>
        <Input.Search
          allowClear placeholder="搜索项目名称 / 编号 / 经办人 / 代理机构"
          style={{ width: 300 }}
          onChange={e => setKeyword(e.target.value)}
        />
        <Select
          allowClear showSearch placeholder="按代理机构筛选" style={{ width: 210 }}
          value={agencyFilter} onChange={setAgencyFilter} options={agencyOptions}
        />
        <Select
          allowClear showSearch placeholder="按采购方式筛选" style={{ width: 180 }}
          value={methodFilter} onChange={setMethodFilter} options={methodOptions}
        />
        {(agencyFilter || methodFilter || keyword.trim()) && (
          <Tag color="blue">筛选后 {shown.length} 条</Tag>
        )}
      </Space>

      <RecordCards dataSource={shown} toCard={toCard} loading={loading}
        emptyText={tab === 'pending' ? '没有待审核的评审资料' : '暂无数据'} />

      <Drawer title={`评审结果 — ${cur?.name || ''}`} open={!!cur} onClose={() => setCur(null)} width={520}>
        {cur && (
          <div>
            {(cur.attachments || []).length === 0 ? (
              <Text type="secondary">暂无评审结果文件</Text>
            ) : (
              (cur.attachments || []).map(att => (
                <div key={att.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 10px', borderRadius: 6, marginBottom: 4,
                  background: '#fafafa', border: '1px solid #f0f0f0',
                }}>
                  <Tooltip title={att.original_name}>
                    <span style={{ fontSize: 13, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {att.original_name}
                    </span>
                  </Tooltip>
                  <Space size={2}>
                    <Text type="secondary" style={{ fontSize: 11 }}>{fmtSize(att.file_size)}</Text>
                    {isPreviewable(att.original_name) && (
                      <Button size="small" type="link" icon={<EyeOutlined />}
                        onClick={() => setPreview({ open: true, url: reviewPreviewUrl(cur.id, att.id), name: att.original_name })} />
                    )}
                    <Button size="small" type="link" icon={<DownloadOutlined />}
                      href={reviewDownloadUrl(cur.id, att.id)} download={att.original_name} />
                    {canUpload && (
                      <Popconfirm title="删除该文件？" onConfirm={async () => {
                        try { await deleteReviewFile(cur.id, att.id); message.success('已删除'); await load() }
                        catch { message.error('删除失败') }
                      }}>
                        <Button size="small" type="link" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    )}
                  </Space>
                </div>
              ))
            )}
            {canUpload && (
              <>
                <Upload showUploadList={false} beforeUpload={(f) => { doUpload(f as File); return false }}>
                  <Button icon={<PaperClipOutlined />} loading={uploading} type="primary" style={{ marginTop: 10 }}>
                    上传评审结果
                  </Button>
                </Upload>
                <div style={{ color: '#aaa', fontSize: 12, marginTop: 6 }}>
                  上传签字盖章的评审结果（PDF / Word / 图片等）。上传后即可草拟采购结果确认函。
                </div>
              </>
            )}
          </div>
        )}
      </Drawer>

      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        siblings={pvList}
        index={pvIdx}
        onNavigate={i => setPreview({ open: true, url: pvList[i].url, name: pvList[i].filename })}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />

      {/* ── 驳回评审资料 ─────────────────────────────────────────── */}
      <Modal
        open={!!rejectRow}
        title={`驳回评审资料 — ${rejectRow?.name || ''}`}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        onOk={doReject}
        onCancel={() => { setRejectRow(null); setRejectReason('') }}
      >
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message="驳回后代理机构补件或重传，再次提交需重新确认。驳回原因会记入审批过程记录，归档时随项目一并留存。" />
        <Input.TextArea
          rows={4} maxLength={500} showCount
          placeholder="请写明缺什么或哪里不合格，例如：评审报告缺少第二位评审专家签字；报价一览表未附"
          value={rejectReason}
          onChange={e => setRejectReason(e.target.value)}
        />
      </Modal>
    </Card>
  )
}
