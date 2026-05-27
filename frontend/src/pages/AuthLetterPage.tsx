import { useEffect, useState } from 'react'
import {
  Card, Form, Select, Button, Descriptions, App, Typography, Empty, Tag, Alert, Input,
} from 'antd'
import { DownloadOutlined, FileWordOutlined } from '@ant-design/icons'
import { getProjects } from '../services/project'
import type { Project } from '../services/project'
import { getSupervisors, getRepresentatives, generateAuthLetter } from '../services/people'
import type { Person } from '../services/people'

const { Text } = Typography

const ROUND_OPTIONS = [
  { value: 1, label: '第一次（正常）' },
  { value: 2, label: '第二次' },
  { value: 3, label: '第三次' },
  { value: 4, label: '第四次' },
  { value: 5, label: '第五次' },
]

/** 人员下拉选项：姓名 + 科室 + 身份证（用于区分同名） */
function personLabel(p: Person) {
  const parts = [p.name]
  if (p.department) parts.push(p.department)
  if (p.id_card) parts.push(p.id_card)
  return parts.join(' · ')
}

export default function AuthLetterPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [supervisors, setSupervisors] = useState<Person[]>([])
  const [representatives, setRepresentatives] = useState<Person[]>([])
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()
  const { message } = App.useApp()

  const roundVal: number = Form.useWatch('round_number', form) ?? 1
  const repIds: number[] = Form.useWatch('representative_ids', form) ?? []

  useEffect(() => {
    Promise.all([
      getProjects(false),
      getSupervisors(),
      getRepresentatives(),
    ]).then(([pRes, sRes, rRes]) => {
      const agencyProjects = pRes.data.data.filter(p => !p.is_draft && p.agency_code)
      setProjects(agencyProjects)
      setSupervisors(sRes.data.data)
      setRepresentatives(rRes.data.data)
    }).catch(() => message.error('加载数据失败'))
  }, [])

  const handleProjectChange = (id: number) => {
    const p = projects.find(x => x.id === id) || null
    setSelectedProject(p)
    // 把项目的开标时间预填到覆盖字段
    form.setFieldValue('bid_time_override', p?.bid_time || '')
  }

  const handleGenerate = async () => {
    let values: {
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

  // 预览项目名称在授权函里显示的样子
  const previewName = selectedProject
    ? selectedProject.name + (roundVal > 1
        ? `（第${'一二三四五'[roundVal - 1]}次）`
        : '')
    : ''

  return (
    <Card>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#2c3e50', marginBottom: 20 }}>
        <FileWordOutlined style={{ marginRight: 8, color: '#1677ff' }} />
        授权函生成
      </div>

      <Alert
        type="info" showIcon
        message="仅显示已正式立项且走代理机构的项目。生成后请打印1份、加盖公章。"
        style={{ marginBottom: 20 }}
      />

      <Form form={form} layout="vertical" style={{ maxWidth: 580 }}
        initialValues={{ round_number: 1 }}
      >
        {/* 项目 */}
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
            options={projects.map(p => ({
              value: p.id,
              label: `${p.number}  ${p.name}`,
            }))}
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
            <Descriptions.Item label="项目经办人">
              {selectedProject.officer || <Text type="secondary">未填写</Text>}
            </Descriptions.Item>
          </Descriptions>
        )}

        {/* 开标次数 */}
        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item label="开标次数" name="round_number" style={{ width: 180 }}>
            <Select options={ROUND_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="本次开标时间"
            name="bid_time_override"
            style={{ flex: 1 }}
            extra="第二次及以后可修改为本次实际时间"
          >
            <Input placeholder="如：2026年6月15日14:00" />
          </Form.Item>
        </div>

        {/* 预览名称 */}
        {previewName && (
          <div style={{ marginBottom: 16, padding: '8px 12px', background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 6, fontSize: 13 }}>
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
            options={supervisors.map(s => ({
              value: s.id,
              label: personLabel(s),
            }))}
          />
        </Form.Item>

        {/* 采购人代表（多选） */}
        <Form.Item
          label={`采购人代表${repIds.length > 0 ? `（已选 ${repIds.length} 人）` : ''}`}
          name="representative_ids"
          rules={[{ required: true, type: 'array', min: 1, message: '请至少选择一位采购人代表' }]}
          extra={<span>可多选 · 如需新增请前往 <a href="/people-manage" target="_blank">人员管理</a></span>}
        >
          <Select
            mode="multiple"
            showSearch
            placeholder="搜索姓名或科室，可多选"
            filterOption={(input, opt) =>
              (opt?.label as string || '').includes(input)
            }
            maxTagCount={3}
            options={representatives.map(r => ({
              value: r.id,
              label: personLabel(r),
            }))}
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
        </Form.Item>
      </Form>

      {projects.length === 0 && !loading && (
        <Empty description="暂无可生成授权函的项目（需要已立项 + 走代理机构）" />
      )}
    </Card>
  )
}
