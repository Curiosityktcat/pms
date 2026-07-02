/**
 * 8.1 询议价评审（评定标报告）
 *
 * 列表：待评审（已发出的询/议价函，截止日期过后可进入）/ 已评审。
 * 工作台（?inquiry=ID）：左侧采购文件 + 各供应商响应文件（可上传/预览），
 * 右侧评定标报告（项目信息预填，逐供应商填资格性/符合性/最终价格，
 * 中选或废标出结果），完成后可下载 Excel 打印签字；废标可一键开下一轮。
 */
import { useState, useEffect, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  Table, Button, Card, Space, Tag, Tabs, App, Typography, Input, InputNumber,
  Select, Radio, DatePicker, Row, Col, Upload, Tooltip, Divider, Alert, Spin, Empty,
  Checkbox,
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, CheckCircleOutlined, DownloadOutlined,
  EyeOutlined, UploadOutlined, DeleteOutlined, RollbackOutlined,
  FileTextOutlined, PaperClipOutlined, SendOutlined, SyncOutlined,
  SwapOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import dayjs from 'dayjs'
import FilePreviewModal, { isPreviewable } from '../components/FilePreviewModal'
import {
  listInquiryReviews, getInquiryReview, saveInquiryReview, completeInquiryReview,
  reopenInquiryReview, startNextRound, convertToNegotiation, reviewExcelUrl,
  fetchReviewReplies, earlyOpenReview,
  uploadSupplierFile, deleteSupplierFile, supplierFileDownloadUrl, supplierFilePreviewUrl,
  listAttachments, attachmentPreviewUrl, attachmentDownloadUrl, previewWordUrl,
  type InquiryReview, type InquiryReviewListRow, type InquirySupplier,
  type InquiryAttachment,
} from '../services/inquiry'
import { useAuth } from '../hooks/useAuth'

const { TextArea } = Input
const { Text } = Typography

const CN = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const cnOrd = (n: number) => (n < CN.length ? CN[n] : String(n))

type PreviewState = { open: boolean; url: string; name: string; dl?: string }

function apiErr(err: unknown, fallback: string): string {
  return (err as { response?: { data?: { error?: string } } })?.response?.data?.error || fallback
}

// ════════════════════════════════════════════════════════════════
// 列表视图
// ════════════════════════════════════════════════════════════════

function ReviewList({ onOpen }: { onOpen: (id: number) => void }) {
  const { message, modal } = App.useApp()
  const { user } = useAuth()
  const isOfficer = user?.role === 'officer'
  const [rows, setRows] = useState<InquiryReviewListRow[]>([])
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState<'待评审' | '已评审'>('待评审')
  const [fetchingId, setFetchingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listInquiryReviews()
      setRows(res.data.data)
    } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [message])
  useEffect(() => { load() }, [load])

  // 截止日期未到时，经办人确认「提前开启评审」（供应商文件已齐）
  const doEarlyOpen = (r: InquiryReviewListRow) => {
    const allIn = r.supplier_count > 0 && r.responded_count >= r.supplier_count
    modal.confirm({
      title: '提前开启评审',
      content: (
        <div>
          <p>
            递交截止日期（<b>{r.deadline || '未填写'}</b>）尚未到。
            当前已响应 <b>{r.responded_count}</b> / {r.supplier_count} 家。
          </p>
          {!allIn && (
            <p style={{ color: '#d46b08' }}>
              注意：仍有供应商未递交响应文件，提前开启后将不再等待其余供应商，请确认文件已齐。
            </p>
          )}
          <p>确认由经办人提前开启本轮评审？</p>
        </div>
      ),
      okText: '确认提前开启',
      onOk: async () => {
        try {
          await earlyOpenReview(r.inquiry_id)
          message.success('已提前开启评审')
          onOpen(r.inquiry_id)
        } catch (err: unknown) {
          message.error(apiErr(err, '操作失败'))
        }
      },
    })
  }

  // 从收件箱抓取供应商回复 → 导入响应文件 + 标记已响应（原在 7. 询/议价函详情，现挪到 8.1 卡片）
  const doFetchReplies = async (r: InquiryReviewListRow) => {
    setFetchingId(r.inquiry_id)
    try {
      const res = await fetchReviewReplies(r.inquiry_id)
      message.success(res.data.message || '已抓取供应商回复')
      load()
    } catch (err: unknown) {
      message.error(apiErr(err, '抓取失败'))
    } finally {
      setFetchingId(null)
    }
  }

  const pending = rows.filter(r => r.review_status !== '已完成' && r.letter_status !== '草稿')
  const done    = rows.filter(r => r.review_status === '已完成')
  const data    = tab === '待评审' ? pending : done

  const reviewToCard = (r: InquiryReviewListRow): RecordCardData => {
    const isDone = r.review_status === '已完成'
    const isDraft = r.review_status === '草稿'
    return {
      key: r.inquiry_id,
      accent: isDone ? '#34a853' : isDraft ? '#1a73e8' : '#9aa0a6',
      title: `${r.project_name}${r.round_no > 1 ? `（第${cnOrd(r.round_no)}次）` : ''}`,
      onTitleClick: () => onOpen(r.inquiry_id),
      subtitle: r.project_number,
      statusText: isDone ? '已完成' : isDraft ? '评审中' : '未开始',
      statusColor: isDone ? 'green' : isDraft ? 'processing' : 'default',
      tags: (
        <>
          <Tag color={r.type === '询价' ? 'blue' : r.type === '紧急采购' ? 'red' : 'orange'} style={{ marginInlineEnd: 0 }}>{r.type}</Tag>
          {isDone && r.result_type && <Tag color={r.result_type === '中选' ? 'gold' : 'red'} style={{ marginInlineEnd: 0 }}>{r.result_type}</Tag>}
          {isDraft && r.early_open === 1 && <Tag color="orange" style={{ marginInlineEnd: 0 }}>提前开启</Tag>}
        </>
      ),
      fields: [
        { label: '截止', value: r.deadline ? <span>{r.deadline} {r.deadline_passed ? <Tag color="green">已截止</Tag> : <Tag color="orange">未到期</Tag>}</span> : '' },
        { label: '供应商', value: `${r.supplier_count} 家` },
        { label: '办法', value: r.method },
      ],
      actions: (
        <Space size={4} wrap>
          {!isDone && (
            <Tooltip title="从收件箱抓取本项目供应商回复：匹配到的自动勾「已响应」，邮件附件直接导入为响应文件">
              <Button size="small" icon={<SyncOutlined />} loading={fetchingId === r.inquiry_id}
                onClick={() => doFetchReplies(r)}>抓取回复</Button>
            </Tooltip>
          )}
          {isDone ? (
            <Button size="small" icon={<EyeOutlined />} onClick={() => onOpen(r.inquiry_id)}>查看</Button>
          ) : (isDraft || r.deadline_passed) ? (
            <Button size="small" type="primary" ghost onClick={() => onOpen(r.inquiry_id)}>
              {isDraft ? '继续评审' : '评审'}
            </Button>
          ) : isOfficer ? (
            <Tooltip title="供应商文件已齐时，经办人可在截止日期前提前开启评审">
              <Button size="small" onClick={() => doEarlyOpen(r)}>提前开启</Button>
            </Tooltip>
          ) : (
            <Tooltip title={`递交截止日期 ${r.deadline || '未填写'} 过后可评审；如文件已齐，可由经办人提前开启`}>
              <Button size="small" type="primary" disabled>评审</Button>
            </Tooltip>
          )}
        </Space>
      ),
    }
  }

  return (
    <Card title={<span style={{ fontWeight: 700, fontSize: 16 }}>8.1 询议价、紧急采购评审</span>}>
      <Tabs
        activeKey={tab}
        onChange={k => setTab(k as '待评审' | '已评审')}
        items={[
          { key: '待评审', label: <span>待评审 <Tag color="blue">{pending.length}</Tag></span> },
          { key: '已评审', label: <span>已评审 <Tag color="green">{done.length}</Tag></span> },
        ]}
      />
      <RecordCards dataSource={data} loading={loading} emptyText="暂无评审" toCard={reviewToCard} />
    </Card>
  )
}

