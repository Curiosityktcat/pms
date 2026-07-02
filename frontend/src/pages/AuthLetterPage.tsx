import { useEffect, useState } from 'react'
import {
  Card, Form, Select, Button, Descriptions, App, Typography, Empty,
  Tag, Alert, Input, Tabs, Popconfirm, Badge,
} from 'antd'
import {
  DownloadOutlined, FileWordOutlined, ArrowLeftOutlined,
  CheckCircleOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import RecordCards, { type RecordCardData } from '../components/RecordCards'
import { getBidOpenProjects } from '../services/project'
import type { Project } from '../services/project'
import { getSupervisors, getRepresentatives, generateAuthLetter } from '../services/people'
import type { Person } from '../services/people'
import {
  listAuthLetterRecords, createAuthLetterRecord, deleteAuthLetterRecord,
  downloadAuthLetterRecordWord,
} from '../services/authLetterRecord'
import type { AuthLetterRecord } from '../services/authLetterRecord'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const { Text } = Typography

type TabKey = 'pending' | 'done'

const ROUND_OPTIONS = [
  { value: 1, label: '第一次（正常）' },
  { value: 2, label: '第二次' },
  { value: 3, label: '第三次' },
  { value: 4, label: '第四次' },
  { value: 5, label: '第五次' },
]

function personLabel(p: Person) {
  const parts = [p.name]
  if (p.department) parts.push(p.department)
  if (p.id_card) parts.push(p.id_card)
  return parts.join(' · ')
}

function formatDate(s: string) {
  return s ? s.replace('T', ' ').substring(0, 16) : '—'
}

export default function AuthLetterPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [supervisors, setSupervisors] = useState<Person[]>([])
  const [representatives, setRepresentatives] = useState<Person[]>([])
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [records, setRecords] = useState<AuthLetterRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<TabKey>('pending')
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user } = useAuth()

  const projectIdFromQuery = searchParams.get('project_id')
  const roundFromQuery = searchParams.get('round')
  const bidTimeFromQuery = searchParams.get('bid_time')
  const fromBid = !!projectIdFromQuery

  const roundVal: number = Form.useWatch('round_number', form) ?? 1
  const repIds: number[] = Form.useWatch('representative_ids', form) ?? []

  const canDelete = ['officer', 'assistant', 'leader'].includes(user?.role || '')

  // 加载基础数据
  useEffect(() => {
    Promise.all([
      getBidOpenProjects(),
      getSupervisors(),
      getRepresentatives(),
    ]).then(([pRes, sRes, rRes]) => {
      // 「开标期」项目（已发公告 ~ 采购结果确认前）由后端 /projects/bid-open 统一返回，跨两阶段：
      // bid_open(可开标确认前) 与 result(可开标已确认、待结果)——流程是「先确认可开标→再做授权函」，
      // 故 result 段也要可见。采购部全部可见、代理仅本机构。这里再兜底过滤一次。
      const agencyProjects = pRes.data.data.filter(
        p => !p.is_draft && p.agency_code && ['bid_open', 'result'].includes(p.current_stage || ''),
      )
      setProjects(agencyProjects)
      setSupervisors(sRes.data.data)
      setRepresentatives(rRes.data.data)

      // 从开标管理跳转：自动预选项目 + 预填轮次和开标时间
      if (projectIdFromQuery) {
        const pid = parseInt(projectIdFromQuery)
        const p = agencyProjects.find(x => x.id === pid)
        if (p) {
          setSelectedProject(p)
          const roundNum = roundFromQuery ? parseInt(roundFromQuery) : 1
          const bidTime = bidTimeFromQuery
            ? decodeURIComponent(bidTimeFromQuery)
            : (p.bid_time || '')
          form.setFieldsValue({
            project_id: p.id,
            round_number: roundNum,
            bid_time_override: bidTime,
          })
          setActiveTab('pending')
        } else {
          message.warning('未找到对应项目，请手动选择')
        }
      }
    }).catch(() => message.error('加载数据失败'))
  }, [])

  // 加载授权函记录
  const loadRecords = async () => {
    setRecordsLoading(true)
    try {
      const res = await listAuthLetterRecords()
      setRecords(res.data.data)
    } catch {
      message.error('加载记录失败')
    } finally {
      setRecordsLoading(false)
    }
  }

  useEffect(() => { loadRecords() }, [])

  const handleProjectChange = (id: number) => {
    const p = projects.find(x => x.id === id) || null
    setSelectedProject(p)
    form.setFieldValue('bid_time_override', p?.bid_time || '')
  }

  const handleGenerate = async () => {
    let values: {
      project_id: number
      supervisor_id: number
      representative_ids: number[]
      round_number: number
      bid_time_override: string
    }
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    if (!selectedProject) return

    setLoading(true)
    try {
      const res = await generateAuthLetter(
        selectedProject.id,
        values.supervisor_id,
        values.representative_ids,
        values.round_number,
        values.bid_time_override,
      )
      const suffix = values.round_number > 1
        ? `（第${'一二三四五'[values.round_number - 1]}次）`
        : ''
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `授权函_${selectedProject.number}${suffix}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('授权函已生成，正在下载')

      // ── 自动保存授权函记录 ───────────────────────────────────────
      const supervisor = supervisors.find(s => s.id === values.supervisor_id)
      const reps = representatives.filter(r => values.representative_ids.includes(r.id))
      await createAuthLetterRecord({
        project_id: selectedProject.id,
        project_name: selectedProject.name,
        project_number: selectedProject.number || '',
        round_number: values.round_number,
        bid_time: values.bid_time_override || selectedProject.bid_time || '',
        supervisor_name: supervisor?.name || '',
        representative_names: reps.map(r => r.name).join('、'),
      })
      await loadRecords()
      message.success('授权函记录已保存')
      setActiveTab('done')  // 自动切换到已授权标签

    } catch (err: any) {
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text()
        try { message.error(JSON.parse(text).error || '生成失败') }
        catch { message.error('生成失败') }
      } else {
        message.error(err.response?.data?.error || '生成失败')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteRecord = async (id: number) => {
    try {
      await deleteAuthLetterRecord(id)
      message.success('已删除记录')
      loadRecords()
    } catch (err: any) {
      message.error(err.response?.data?.error || '删除失败')
    }
  }

  const [downloadingId, setDownloadingId] = useState<number | null>(null)

  const handleDownloadRecord = async (record: AuthLetterRecord) => {
    setDownloadingId(record.id)
    try {
      const res = await downloadAuthLetterRecordWord(record.id)
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const suffix = record.round_number > 1
        ? `（第${'一二三四五'[record.round_number - 1]}次）`
        : ''
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `授权函_${record.project_number || record.project_name}${suffix}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('授权函已下载')
    } catch (err: any) {
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text()
        try { message.error(JSON.parse(text).error || '下载失败') }
        catch { message.error('下载失败') }
      } else {
        message.error(err.response?.data?.error || '下载失败')
      }
    } finally {
      setDownloadingId(null)
    }
  }

  const handleReGenerate = (record: AuthLetterRecord) => {
    // 从已授权记录跳转回待授权，预选项目
    const p = projects.find(x => x.id === record.project_id)
    if (p) {
      setSelectedProject(p)
      form.setFieldsValue({
        project_id: p.id,
        round_number: record.round_number,
        bid_time_override: record.bid_time,
      })
    }
    setActiveTab('pending')
    message.info('已切换到待授权，请确认信息后重新生成')
  }

  // 预览项目名称
  const previewName = selectedProject
    ? selectedProject.name + (roundVal > 1
        ? `（第${'一二三四五'[roundVal - 1]}次）`
        : '')
    : ''

  // 已有授权函的项目ID集合（用于"待授权"标注）
  const doneProjectIds = new Set(records.map(r => `${r.project_id}-${r.round_number}`))

  // ── 已授权表格列 ────────────────────────────────────────────────
  const recordToCard = (row: AuthLetterRecord): RecordCardData => ({
    key: row.id,
    accent: '#1a73e8',
    title: row.project_name || '—',
    subtitle: row.project_number || '无编号',
    tags: row.round_number > 1
      ? <Tag color="orange" style={{ marginInlineEnd: 0 }}>第{'一二三四五'[row.round_number - 1]}次</Tag>
      : <Tag color="blue" style={{ marginInlineEnd: 0 }}>第一次</Tag>,
    fields: [
      { label: '开标时间', value: row.bid_time },
      { label: '监督', value: row.supervisor_name },
      { label: '代表', value: row.representative_names },
      { label: '生成人', value: row.generated_by },
    ],
    meta: row.generated_at ? `生成于 ${formatDate(row.generated_at)}` : undefined,
    actions: (
      <>
        <Button size="small" type="primary" ghost icon={<DownloadOutlined />}
          loading={downloadingId === row.id} onClick={() => handleDownloadRecord(row)}>
          下载授权函
        </Button>
        {canDelete && (
          <Button size="small" icon={<ReloadOutlined />} onClick={() => handleReGenerate(row)}>重新生成</Button>
        )}
        {canDelete && (
          <Popconfirm title="确认删除该记录？" onConfirm={() => handleDeleteRecord(row.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        )}
      </>
    ),
  })

  return (
    <Card>
      {/* 顶部标题 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        {fromBid && (
          <Button icon={<ArrowLeftOutlined />} size="small" onClick={() => navigate('/bid')}>
            返回开标管理
          </Button>
        )}
        <div style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50' }}>
          <FileWordOutlined style={{ marginRight: 8, color: '#1677ff' }} />
          授权函管理
        </div>
      </div>

      {/* 标签页 */}
      <Tabs
        activeKey={activeTab}
        onChange={k => setActiveTab(k as TabKey)}
        items={[
          {
            key: 'pending',
            label: (
              <span>
                <FileWordOutlined style={{ marginRight: 4 }} />
                待授权（生成授权函）
              </span>
            ),
          },
          {
            key: 'done',
            label: (
              <span>
                <CheckCircleOutlined style={{ marginRight: 4, color: '#52c41a' }} />
                已授权
                {records.length > 0 && (
                  <Badge count={records.length} size="small"
                    style={{ marginLeft: 6, backgroundColor: '#52c41a' }} />
                )}
              </span>
            ),
          },
        ]}
      />

      {/* ══ 待授权 Tab ══════════════════════════════════════════════ */}
      {activeTab === 'pending' && (
        <>
          {fromBid && selectedProject && (
            <Alert
              type="success" showIcon style={{ marginBottom: 16 }}
              message={`已从开标管理跳转：项目「${selectedProject.name}」，开标时间和轮次已自动导入，请补充监督人员和采购人代表后生成。`}
            />
          )}

          <Alert
            type="info" showIcon style={{ marginBottom: 20 }}
            message="仅显示已正式立项且走代理机构的项目。生成后记录将自动保存至「已授权」，打印1份、加盖公章。"
          />

          <Form form={form} layout="vertical" style={{ maxWidth: 600 }}
            initialValues={{ round_number: 1 }}
          >
            {/* 项目选择 */}
            <Form.Item label="选择项目" name="project_id"
              rules={[{ required: true, message: '请选择项目' }]}
            >
              <Select
                showSearch
                placeholder="搜索项目名称或编号"
                filterOption={(input, opt) =>
                  (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())
                }
                onChange={handleProjectChange}
                options={projects.map(p => {
                  const hasDone = doneProjectIds.has(`${p.id}-1`) ||
                    Array.from(doneProjectIds).some(k => k.startsWith(`${p.id}-`))
                  return {
                    value: p.id,
                    label: `${p.number}  ${p.name}${hasDone ? '  ✓已生成' : ''}`,
                  }
                })}
              />
            </Form.Item>

            {/* 项目信息 */}
            {selectedProject && (
              <Descriptions size="small" bordered column={2} style={{ marginBottom: 16 }}>
                <Descriptions.Item label="项目名称" span={2}>
                  {selectedProject.name}
                </Descriptions.Item>
                <Descriptions.Item label="编号">
                  <Text code>{selectedProject.number}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color="blue">{selectedProject.status}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="代理机构">
                  {selectedProject.agency_name || selectedProject.agency_code}
                </Descriptions.Item>
                <Descriptions.Item label="经办人">
                  {selectedProject.officer || <Text type="secondary">未填写</Text>}
                </Descriptions.Item>
              </Descriptions>
            )}

            {/* 开标次数 + 开标时间 */}
            <div style={{ display: 'flex', gap: 16 }}>
              <Form.Item label="开标次数" name="round_number" style={{ width: 180 }}>
                <Select options={ROUND_OPTIONS} />
              </Form.Item>
              <Form.Item
                label="本次开标时间"
                name="bid_time_override"
                style={{ flex: 1 }}
                extra="从开标管理跳转时已自动填入，第二次及以后可修改"
              >
                <Input placeholder="如：2026年6月15日14:00" />
              </Form.Item>
            </div>

            {/* 预览名称 */}
            {previewName && (
              <div style={{
                marginBottom: 16, padding: '8px 12px',
                background: '#f6ffed', border: '1px solid #b7eb8f',
                borderRadius: 6, fontSize: 13,
              }}>
                授权函中项目名称将显示为：<Text strong>{previewName}</Text>
              </div>
            )}

            {/* 监督人员 */}
            <Form.Item label="监督人员" name="supervisor_id"
              rules={[{ required: true, message: '请选择监督人员' }]}
            >
              <Select
                showSearch
                placeholder="选择监督人员"
                filterOption={(input, opt) =>
                  (opt?.label as string || '').includes(input)
                }
                options={supervisors.map(s => ({ value: s.id, label: personLabel(s) }))}
              />
            </Form.Item>

            {/* 采购人代表 */}
            <Form.Item
              label={`采购人代表${repIds.length > 0 ? `（已选 ${repIds.length} 人）` : ''}`}
              name="representative_ids"
              rules={[{ required: true, type: 'array', min: 1, message: '请至少选择一位采购人代表' }]}
              extra={
                <span>
                  可多选 · 如需新增请前往{' '}
                  <a href="/people-manage" target="_blank">人员管理</a>
                </span>
              }
            >
              <Select
                mode="multiple"
                showSearch
                placeholder="搜索姓名或科室，可多选"
                filterOption={(input, opt) =>
                  (opt?.label as string || '').includes(input)
                }
                maxTagCount={3}
                options={representatives.map(r => ({ value: r.id, label: personLabel(r) }))}
              />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                size="large"
                loading={loading}
                disabled={!selectedProject}
                onClick={handleGenerate}
              >
                生成授权函（下载 Word）
              </Button>
              <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
                生成后自动保存至「已授权」记录
              </Text>
            </Form.Item>
          </Form>

          {projects.length === 0 && !loading && (
            <Empty description="暂无可生成授权函的项目（需要已立项 + 走代理机构）" />
          )}
        </>
      )}

      {/* ══ 已授权 Tab ══════════════════════════════════════════════ */}
      {activeTab === 'done' && (
        <>
          <Alert
            type="success" showIcon style={{ marginBottom: 16 }}
            message="以下为已生成授权函的项目记录。点击「重新生成」可切换到待授权标签重新填写并生成。"
          />
          <RecordCards
            dataSource={records}
            loading={recordsLoading}
            emptyText="暂无授权函记录，生成后自动保存"
            toCard={recordToCard}
          />
        </>
      )}
    </Card>
  )
}