// ════════════════════════════════════════════════════════════════
// 评审工作台
// ════════════════════════════════════════════════════════════════

const PASS_OPTS = [
  { value: '', label: '—' },
  { value: '通过', label: '通过' },
  { value: '不通过', label: '不通过' },
]

function ReviewWorkspace({ inquiryId, onBack }: { inquiryId: number; onBack: () => void }) {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [review, setReview] = useState<InquiryReview | null>(null)
  const [sups, setSups] = useState<InquirySupplier[]>([])
  const [winnerId, setWinnerId] = useState<number | undefined>(undefined)
  const [attachments, setAttachments] = useState<InquiryAttachment[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [preview, setPreview] = useState<PreviewState>({ open: false, url: '', name: '' })

  const applyReview = useCallback((r: InquiryReview) => {
    setReview(r)
    setSups(r.suppliers)
    const w = r.suppliers.find(s => s.is_selected)
    setWinnerId(w?.id)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const res = await getInquiryReview(inquiryId)
      applyReview(res.data.data)
      const att = await listAttachments(inquiryId)
      setAttachments(att.data.data)
    } catch (err: unknown) {
      setLoadError(apiErr(err, '加载评审记录失败'))
    } finally { setLoading(false) }
  }, [inquiryId, applyReview])
  useEffect(() => { load() }, [load])

  const editable = review?.status === '草稿'

  const setField = <K extends keyof InquiryReview>(k: K, v: InquiryReview[K]) =>
    setReview(prev => (prev ? { ...prev, [k]: v } : prev))

  const setSup = (id: number, patch: Partial<InquirySupplier>) =>
    setSups(prev => prev.map(s => (s.id === id ? { ...s, ...patch } : s)))

  const responded = sups.filter(s => s.responded === 1)
  const passed = responded.filter(s => s.qual_pass === '通过' && s.conform_pass === '通过')
  const need = review?.method === '院内询价' ? 3 : 1

  const supplierPayload = () => sups.map(s => ({
    id: s.id,
    supplier_name: s.supplier_name,
    responded: s.responded,
    quote_amount: s.quote_amount,
    quote_date: s.quote_date,
    quote_note: s.quote_note,
    qual_pass: s.qual_pass,
    conform_pass: s.conform_pass,
    final_price: s.final_price,
    review_rank: s.review_rank,
    fail_reason: s.fail_reason,
  }))

  const doSave = async (silent = false) => {
    if (!review) return false
    setSaving(true)
    try {
      const res = await saveInquiryReview(inquiryId, {
        project_name: review.project_name,
        project_number: review.project_number,
        package_no: review.package_no,
        content: review.content,
        budget: review.budget,
        review_date: review.review_date,
        location: review.location,
        method: review.method,
        result_type: review.result_type,
        result_text: review.result_text,
        remark: review.remark,
        review_place: review.review_place,
        committee: review.committee,
        bid_open_info: review.bid_open_info,
        suppliers: supplierPayload(),
      })
      applyReview(res.data.data)
      if (!silent) message.success('已保存')
      return true
    } catch (err: unknown) {
      message.error(apiErr(err, '保存失败'))
      return false
    } finally { setSaving(false) }
  }

  const doComplete = (resultType: '中选' | '废标') => {
    if (!review) return
    if (resultType === '中选' && !winnerId) {
      message.warning('请先在「采购结果」中选择中选供应商')
      return
    }
    const winner = sups.find(s => s.id === winnerId)
    modal.confirm({
      title: `确认评审结果：${resultType}`,
      content: resultType === '中选'
        ? `确认「${winner?.supplier_name}」中选？确认后本轮评审完成，可下载评定标报告打印签字。`
        : '确认本轮废标？确认后可下载评定标报告，并可一键开启下一轮邀请。',
      okText: `确认${resultType}`,
      okButtonProps: resultType === '废标' ? { danger: true } : {},
      onOk: async () => {
        if (!(await doSave(true))) return
        try {
          const res = await completeInquiryReview(inquiryId, resultType, winnerId)
          applyReview(res.data.data)
          message.success(res.data.message || '评审完成')
        } catch (err: unknown) {
          message.error(apiErr(err, '操作失败'))
        }
      },
    })
  }

  const doReopen = () => {
    modal.confirm({
      title: '撤回评审',
      content: '撤回后评审记录退回草稿状态，函件恢复为进行中，可重新修改。确认撤回？',
      onOk: async () => {
        try {
          const res = await reopenInquiryReview(inquiryId)
          applyReview(res.data.data)
          message.success('已撤回')
        } catch (err: unknown) {
          message.error(apiErr(err, '撤回失败'))
        }
      },
    })
  }

  const doNextRound = () => {
    modal.confirm({
      title: '开启下一轮',
      content: '将复制本轮函件（含供应商名单与附件）为新一轮草稿，到「7. 询/议价函」中调整后重新发出邀请。确认？',
      onOk: async () => {
        try {
          const res = await startNextRound(inquiryId)
          message.success(res.data.message || '已开启下一轮')
          navigate('/inquiry')
        } catch (err: unknown) {
          message.error(apiErr(err, '操作失败'))
        }
      },
    })
  }

  const doConvertNegotiation = () => {
    modal.confirm({
      title: `转为第${review?.round_no || ''}次院内议价`,
      width: 520,
      content: `本次院内询价的废标记录将保留归档；系统另建同轮次（第${review?.round_no || ''}次）` +
        '的院内议价函草稿（供应商名单默认带入已递交响应的供应商），' +
        '到「7. 询/议价函」中确认后发出议价邀请。确认转换？',
      okText: '转为院内议价',
      onOk: async () => {
        try {
          const res = await convertToNegotiation(inquiryId)
          message.success(res.data.message || '已转为院内议价')
          navigate('/inquiry')
        } catch (err: unknown) {
          message.error(apiErr(err, '操作失败'))
        }
      },
    })
  }

  const doFetchReplies = async () => {
    setFetching(true)
    try {
      const res = await fetchReviewReplies(inquiryId)
      const d = res.data.data
      message.success(res.data.message || `匹配到 ${d.replied} 家回复`)
      if (d.unmatched.length > 0) {
        modal.info({
          title: '以下邮件主题含本项目名，但未匹配到供应商（请人工归类）',
          width: 640,
          content: (
            <ul style={{ paddingLeft: 18 }}>
              {d.unmatched.map((u, i) => (
                <li key={i}><b>{u.subject}</b><br /><Text type="secondary">{u.from}　{u.date}</Text></li>
              ))}
            </ul>
          ),
        })
      }
      load()
    } catch (err: unknown) {
      message.error(apiErr(err, '拉取失败，请检查邮箱配置'))
    } finally { setFetching(false) }
  }

  const handleUpload = async (supplierId: number, file: File) => {
    try {
      await uploadSupplierFile(inquiryId, supplierId, file)
      message.success('已上传')
      load()
    } catch (err: unknown) {
      message.error(apiErr(err, '上传失败'))
    }
    return false
  }

  const handleDeleteFile = (fileId: number, name: string) => {
    modal.confirm({
      title: '删除文件',
      content: `确认删除「${name}」？`,
      onOk: async () => {
        try {
          await deleteSupplierFile(inquiryId, fileId)
          message.success('已删除')
          load()
        } catch { message.error('删除失败') }
      },
    })
  }

  const openPreview = (url: string, name: string, dl?: string) =>
    setPreview({ open: true, url, name, dl })

  if (loading) {
    return <Card><div style={{ textAlign: 'center', padding: 60 }}><Spin tip="加载中…" /></div></Card>
  }
  if (loadError || !review) {
    return (
      <Card>
        <Alert type="warning" showIcon message={loadError || '评审记录不存在'}
          action={<Button size="small" onClick={onBack}>返回列表</Button>} />
      </Card>
    )
  }

  // ── 供应商评审表格（只有「已响应」的行可填，未响应的不进报告）──
  const rowOn = (s: InquirySupplier) => editable && s.responded === 1
  const supColumns: ColumnsType<InquirySupplier> = [
    {
      title: <Tooltip title="实际递交了响应文件的供应商。「拉取邮箱回复」或上传响应文件会自动勾选，也可手动勾。未勾选的不进评定标报告。">已响应</Tooltip>,
      dataIndex: 'responded', width: 70, align: 'center' as const,
      render: (v: number, s) => (
        <Checkbox checked={v === 1} disabled={!editable}
          onChange={e => setSup(s.id, { responded: e.target.checked ? 1 : 0 })} />
      ),
    },
    {
      title: '供应商名称', dataIndex: 'supplier_name', ellipsis: true,
      render: (v: string, s) => (
        <Space size={4} style={{ width: '100%' }}>
          {editable ? (
            <Input size="small" value={v} placeholder="供应商名称"
              style={{ opacity: s.responded ? 1 : 0.6 }}
              onChange={e => setSup(s.id, { supplier_name: e.target.value })} />
          ) : (
            <span style={{ opacity: s.responded ? 1 : 0.45 }}>{v}</span>
          )}
          {s.is_selected === 1 && <Tag color="gold">中选</Tag>}
        </Space>
      ),
    },
    {
      title: '供应商报价', dataIndex: 'quote_amount', width: 140,
      render: (v: number | null, s) => rowOn(s) ? (
        <InputNumber
          size="small" style={{ width: '100%' }} min={0} addonAfter="元"
          value={v} placeholder="未报价留空"
          onChange={val => setSup(s.id, { quote_amount: val as number | null })}
        />
      ) : (s.responded && v != null ? `${v}元` : '—'),
    },
    {
      title: '资格性审查', dataIndex: 'qual_pass', width: 110,
      render: (v: string, s) => rowOn(s) ? (
        <Select size="small" style={{ width: '100%' }} value={v} options={PASS_OPTS}
          onChange={val => setSup(s.id, { qual_pass: val as InquirySupplier['qual_pass'] })} />
      ) : (s.responded && v ? <Tag color={v === '通过' ? 'green' : 'red'}>{v}</Tag> : '—'),
    },
    {
      title: '符合性审查', dataIndex: 'conform_pass', width: 110,
      render: (v: string, s) => rowOn(s) ? (
        <Select size="small" style={{ width: '100%' }} value={v} options={PASS_OPTS}
          onChange={val => setSup(s.id, { conform_pass: val as InquirySupplier['conform_pass'] })} />
      ) : (s.responded && v ? <Tag color={v === '通过' ? 'green' : 'red'}>{v}</Tag> : '—'),
    },
    {
      title: <Tooltip title="与供应商电话/邮件确认后的最终报价，如「35133元」或「维持原价不变」">最终价格</Tooltip>,
      dataIndex: 'final_price', width: 140,
      render: (v: string, s) => rowOn(s) ? (
        <Input size="small" value={v} placeholder="如 35133元"
          onChange={e => setSup(s.id, { final_price: e.target.value })} />
      ) : ((s.responded && v) || '—'),
    },
    {
      title: '排名', dataIndex: 'review_rank', width: 80,
      render: (v: string, s) => rowOn(s) ? (
        <Input size="small" value={v} placeholder="如 1"
          onChange={e => setSup(s.id, { review_rank: e.target.value })} />
      ) : ((s.responded && v) || '—'),
    },
    {
      title: <Tooltip title="未通过审查时填写，进入报告附件三的无效供应商名单">无效原因</Tooltip>,
      dataIndex: 'fail_reason', width: 160,
      render: (v: string, s) => {
        const failed = s.qual_pass === '不通过' || s.conform_pass === '不通过'
        if (!rowOn(s)) return (s.responded && v) || '—'
        return (
          <Input size="small" value={v} disabled={!failed}
            placeholder={failed ? '如 未提供营业执照' : '通过则无需填写'}
            onChange={e => setSup(s.id, { fail_reason: e.target.value })} />
        )
      },
    },
  ]

  const labelStyle: React.CSSProperties = { color: '#666', fontSize: 13, marginBottom: 2 }

  return (
    <Card
      title={
        <Space wrap>
          <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回</Button>
          <span style={{ fontWeight: 700, fontSize: 16 }}>
            {review.project_name}
            {review.round_no > 1 && `（第${cnOrd(review.round_no)}次）`}
          </span>
          <Tag color={review.letter_type === '询价' ? 'blue' : 'orange'}>{review.letter_type}</Tag>
          <Tag>{review.method}</Tag>
          {review.status === '已完成'
            ? (
              <>
                <Tag color="green">评审已完成</Tag>
                {review.result_type && (
                  <Tag color={review.result_type === '中选' ? 'gold' : 'red'}>{review.result_type}</Tag>
                )}
              </>
            )
            : <Tag color="processing">评审中</Tag>}
          {review.early_open === 1 && (
            <Tooltip title={`经办人 ${review.early_open_by || ''} 于 ${review.early_open_at || ''} 在截止日期前提前开启`}>
              <Tag color="orange">提前开启</Tag>
            </Tooltip>
          )}
        </Space>
      }
      extra={
        <Space wrap>
          {editable && (
            <Button icon={<SaveOutlined />} loading={saving} onClick={() => doSave()}>
              保存草稿
            </Button>
          )}
          {editable && (
            <>
              <Button type="primary" icon={<CheckCircleOutlined />}
                onClick={() => doComplete('中选')}>
                完成评审（中选）
              </Button>
              <Button danger icon={<CheckCircleOutlined />}
                onClick={() => doComplete('废标')}>
                完成评审（废标）
              </Button>
            </>
          )}
          {review.status === '已完成' && (
            <Button icon={<RollbackOutlined />} onClick={doReopen}>撤回评审</Button>
          )}
          {review.status === '已完成' && review.result_type === '废标' && (
            <Button type="primary" icon={<SendOutlined />} onClick={doNextRound}>
              开启下一轮
            </Button>
          )}
          {review.status === '已完成' && review.result_type === '废标'
            && review.letter_type === '询价' && (review.round_no || 1) >= 2 && (
            <Button icon={<SwapOutlined />} style={{ color: '#d46b08', borderColor: '#d46b08' }}
              onClick={doConvertNegotiation}>
              转为院内议价（第{review.round_no}次）
            </Button>
          )}
          <Button icon={<DownloadOutlined />}
            onClick={() => window.open(reviewExcelUrl(inquiryId), '_blank')}>
            评定标报告
          </Button>
        </Space>
      }
    >
      <Row gutter={16}>
        {/* ── 左：文件区 ─────────────────────────────────────── */}
        <Col xs={24} lg={9}>
          <Card size="small" title={<><FileTextOutlined /> 采购文件</>}
            style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
              <Text>{review.letter_type}邀请函（系统生成）</Text>
              <Button size="small" icon={<EyeOutlined />}
                onClick={() => openPreview(previewWordUrl(inquiryId), '邀请函.docx')}>
                预览
              </Button>
            </div>
            <Divider style={{ margin: '8px 0' }} />
            {attachments.length === 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>无函件附件</Text>
            )}
            {attachments.map(a => (
              <div key={a.id}
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
                <Text ellipsis style={{ maxWidth: '60%' }} title={a.filename}>
                  <PaperClipOutlined /> {a.filename}
                </Text>
                <Space size={4}>
                  {isPreviewable(a.filename) && (
                    <Button size="small" icon={<EyeOutlined />}
                      onClick={() => openPreview(
                        attachmentPreviewUrl(inquiryId, a.id), a.filename,
                        attachmentDownloadUrl(inquiryId, a.id))}>
                      预览
                    </Button>
                  )}
                  <Button size="small" icon={<DownloadOutlined />}
                    href={attachmentDownloadUrl(inquiryId, a.id)} />
                </Space>
              </div>
            ))}
          </Card>

          <Card size="small" title={<><PaperClipOutlined /> 供应商响应文件</>}>
            {sups.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无供应商" />}
            {sups.map(s => {
              const files = review.supplier_files[s.id] || []
              return (
                <div key={s.id} style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Space size={4} style={{ maxWidth: '70%', overflow: 'hidden' }}>
                      <Text strong ellipsis title={s.supplier_name}>
                        {s.supplier_name}
                      </Text>
                      {s.responded === 1
                        ? <Tag color="green" style={{ marginInlineEnd: 0 }}>已响应</Tag>
                        : <Tag style={{ marginInlineEnd: 0 }}>未响应</Tag>}
                    </Space>
                    <Upload
                      showUploadList={false}
                      beforeUpload={(file) => handleUpload(s.id, file)}
                      accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.zip,.rar"
                    >
                      <Button size="small" icon={<UploadOutlined />}>上传</Button>
                    </Upload>
                  </div>
                  {files.length === 0
                    ? <Text type="secondary" style={{ fontSize: 12 }}>未上传响应文件（邮件附件或邮寄资料扫描件）</Text>
                    : files.map(f => (
                      <div key={f.id}
                        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '2px 0' }}>
                        <Text ellipsis style={{ maxWidth: '55%', fontSize: 13 }} title={f.filename}>
                          {f.filename}
                        </Text>
                        <Space size={4}>
                          {isPreviewable(f.filename) && (
                            <Button size="small" type="text" icon={<EyeOutlined />}
                              onClick={() => openPreview(
                                supplierFilePreviewUrl(inquiryId, f.id), f.filename,
                                supplierFileDownloadUrl(inquiryId, f.id))} />
                          )}
                          <Button size="small" type="text" icon={<DownloadOutlined />}
                            href={supplierFileDownloadUrl(inquiryId, f.id)} />
                          {editable && (
                            <Button size="small" type="text" danger icon={<DeleteOutlined />}
                              onClick={() => handleDeleteFile(f.id, f.filename)} />
                          )}
                        </Space>
                      </div>
                    ))}
                  <Divider style={{ margin: '8px 0' }} />
                </div>
              )
            })}
          </Card>
        </Col>

        {/* ── 右：评定标报告 ─────────────────────────────────── */}
        <Col xs={24} lg={15}>
          <Card size="small" title="一、项目信息" style={{ marginBottom: 16 }}>
            <Row gutter={[12, 8]}>
              <Col span={12}>
                <div style={labelStyle}>项目名称</div>
                <Input value={review.project_name} disabled={!editable}
                  onChange={e => setField('project_name', e.target.value)} />
              </Col>
              <Col span={8}>
                <div style={labelStyle}>项目编号</div>
                <Input value={review.project_number} disabled={!editable}
                  onChange={e => setField('project_number', e.target.value)} />
              </Col>
              <Col span={4}>
                <div style={labelStyle}>包号</div>
                <Input value={review.package_no} disabled={!editable}
                  onChange={e => setField('package_no', e.target.value)} />
              </Col>
              <Col span={24}>
                <div style={labelStyle}>采购内容</div>
                <TextArea rows={2} value={review.content} disabled={!editable}
                  onChange={e => setField('content', e.target.value)} />
              </Col>
              <Col span={8}>
                <div style={labelStyle}>预算金额</div>
                <Input value={review.budget} disabled={!editable} placeholder="如 35485.8元"
                  onChange={e => setField('budget', e.target.value)} />
              </Col>
              <Col span={8}>
                <div style={labelStyle}>采购时间（选填）</div>
                <DatePicker
                  style={{ width: '100%' }}
                  value={review.review_date ? dayjs(review.review_date) : null}
                  disabled={!editable}
                  onChange={d => setField('review_date', d ? d.format('YYYY-MM-DD') : '')}
                />
              </Col>
              <Col span={8}>
                <div style={labelStyle}>采购地点</div>
                <Input value={review.location} disabled={!editable}
                  onChange={e => setField('location', e.target.value)} />
              </Col>
              <Col span={24}>
                <div style={labelStyle}>评审办法</div>
                <Radio.Group
                  value={review.method}
                  disabled={!editable || review.letter_type !== '询价' || !review.method_switchable}
                  onChange={e => setField('method', e.target.value)}
                >
                  <Radio value="院内询价">院内询价（通过审查须满 3 家）</Radio>
                  <Radio value="院内议价">院内议价（1 家及以上即可）</Radio>
                </Radio.Group>
                {review.letter_type === '询价' && !review.method_switchable && (
                  <div style={{ color: '#999', fontSize: 12, marginTop: 2 }}>
                    询价项目第一轮不允许转为院内议价；第二轮起经办人可酌情转换
                  </div>
                )}
              </Col>
            </Row>
          </Card>

          <Card
            size="small"
            title="二、评审过程"
            style={{ marginBottom: 16 }}
            extra={editable && (
              <Tooltip title="从收件箱抓取本项目的供应商回复：匹配到的自动勾「已响应」，邮件附件直接导入为响应文件">
                <Button size="small" icon={<SyncOutlined />} loading={fetching}
                  onClick={doFetchReplies}>
                  拉取邮箱回复
                </Button>
              </Tooltip>
            )}
          >
            <Alert
              style={{ marginBottom: 8 }}
              type={passed.length >= need ? 'success' : 'warning'}
              showIcon
              message={
                <span>
                  已响应 <b>{responded.length}</b> / {sups.length} 家，
                  通过资格性+符合性审查：<b>{passed.length}</b> 家
                  （{review.method}要求 ≥ {need} 家）
                  {review.method === '院内询价' && passed.length < 3 && review.method_switchable && (
                    <Text type="secondary">　不足三家可废标，或将评审办法转为院内议价</Text>
                  )}
                </span>
              }
            />
            <Table
              rowKey="id"
              size="small"
              columns={supColumns}
              dataSource={sups}
              pagination={false}
            />
          </Card>

          <Card size="small" title="三、采购结果">
            <Row gutter={[12, 8]}>
              <Col span={24}>
                <Space wrap>
                  <Radio.Group
                    value={review.result_type || undefined}
                    disabled={!editable}
                    onChange={e => setField('result_type', e.target.value)}
                  >
                    <Radio.Button value="中选">中选</Radio.Button>
                    <Radio.Button value="废标">废标</Radio.Button>
                  </Radio.Group>
                  {review.result_type === '中选' && (
                    <Select
                      style={{ minWidth: 260 }}
                      placeholder="选择中选供应商（仅通过审查的可选）"
                      value={winnerId}
                      disabled={!editable}
                      onChange={v => setWinnerId(v)}
                      options={passed.map(s => ({
                        value: s.id,
                        label: `${s.supplier_name}${s.final_price ? `（${s.final_price}）` : ''}`,
                      }))}
                    />
                  )}
                </Space>
              </Col>
              <Col span={24}>
                <div style={labelStyle}>采购结果（留空则完成评审时自动生成）</div>
                <TextArea rows={2} value={review.result_text} disabled={!editable}
                  placeholder='如：四川xx有限公司以35133元价格成交。 / 有效供应商不足三家，故废标。'
                  onChange={e => setField('result_text', e.target.value)} />
              </Col>
              <Col span={24}>
                <div style={labelStyle}>备注（选填）</div>
                <TextArea rows={1} value={review.remark} disabled={!editable}
                  onChange={e => setField('remark', e.target.value)} />
              </Col>
            </Row>
          </Card>
          {/* 四、评审地点/委员会、五、开标情况：界面不展示（经办人不填），
              报告 Excel 仍按模板保留这两节（开标情况含自动预填的截止时间）及签字/确认行 */}
        </Col>
      </Row>

      <FilePreviewModal
        open={preview.open}
        url={preview.url}
        filename={preview.name}
        downloadUrl={preview.dl}
        onClose={() => setPreview(p => ({ ...p, open: false }))}
      />
    </Card>
  )
}

// ════════════════════════════════════════════════════════════════

export default function InquiryReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const inquiryId = Number(searchParams.get('inquiry')) || 0

  if (inquiryId) {
    return (
      <ReviewWorkspace
        key={inquiryId}
        inquiryId={inquiryId}
        onBack={() => setSearchParams({})}
      />
    )
  }
  return <ReviewList onOpen={(id) => setSearchParams({ inquiry: String(id) })} />
}
